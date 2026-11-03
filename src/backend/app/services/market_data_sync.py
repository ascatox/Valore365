"""Sincronizzazione affidabile dei dati di mercato (TASK-54).

Una sola funzione fa il lavoro, chiunque la avvii: ``MarketDataSyncService.run_sync``
(o ``start_in_background`` per l'endpoint interno). Trigger: recupero
all'avvio ('startup'), GitHub Actions via POST /api/internal/market-data/sync
('external'), job delle barre dello scheduler interno ('scheduler'), manuale.

Concorrenza: prima un lock di processo (threading.Lock), poi un lock di
database ``pg_try_advisory_xact_lock(MARKET_DATA_SYNC_LOCK_KEY)`` preso su una
connessione dedicata dentro una transazione tenuta aperta per tutta la run e
chiusa nel finally. Variante "xact" invece della sessione perché Supabase
espone Postgres anche dietro PgBouncer in transaction mode: un lock di
sessione resterebbe sulla connessione server sbagliata, uno di transazione
vive esattamente quanto la transazione (e si libera da solo se la connessione
cade). È l'unica connessione tenuta durante le chiamate di rete: tutte le
altre letture/scritture sono brevi (pool: db_pool_size + db_max_overflow,
una connessione in più per la run).

Passi (registro ``DEFAULT_STEPS``, estendibile con ``register_step``):
  quotes  quotazioni di tutti gli asset attivi in portafoglio (best effort: non
          decide l'esito, la chiusura giornaliera è il dato di riferimento);
  bars    barre giornaliere dall'ultima barra per asset (finestra massima
          market_data_sync_max_lookback_days);
  fx      cambi giornalieri delle valute in uso verso le valute base.

Esito: success solo se ogni asset prezzabile ha la barra dell'ultima seduta
conclusa della sua borsa (calendari di market_hours: weekend e festività non
sono sedute mancate; una seduta conta come conclusa dopo chiusura + grace) e
nessun passo bloccante ha errori; failed se un passo bloccante fallisce o
nessun asset è aggiornato; altrimenti partial. last_successful_price_sync =
finished_at dell'ultima run success: una run partial o failed non lo sposta,
mentre lo stato per asset (market_data_asset_sync) avanza comunque.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Callable

from sqlalchemy import text

from .market_hours import completed_sessions_after, last_completed_session_close

logger = logging.getLogger(__name__)

# Chiave del lock advisory (bigint arbitrario, unico nel database).
MARKET_DATA_SYNC_LOCK_KEY = 54_365_001
VALID_TRIGGERS = frozenset({"startup", "external", "scheduler", "manual"})
# La finestra delle barre copre sempre almeno un weekend lungo con festività.
MIN_LOOKBACK_DAYS = 5
# Il recupero all'avvio non riparte se una run è finita da meno di così (un
# asset che il provider non aggiorna più non deve far ripartire una run a
# ogni risveglio dell'istanza).
STARTUP_RETRY_COOLDOWN_MINUTES = 180
MAX_STEP_ERRORS = 20


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def _iso(value: Any) -> str | None:
    return value.isoformat() if value is not None and hasattr(value, "isoformat") else None


# --- lock -----------------------------------------------------------------


class PgAdvisoryLock:
    """pg_try_advisory_xact_lock on a dedicated connection, held until release()."""

    def __init__(self, engine, key: int = MARKET_DATA_SYNC_LOCK_KEY) -> None:
        self.engine = engine
        self.key = key
        self._conn = None
        self._trans = None

    def acquire(self) -> bool:
        conn = self.engine.connect()
        try:
            trans = conn.begin()
            acquired = bool(conn.execute(text("select pg_try_advisory_xact_lock(:key)"), {"key": self.key}).scalar())
        except Exception:
            conn.close()
            raise
        if not acquired:
            trans.rollback()
            conn.close()
            return False
        self._conn, self._trans = conn, trans
        return True

    def heartbeat(self) -> None:
        """Short query on the lock connection between steps (keeps it from looking idle)."""
        if self._conn is None:
            return
        try:
            self._conn.execute(text("select 1"))
        except Exception as exc:  # the lock may be gone with the connection
            logger.warning("market_data_sync lock heartbeat failed: %s", exc)

    def release(self) -> None:
        conn, trans = self._conn, self._trans
        self._conn = self._trans = None
        if conn is None:
            return
        try:
            if trans is not None and trans.is_active:
                trans.rollback()
        except Exception as exc:
            logger.warning("market_data_sync lock release failed: %s", exc)
        finally:
            conn.close()


# --- results ----------------------------------------------------------------


@dataclass(frozen=True)
class AlreadyRunning:
    run_id: int | None = None
    status: str = "already_running"


@dataclass(frozen=True)
class SyncStarted:
    run_id: int
    status: str = "running"


@dataclass
class SyncOutcome:
    run_id: int
    status: str
    steps: list[dict]
    assets_requested: int = 0
    assets_updated: int = 0
    assets_failed: int = 0
    error: str | None = None


@dataclass
class SyncContext:
    """Shared state of one run, passed to every step."""

    run_id: int
    trigger: str
    now: datetime
    grace: timedelta
    provider: str
    max_lookback_days: int
    assets: list = field(default_factory=list)  # held, priceable PricingAsset
    skipped: list = field(default_factory=list)  # held, no provider symbol (ISIN only)
    latest_bars: dict[int, date] = field(default_factory=dict)
    # asset_id -> True when its bar covers the last completed session
    up_to_date: dict[int, bool] = field(default_factory=dict)
    lookback_days: int = MIN_LOOKBACK_DAYS


@dataclass(frozen=True)
class SyncStep:
    name: str
    run: Callable[["MarketDataSyncService", SyncContext], dict]
    # A blocking step decides the run status; a best-effort one is only recorded.
    blocking: bool = True


def asset_is_up_to_date(market_symbol: str, last_bar: date | None, now: datetime, grace: timedelta) -> bool:
    """True when the last bar covers every session of the asset's market closed before now - grace."""
    if last_bar is None:
        return False
    return completed_sessions_after(market_symbol, last_bar, now - grace, limit=1) == 0


def _market_symbol(asset) -> str:
    return getattr(asset, "market_symbol", None) or asset.provider_symbol


# --- steps ------------------------------------------------------------------


def _errors_by_symbol(errors: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for message in errors or []:
        symbol, _, reason = str(message).partition(": ")
        out.setdefault(symbol, reason or str(message))
    return out


def step_quotes(svc: "MarketDataSyncService", ctx: SyncContext) -> dict:
    if not ctx.assets:
        return {"status": "ok", "requested": 0, "updated": 0, "failed": 0}
    response = svc.pricing_service.refresh_prices(assets=ctx.assets)
    ts_by_asset = {item.asset_id: item.ts for item in response.items}
    errors = _errors_by_symbol(list(response.errors))
    now = svc._clock()
    rows = []
    for asset in ctx.assets:
        if asset.asset_id in ts_by_asset:
            rows.append({"asset_id": asset.asset_id, "last_tick_at": _aware(ts_by_asset[asset.asset_id])})
        else:
            reason = errors.get(asset.provider_symbol, "nessuna quotazione dal provider")
            rows.append({"asset_id": asset.asset_id, "last_error": f"quotazione: {reason}", "last_error_at": now})
    svc.repository.upsert_market_data_asset_sync(rows)
    failed = len(ctx.assets) - len(ts_by_asset)
    return {
        "status": "ok" if failed == 0 else ("failed" if not ts_by_asset else "partial"),
        "requested": len(ctx.assets),
        "updated": len(ts_by_asset),
        "failed": failed,
        "unchanged_ts": len(getattr(response, "unchanged_ts_symbols", None) or []),
        "errors": list(response.errors)[:MAX_STEP_ERRORS],
    }


def step_bars(svc: "MarketDataSyncService", ctx: SyncContext) -> dict:
    if not ctx.assets:
        return {"status": "ok", "requested": 0, "updated": 0, "failed": 0, "lookback_days": 0}
    result = svc.historical_service.refresh_recent_daily_bars(
        days=ctx.lookback_days, now=ctx.now, assets=ctx.assets,
    )
    latest = svc.repository.get_latest_daily_bars([a.asset_id for a in ctx.assets]) or {}
    failed_symbols = set(result.failed)
    now = svc._clock()
    rows, behind = [], []
    for asset in ctx.assets:
        last_bar = (latest.get(asset.asset_id) or (None, None))[0]
        ctx.latest_bars[asset.asset_id] = last_bar
        ok = asset_is_up_to_date(_market_symbol(asset), last_bar, ctx.now, ctx.grace)
        ctx.up_to_date[asset.asset_id] = ok
        row: dict[str, Any] = {"asset_id": asset.asset_id, "last_bar_date": last_bar}
        if ok:
            row["last_success_at"] = now
        else:
            behind.append(asset.provider_symbol)
            reason = (
                "errore del provider sulle barre giornaliere"
                if asset.provider_symbol in failed_symbols
                else "il provider non ha la barra dell'ultima seduta conclusa"
            )
            row.update(last_error=f"barre: {reason}", last_error_at=now)
        rows.append(row)
    svc.repository.upsert_market_data_asset_sync(rows)
    if not behind:
        # Provider errors on assets that already have their last session are
        # recorded but do not make the data incomplete.
        status = "ok"
    elif len(behind) == len(ctx.assets):
        status = "failed"
    else:
        status = "partial"
    return {
        "status": status,
        "requested": len(ctx.assets),
        "lookback_days": ctx.lookback_days,
        "updated": len(result.updated),
        "up_to_date": len(ctx.assets) - len(behind),
        "behind": len(behind),
        "behind_symbols": behind[:MAX_STEP_ERRORS],
        "failed": len(result.failed),
        "errors": [f"{s}: errore del provider" for s in result.failed][:MAX_STEP_ERRORS],
    }


def step_fx(svc: "MarketDataSyncService", ctx: SyncContext) -> dict:
    pairs = svc.repository.get_fx_pairs_in_use()
    if not pairs:
        return {"status": "ok", "requested": 0, "updated": 0, "failed": 0}
    result = svc.historical_service.refresh_recent_fx_rates(pairs, days=ctx.lookback_days, now=ctx.now)
    if not result.failed:
        status = "ok"
    elif len(result.failed) == len(pairs):
        status = "failed"
    else:
        status = "partial"
    return {
        "status": status,
        "requested": len(pairs),
        "updated": len(result.updated),
        "no_data": len(result.no_data),
        "failed": len(result.failed),
        "last_dates": {k: v.isoformat() for k, v in result.last_dates.items()},
        "errors": result.errors[:MAX_STEP_ERRORS],
    }


DEFAULT_STEPS: tuple[SyncStep, ...] = (
    SyncStep("quotes", step_quotes, blocking=False),
    SyncStep("bars", step_bars),
    SyncStep("fx", step_fx),
)


def run_status(steps: list[dict], blocking: set[str], ctx: SyncContext) -> str:
    """success / partial / failed from the recorded steps and the per-asset check."""
    blocking_steps = [s for s in steps if s.get("name") in blocking]
    if any(s.get("status") == "failed" for s in blocking_steps):
        return "failed"
    behind = [aid for aid in (a.asset_id for a in ctx.assets) if not ctx.up_to_date.get(aid, False)]
    if behind or any(s.get("status") != "ok" for s in blocking_steps):
        return "partial"
    return "success"


# --- service ----------------------------------------------------------------


class MarketDataSyncService:
    def __init__(
        self,
        settings,
        repository,
        pricing_service,
        historical_service,
        *,
        lock_factory: Callable[[], Any] | None = None,
        thread_factory: Callable[..., Any] = threading.Thread,
        steps: tuple[SyncStep, ...] | list[SyncStep] = DEFAULT_STEPS,
        clock: Callable[[], datetime] = _utcnow,
    ) -> None:
        self.settings = settings
        self.repository = repository
        self.pricing_service = pricing_service
        self.historical_service = historical_service
        self._lock_factory = lock_factory or (lambda: PgAdvisoryLock(repository.engine))
        self._thread_factory = thread_factory
        self.steps: list[SyncStep] = list(steps)
        self._clock = clock
        self._local_lock = threading.Lock()

    # --- configuration ---

    def register_step(self, step: SyncStep) -> None:
        """Add a step (e.g. ETF enrichment, asset metadata) run after the existing ones."""
        if any(s.name == step.name for s in self.steps):
            raise ValueError(f"step {step.name} già registrato")
        self.steps.append(step)

    @property
    def provider(self) -> str:
        return str(getattr(self.settings, "finance_provider", "yfinance")).strip().lower()

    @property
    def grace(self) -> timedelta:
        return timedelta(minutes=max(0, int(getattr(self.settings, "market_data_sync_grace_minutes", 60))))

    @property
    def max_lookback_days(self) -> int:
        return max(MIN_LOOKBACK_DAYS, int(getattr(self.settings, "market_data_sync_max_lookback_days", 30)))

    # --- state reads ---

    def _held_assets(self) -> tuple[list, list]:
        from ..finance_client import is_unpriceable_on_yahoo

        assets = list(self.repository.get_held_assets_for_daily_bars(self.provider))
        skipped = [a for a in assets if is_unpriceable_on_yahoo(self.provider, a.provider_symbol)]
        return [a for a in assets if a not in skipped], skipped

    def overview(self) -> dict[str, Any]:
        return self.repository.get_market_data_sync_overview()

    def latest_close_cutoff(self, assets: list, now: datetime) -> datetime | None:
        """Most recent close (+ grace) already past at `now` among the assets' markets."""
        reference = now - self.grace
        closes = [last_completed_session_close(_market_symbol(a), reference) for a in assets]
        closes = [c for c in closes if c is not None]
        return max(closes) + self.grace if closes else None

    def lagging_assets(self, now: datetime | None = None, *, assets: list | None = None) -> list[dict]:
        """Held assets whose last bar misses a completed session of their market."""
        now = now or self._clock()
        if assets is None:
            assets, _ = self._held_assets()
        if not assets:
            return []
        latest = self.repository.get_latest_daily_bars([a.asset_id for a in assets]) or {}
        state = self._asset_state([a.asset_id for a in assets])
        out = []
        for asset in assets:
            last_bar = (latest.get(asset.asset_id) or (None, None))[0]
            if asset_is_up_to_date(_market_symbol(asset), last_bar, now, self.grace):
                continue
            missed = (
                completed_sessions_after(_market_symbol(asset), last_bar, now - self.grace)
                if last_bar else None
            )
            st = state.get(asset.asset_id) or {}
            out.append({
                "asset_id": asset.asset_id,
                "symbol": asset.symbol,
                "provider_symbol": asset.provider_symbol,
                "last_bar_date": _iso(last_bar),
                "missed_sessions": missed,
                "last_attempt_at": _iso(self._last_attempt(st)),
                "last_error": st.get("last_error"),
            })
        return out

    def _asset_state(self, asset_ids: list[int]) -> dict[int, dict]:
        try:
            return self.repository.get_market_data_asset_sync(asset_ids) or {}
        except Exception as exc:
            logger.warning("market_data_sync asset state unavailable: %s", exc)
            return {}

    @staticmethod
    def _last_attempt(state: dict) -> datetime | None:
        stamps = [_aware(state.get("last_success_at")), _aware(state.get("last_error_at"))]
        stamps = [s for s in stamps if s is not None]
        return max(stamps) if stamps else None

    def needs_sync(self, now: datetime | None = None, *, retry_cooldown_minutes: int = 0) -> bool:
        """True when a sync is due.

        - no success run yet, or the last success finished before the most
          recent close (+ grace) among the held assets' markets: weekends and
          holidays are not sessions, so they never make a sync "missed";
        - or an asset is behind its own last completed session and nothing was
          attempted for it since that session closed (+ grace).
        ``retry_cooldown_minutes`` > 0 (startup): False when any run finished
        that recently, so repeated restarts do not hammer the provider.
        """
        now = now or self._clock()
        overview = self.overview()
        if retry_cooldown_minutes > 0:
            last_finished = overview.get("last_finished") or {}
            finished_at = _aware(last_finished.get("finished_at"))
            if finished_at is not None and now - finished_at < timedelta(minutes=retry_cooldown_minutes):
                return False
        assets, _ = self._held_assets()
        last_success = overview.get("last_success") or {}
        success_at = _aware(last_success.get("finished_at"))
        if success_at is None:
            return True
        cutoff = self.latest_close_cutoff(assets, now)
        if cutoff is not None and success_at < cutoff:
            return True
        if not assets:
            return False
        latest = self.repository.get_latest_daily_bars([a.asset_id for a in assets]) or {}
        state = self._asset_state([a.asset_id for a in assets])
        reference = now - self.grace
        for asset in assets:
            last_bar = (latest.get(asset.asset_id) or (None, None))[0]
            if asset_is_up_to_date(_market_symbol(asset), last_bar, now, self.grace):
                continue
            close = last_completed_session_close(_market_symbol(asset), reference)
            attempt = self._last_attempt(state.get(asset.asset_id) or {})
            if attempt is None or close is None or attempt < close + self.grace:
                return True
        return False

    # --- runs ---

    def try_begin(self, trigger: str):
        """Take the locks and create the run row: a handle, or AlreadyRunning."""
        if trigger not in VALID_TRIGGERS:
            raise ValueError(f"trigger non valido: {trigger}")
        if not self._local_lock.acquire(blocking=False):
            return AlreadyRunning(run_id=self._running_run_id())
        lock = None
        try:
            lock = self._lock_factory()
            if not lock.acquire():
                lock = None
                self._local_lock.release()
                return AlreadyRunning(run_id=self._running_run_id())
            run_id = self.repository.create_market_data_sync_run(trigger)
        except Exception:
            if lock is not None:
                lock.release()
            self._local_lock.release()
            raise
        logger.info("market_data_sync started run_id=%s trigger=%s", run_id, trigger)
        return _RunHandle(run_id=run_id, trigger=trigger, lock=lock)

    def _running_run_id(self) -> int | None:
        try:
            running = self.overview().get("running") or {}
            return int(running["id"]) if running.get("id") is not None else None
        except Exception:
            return None

    def run_sync(self, trigger: str):
        """Run the whole sync in this thread: SyncOutcome, or AlreadyRunning."""
        handle = self.try_begin(trigger)
        if isinstance(handle, AlreadyRunning):
            logger.info("market_data_sync skipped trigger=%s: already running run_id=%s", trigger, handle.run_id)
            return handle
        return self._execute(handle)

    def start_in_background(self, trigger: str):
        """Lock + run row now, steps in a daemon thread: SyncStarted, or AlreadyRunning."""
        handle = self.try_begin(trigger)
        if isinstance(handle, AlreadyRunning):
            return handle
        try:
            thread = self._thread_factory(
                target=self._execute, args=(handle,), name=f"market-data-sync-{handle.run_id}", daemon=True,
            )
            thread.start()
        except Exception:
            self._finish_lock(handle)
            raise
        return SyncStarted(run_id=handle.run_id)

    def _finish_lock(self, handle: "_RunHandle") -> None:
        try:
            handle.lock.release()
        finally:
            self._local_lock.release()

    def _execute(self, handle: "_RunHandle") -> SyncOutcome:
        steps: list[dict] = []
        status, error = "failed", None
        ctx = SyncContext(
            run_id=handle.run_id,
            trigger=handle.trigger,
            now=self._clock(),
            grace=self.grace,
            provider=self.provider,
            max_lookback_days=self.max_lookback_days,
        )
        try:
            try:
                ctx.assets, ctx.skipped = self._held_assets()
                ctx.lookback_days = self._lookback_days(ctx)
            except Exception as exc:
                error = f"lettura degli asset in portafoglio fallita: {str(exc)[:200]}"
                logger.exception("market_data_sync run_id=%s setup failed", handle.run_id)
                raise _SetupFailed() from exc
            for step in self.steps:
                steps.append(self._run_step(step, ctx))
                self._save_progress(handle.run_id, steps, ctx)
                handle.lock.heartbeat()
            status = run_status(steps, {s.name for s in self.steps if s.blocking}, ctx)
            if status != "success":
                error = self._summary_error(steps, ctx)
        except _SetupFailed:
            status = "failed"
        except Exception as exc:  # never leave a run 'running'
            status, error = "failed", f"errore inatteso: {str(exc)[:200]}"
            logger.exception("market_data_sync run_id=%s failed", handle.run_id)
        finally:
            outcome = SyncOutcome(
                run_id=handle.run_id,
                status=status,
                steps=steps,
                assets_requested=len(ctx.assets) + len(ctx.skipped),
                assets_updated=sum(1 for a in ctx.assets if ctx.up_to_date.get(a.asset_id)),
                assets_failed=sum(1 for a in ctx.assets if not ctx.up_to_date.get(a.asset_id)),
                error=error,
            )
            try:
                self.repository.update_market_data_sync_run(
                    handle.run_id,
                    steps=steps,
                    status=status,
                    assets_requested=outcome.assets_requested,
                    assets_updated=outcome.assets_updated,
                    assets_failed=outcome.assets_failed,
                    error=error,
                    finished_at=self._clock(),
                )
            except Exception:
                logger.exception("market_data_sync run_id=%s: unable to record the outcome", handle.run_id)
            self._finish_lock(handle)
        log = logger.info if status == "success" else logger.warning
        log(
            "market_data_sync finished run_id=%s trigger=%s status=%s assets=%s up_to_date=%s behind=%s skipped=%s%s",
            handle.run_id, handle.trigger, status, outcome.assets_requested, outcome.assets_updated,
            outcome.assets_failed, len(ctx.skipped), f" error={error}" if error else "",
        )
        return outcome

    def _lookback_days(self, ctx: SyncContext) -> int:
        """Days back to the oldest per-asset last bar (+1), capped at max_lookback_days."""
        if not ctx.assets:
            return MIN_LOOKBACK_DAYS
        latest = self.repository.get_latest_daily_bars([a.asset_id for a in ctx.assets]) or {}
        today = ctx.now.astimezone(UTC).date()
        days = []
        for asset in ctx.assets:
            last_bar = (latest.get(asset.asset_id) or (None, None))[0]
            days.append(ctx.max_lookback_days if last_bar is None else (today - last_bar).days + 1)
        return max(MIN_LOOKBACK_DAYS, min(ctx.max_lookback_days, max(days)))

    def _run_step(self, step: SyncStep, ctx: SyncContext) -> dict:
        started = self._clock()
        try:
            result = dict(step.run(self, ctx) or {})
        except Exception as exc:
            logger.exception("market_data_sync run_id=%s step=%s failed", ctx.run_id, step.name)
            result = {"status": "failed", "errors": [f"errore del passo: {str(exc)[:200]}"]}
        result.setdefault("status", "ok")
        return {
            "name": step.name,
            "blocking": step.blocking,
            **result,
            "started_at": started.isoformat(),
            "finished_at": self._clock().isoformat(),
        }

    def _save_progress(self, run_id: int, steps: list[dict], ctx: SyncContext) -> None:
        try:
            self.repository.update_market_data_sync_run(run_id, steps=steps, assets_requested=len(ctx.assets) + len(ctx.skipped))
        except Exception as exc:
            logger.warning("market_data_sync run_id=%s: unable to save progress: %s", run_id, exc)

    @staticmethod
    def _summary_error(steps: list[dict], ctx: SyncContext) -> str:
        parts = [f"{s['name']}={s.get('status')}" for s in steps if s.get("status") != "ok"]
        behind = [a.provider_symbol for a in ctx.assets if not ctx.up_to_date.get(a.asset_id)]
        if behind:
            parts.append("asset non aggiornati: " + ",".join(behind[:MAX_STEP_ERRORS]))
        return "; ".join(parts) or "esito non completo"

    # --- status payload (internal endpoint) ---

    def status_payload(self, now: datetime | None = None) -> dict[str, Any]:
        """Last run, last success and lagging assets: counts and symbols only, no user data."""
        now = now or self._clock()
        overview = self.overview()
        assets, skipped = self._held_assets()
        lagging = self.lagging_assets(now, assets=assets)
        return {
            "last_run": public_run(overview.get("last_run")),
            "running": public_run(overview.get("running")),
            "last_successful_price_sync": _iso((overview.get("last_success") or {}).get("finished_at")),
            "last_success_run_id": (overview.get("last_success") or {}).get("id"),
            "needs_sync": self.needs_sync(now),
            "held_assets": len(assets) + len(skipped),
            "skipped_symbols": [a.provider_symbol for a in skipped],
            "lagging": [
                {k: row[k] for k in ("symbol", "last_bar_date", "missed_sessions", "last_attempt_at", "last_error")}
                for row in lagging
            ],
        }


def public_run(run: dict | None) -> dict | None:
    if not run:
        return None
    return {
        "run_id": run.get("id"),
        "trigger": run.get("trigger"),
        "status": run.get("status"),
        "started_at": _iso(run.get("started_at")),
        "finished_at": _iso(run.get("finished_at")),
        "assets_requested": run.get("assets_requested"),
        "assets_updated": run.get("assets_updated"),
        "assets_failed": run.get("assets_failed"),
        "error": run.get("error"),
        "steps": run.get("steps") or [],
    }


class _SetupFailed(Exception):
    pass


@dataclass
class _RunHandle:
    run_id: int
    trigger: str
    lock: Any


# --- startup catch-up -------------------------------------------------------


def launch_startup_catch_up(service: MarketDataSyncService, settings, *, thread_factory=threading.Thread):
    """At app startup: a daemon thread that checks needs_sync() and, if due, runs the sync.

    Returns the started thread, or None when MARKET_DATA_SYNC_ON_STARTUP is off.
    The check itself runs in the thread too, so startup never waits on the DB.
    """
    if not bool(getattr(settings, "market_data_sync_on_startup", True)):
        logger.info("market_data_sync startup catch-up disabled")
        return None

    def work() -> None:
        try:
            if not service.needs_sync(retry_cooldown_minutes=STARTUP_RETRY_COOLDOWN_MINUTES):
                logger.info("market_data_sync startup catch-up: data up to date")
                return
            logger.info("market_data_sync startup catch-up: sync needed")
            service.run_sync("startup")
        except Exception as exc:
            logger.warning("market_data_sync startup catch-up failed: %s", exc)

    thread = thread_factory(target=work, name="market-data-sync-startup", daemon=True)
    thread.start()
    return thread
