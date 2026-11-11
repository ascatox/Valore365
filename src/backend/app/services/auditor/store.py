"""Corsa notturna dell'Auditor in produzione e storico degli esiti (TASK-80).

Contratto: ``docs/auditor/architecture.md`` §6 (modalità notturna), §6.1 (endpoint), §7.2
(cosa si salva), §8 (configurazione). Modello: ``services/market_data_sync.py``.

- ``AuditorStore``: SQL sulle tabelle ``auditor_runs`` e ``auditor_results``. Si salvano solo
  le righe di ``report.privacy_rows`` (id regola, esito, severità, tipo di scope, portafoglio) e i
  conteggi: mai importi, simboli, nomi, evidenze, ``reason`` o messaggi d'eccezione (della corsa
  ``failed`` solo il **nome** dell'eccezione).
- ``AuditorNightlyService``: orchestrazione multiutente. Per ogni utente con almeno un portafoglio
  ``run_audit(AuditContext(deps, uid, run_id=..., mode="nightly"), rules, RunOptions(mode="nightly"))``
  con ``deps = build_tool_dependencies(offline=True)``: nessuna rete, nessuna quota MCP degli
  utenti (``run_tool_sync`` non passa da ``_run_bounded``). ``auditor_max_concurrency`` utenti in
  parallelo, ognuno con le regole in sequenza; durata massima della corsa e di ogni utente.
  Un utente che fallisce prima della valutazione (``ScopeSelectionError``, ``AuditToolError`` su
  ``list_portfolios``, errore del DB) non ferma gli altri.
- Lock: lock di processo + ``pg_try_advisory_xact_lock(AUDITOR_LOCK_KEY)`` su una connessione
  dedicata tenuta per tutta la corsa (come la sincronizzazione dei prezzi). Chi tiene il lock è
  l'unico che può avere una corsa viva: una riga ``running`` trovata con il lock in mano (all'avvio
  dell'app o all'avvio di una nuova corsa) è di un processo morto e diventa ``interrupted``.
- Log: run_id, durata, conteggi, id delle regole che falliscono e nomi di eccezioni; mai utenti,
  portafogli o valori.
"""

from __future__ import annotations

import logging
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Iterable, Sequence

from sqlalchemy import bindparam, text

logger = logging.getLogger(__name__)

# Chiave del lock advisory (bigint arbitrario, unico nel database; market data sync: 54_365_001).
AUDITOR_LOCK_KEY = 80_365_001
VALID_TRIGGERS = frozenset({"external", "manual"})
RUN_STATUSES = ("running", "success", "completed_with_failures", "failed", "interrupted")
# Corse che hanno valutato tutti gli utenti (o ci hanno provato fino alla fine): le sole che contano
# per lo storico mostrato agli utenti (TASK-81) e per la serie di `since`.
CONCLUDED_STATUSES = ("success", "completed_with_failures")
RESULT_STATUSES = ("pass", "fail", "skip", "error")
SCOPE_KINDS = ("portfolio", "aggregate", "instrument", "user")
SEVERITIES = ("P0", "P1", "P2")
# Corse lette all'indietro per calcolare `since`.
SINCE_HISTORY_LIMIT = 400
# Colonne di auditor_results: chiuse, nessuna può contenere testo libero.
RESULT_COLUMNS = ("portfolio_id", "rule_id", "scope_kind", "status", "severity")


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.isoformat() if hasattr(value, "isoformat") else None


def _error_type(exc: BaseException) -> str:
    """Solo il nome della classe (mai il messaggio, che può contenere dati)."""
    name = type(exc).__name__
    return name[:100] if name.isidentifier() else "Exception"


def clean_result_row(row: dict) -> dict:
    """Valida e riduce una riga di privacy_rows alle sole colonne salvabili."""
    clean = {
        "portfolio_id": int(row["portfolio_id"]),
        "rule_id": str(row["rule_id"]),
        "scope_kind": str(row["scope_kind"]),
        "status": str(row["status"]),
        "severity": str(row["severity"]),
    }
    if clean["scope_kind"] not in SCOPE_KINDS:
        raise ValueError(f"scope_kind non valido: {clean['scope_kind']}")
    if clean["status"] not in RESULT_STATUSES:
        raise ValueError(f"esito non valido: {clean['status']}")
    if clean["severity"] not in SEVERITIES:
        raise ValueError(f"severità non valida: {clean['severity']}")
    return clean


# --- store -------------------------------------------------------------------------------------


class AuditorStore:
    """Letture e scritture di auditor_runs / auditor_results (transazioni brevi)."""

    def __init__(self, engine) -> None:
        self.engine = engine

    # -- scritture --

    def create_run(self, run_uuid: str, trigger: str, app_version: str) -> int:
        with self.engine.begin() as conn:
            return int(conn.execute(
                text(
                    "insert into auditor_runs (run_uuid, status, trigger, app_version) "
                    "values (:run_uuid, 'running', :trigger, :app_version) returning id"
                ),
                {"run_uuid": run_uuid, "trigger": trigger, "app_version": app_version},
            ).scalar_one())

    _UPDATABLE = (
        "status", "finished_at", "users_total", "users_failed", "portfolios_total", "rules_total",
        "pass_count", "fail_count", "skip_count", "error_count", "deadline_exceeded", "error_type",
    )

    def update_run(self, run_id: int, **values: Any) -> None:
        unknown = set(values) - set(self._UPDATABLE)
        if unknown:
            raise ValueError(f"colonne non aggiornabili: {sorted(unknown)}")
        if not values:
            return
        assignments = ", ".join(f"{name} = :{name}" for name in values)
        with self.engine.begin() as conn:
            conn.execute(text(f"update auditor_runs set {assignments} where id = :id"), {**values, "id": run_id})

    def mark_interrupted(self) -> int:
        """Corse 'running' senza un processo vivo → 'interrupted'. Va chiamata col lock in mano."""
        with self.engine.begin() as conn:
            result = conn.execute(text(
                "update auditor_runs set status = 'interrupted', finished_at = coalesce(finished_at, now()) "
                "where status = 'running'"
            ))
            return int(result.rowcount or 0)

    def save_results(self, run_id: int, rows: Iterable[dict]) -> int:
        """Salva le righe di privacy_rows. Un portafoglio cancellato durante la corsa è ignorato."""
        params = [{"run_id": run_id, **clean_result_row(row)} for row in rows]
        if not params:
            return 0
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    "insert into auditor_results (run_id, portfolio_id, rule_id, scope_kind, status, severity) "
                    "select :run_id, p.id, :rule_id, :scope_kind, :status, :severity "
                    "from portfolios p where p.id = :portfolio_id "
                    "on conflict (run_id, portfolio_id, rule_id, scope_kind) do nothing"
                ),
                params,
            )
        return len(params)

    # -- letture --

    def list_audit_user_ids(self) -> list[str]:
        with self.engine.connect() as conn:
            rows = conn.execute(text(
                "select distinct owner_user_id from portfolios where owner_user_id is not null "
                "order by owner_user_id"
            )).scalars().all()
        return [str(r) for r in rows]

    _RUN_COLUMNS = (
        "id, run_uuid, status, trigger, app_version, started_at, finished_at, users_total, users_failed, "
        "portfolios_total, rules_total, pass_count, fail_count, skip_count, error_count, "
        "deadline_exceeded, error_type"
    )

    def _one_run(self, where: str, params: dict | None = None) -> dict | None:
        with self.engine.connect() as conn:
            row = conn.execute(
                text(f"select {self._RUN_COLUMNS} from auditor_runs where {where} "
                     "order by started_at desc, id desc limit 1"),
                params or {},
            ).mappings().first()
        return dict(row) if row else None

    def get_run(self, run_uuid: str) -> dict | None:
        return self._one_run("run_uuid = :u", {"u": run_uuid})

    def running_run(self) -> dict | None:
        return self._one_run("status = 'running'")

    def last_finished_run(self) -> dict | None:
        return self._one_run("status <> 'running'")

    def last_concluded_run(self) -> dict | None:
        return self._one_run("status in ('success', 'completed_with_failures')")

    def failing_rules(self, run_id: int) -> list[dict]:
        """[{rule_id, severity, portfolios}] delle regole in 'fail' su almeno un portafoglio."""
        return self._rules_with_status(run_id, "fail", with_severity=True)

    def error_rules(self, run_id: int) -> list[dict]:
        return self._rules_with_status(run_id, "error", with_severity=False)

    def _rules_with_status(self, run_id: int, status: str, *, with_severity: bool) -> list[dict]:
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "select rule_id, min(severity) as severity, count(distinct portfolio_id) as portfolios "
                    "from auditor_results where run_id = :run_id and status = :status "
                    "group by rule_id order by min(severity), rule_id"
                ),
                {"run_id": run_id, "status": status},
            ).mappings().all()
        out = []
        for row in rows:
            item = {"rule_id": row["rule_id"], "portfolios": int(row["portfolios"])}
            if with_severity:
                item = {"rule_id": row["rule_id"], "severity": row["severity"], "portfolios": int(row["portfolios"])}
            out.append(item)
        return out

    def fail_history(self, rule_ids: Sequence[str], *, up_to_run_id: int,
                     limit: int = SINCE_HISTORY_LIMIT) -> tuple[list[dict], set[tuple[int, str]]]:
        """Corse concluse fino a ``up_to_run_id`` (più recenti prima) e coppie (corsa, regola) in fail."""
        with self.engine.connect() as conn:
            runs = [dict(r) for r in conn.execute(
                text(
                    "select id, status, started_at from auditor_runs "
                    "where (status in ('success', 'completed_with_failures') and id <= :up_to) or id = :up_to "
                    "order by started_at desc, id desc limit :limit"
                ),
                {"up_to": up_to_run_id, "limit": limit},
            ).mappings().all()]
            if not runs or not rule_ids:
                return runs, set()
            failing = conn.execute(
                text(
                    "select distinct run_id, rule_id from auditor_results "
                    "where status = 'fail' and run_id in :run_ids and rule_id in :rule_ids"
                ).bindparams(bindparam("run_ids", expanding=True), bindparam("rule_ids", expanding=True)),
                {"run_ids": [r["id"] for r in runs], "rule_ids": list(rule_ids)},
            ).all()
        return runs, {(int(r[0]), str(r[1])) for r in failing}

    def latest_results_for_portfolios(self, portfolio_ids: Sequence[int]) -> dict:
        """Righe dell'ultima corsa conclusa per i portafogli dati (per TASK-81).

        ``{"run": {"run_id", "status", "started_at", "finished_at"} | None, "rows": [...]}``; righe
        ``{portfolio_id, rule_id, scope_kind, status, severity}`` ordinate. La proprietà dei
        portafogli va verificata dal chiamante.
        """
        run = self.last_concluded_run()
        if run is None or not portfolio_ids:
            return {"run": _run_ref(run), "rows": []}
        with self.engine.connect() as conn:
            rows = conn.execute(
                text(
                    "select portfolio_id, rule_id, scope_kind, status, severity from auditor_results "
                    "where run_id = :run_id and portfolio_id in :ids "
                    "order by portfolio_id, rule_id, scope_kind"
                ).bindparams(bindparam("ids", expanding=True)),
                {"run_id": run["id"], "ids": sorted({int(i) for i in portfolio_ids})},
            ).mappings().all()
        return {"run": _run_ref(run), "rows": [dict(r) for r in rows]}


def _run_ref(run: dict | None) -> dict | None:
    if run is None:
        return None
    return {
        "run_id": run["run_uuid"], "status": run["status"],
        "started_at": _iso(run["started_at"]), "finished_at": _iso(run["finished_at"]),
    }


def run_summary(run: dict | None, failing_rules: Sequence[dict] = ()) -> dict | None:
    """RunSummary (§6.1): solo conteggi e id di regole, nessun dato utente."""
    if not run:
        return None
    return {
        "run_id": run["run_uuid"],
        "status": run["status"],
        "trigger": run["trigger"],
        "app_version": run["app_version"],
        "started_at": _iso(run["started_at"]),
        "finished_at": _iso(run["finished_at"]),
        "portfolios_total": int(run["portfolios_total"] or 0),
        "rules_total": int(run["rules_total"] or 0),
        "users_total": int(run.get("users_total") or 0),
        "users_failed": int(run.get("users_failed") or 0),
        "deadline_exceeded": bool(run.get("deadline_exceeded")),
        "error_type": run.get("error_type"),
        "counts": {
            "pass": int(run["pass_count"] or 0),
            "fail": int(run["fail_count"] or 0),
            "skip": int(run["skip_count"] or 0),
            "error": int(run["error_count"] or 0),
        },
        "failing_rules": [dict(r) for r in failing_rules],
    }


def compute_since(rule_id: str, runs: Sequence[dict], failing: set[tuple[int, str]]) -> str | None:
    """Inizio della prima corsa della serie ininterrotta (dalla più recente) in cui la regola fallisce."""
    since = None
    for run in runs:  # più recenti prima
        if (int(run["id"]), rule_id) not in failing:
            break
        since = run["started_at"]
    return _iso(since)


# --- corsa notturna ----------------------------------------------------------------------------


@dataclass(frozen=True)
class AlreadyRunning:
    run_id: str | None = None
    status: str = "already_running"


@dataclass(frozen=True)
class RunStarted:
    run_id: str
    status: str = "running"


@dataclass
class _RunHandle:
    run_id: int          # id della riga
    run_uuid: str        # id pubblico (= report.run_id)
    trigger: str
    lock: Any


@dataclass
class UserOutcome:
    ok: bool
    counts: dict[str, int] = field(default_factory=dict)
    portfolio_ids: set[int] = field(default_factory=set)
    rows: int = 0
    deadline_exceeded: bool = False
    tool_calls: dict[str, int] = field(default_factory=dict)
    error_type: str | None = None


@dataclass
class RunOutcome:
    run_id: str
    status: str
    users_total: int = 0
    users_failed: int = 0
    portfolios_total: int = 0
    rules_total: int = 0
    counts: dict[str, int] = field(default_factory=lambda: dict.fromkeys(RESULT_STATUSES, 0))
    deadline_exceeded: bool = False
    error_type: str | None = None
    tool_calls: dict[str, int] = field(default_factory=dict)


class _SetupFailed(Exception):
    def __init__(self, error_type: str) -> None:
        super().__init__(error_type)
        self.error_type = error_type


def _default_lock_factory(engine):
    from ..market_data_sync import PgAdvisoryLock

    return lambda: PgAdvisoryLock(engine, AUDITOR_LOCK_KEY)


def _default_rules_loader():
    from .registry import load_rules

    return load_rules()


def _default_deps_factory():
    from .context import build_tool_dependencies

    return build_tool_dependencies(offline=True)


def _default_audit_user(deps, rules, user_id: str, run_uuid: str, options) -> dict:
    from .context import AuditContext
    from .runner import run_audit

    ctx = AuditContext(deps, user_id, run_id=run_uuid, mode="nightly")
    return run_audit(ctx, rules, options)


class AuditorNightlyService:
    """Una corsa alla volta, in un thread daemon; stato e storico in auditor_runs/auditor_results."""

    def __init__(
        self,
        settings,
        engine,
        *,
        store: AuditorStore | None = None,
        lock_factory: Callable[[], Any] | None = None,
        rules_loader: Callable[[], Sequence[Any]] = _default_rules_loader,
        deps_factory: Callable[[], Any] = _default_deps_factory,
        audit_user: Callable[..., dict] = _default_audit_user,
        thread_factory=threading.Thread,
        app_version: str | None = None,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.settings = settings
        self.store = store or AuditorStore(engine)
        self._lock_factory = lock_factory or _default_lock_factory(engine)
        self._rules_loader = rules_loader
        self._deps_factory = deps_factory
        self._audit_user_fn = audit_user
        self._thread_factory = thread_factory
        self._app_version = app_version
        self._monotonic = monotonic
        self._local_lock = threading.Lock()

    # -- configurazione --

    def _setting(self, name: str, default: float) -> float:
        try:
            return float(getattr(self.settings, name, default))
        except (TypeError, ValueError):
            return float(default)

    @property
    def max_concurrency(self) -> int:
        return max(1, int(self._setting("auditor_max_concurrency", 2)))

    @property
    def max_duration_s(self) -> float:
        return max(1.0, self._setting("auditor_max_duration_s", 1800.0))

    @property
    def user_max_duration_s(self) -> float:
        return max(1.0, self._setting("auditor_user_max_duration_s", 300.0))

    @property
    def rule_timeout_s(self) -> float:
        return max(0.1, self._setting("auditor_rule_timeout_s", 30.0))

    @property
    def app_version(self) -> str:
        if self._app_version:
            return self._app_version
        from ...version import APP_VERSION

        return str(APP_VERSION)

    # -- lock e avvio --

    def try_begin(self, trigger: str):
        """Lock + riga della corsa: un handle, oppure AlreadyRunning."""
        if trigger not in VALID_TRIGGERS:
            raise ValueError(f"trigger non valido: {trigger}")
        if not self._local_lock.acquire(blocking=False):
            return AlreadyRunning(run_id=self._running_run_uuid())
        lock = None
        try:
            lock = self._lock_factory()
            if not lock.acquire():
                lock = None
                self._local_lock.release()
                return AlreadyRunning(run_id=self._running_run_uuid())
            # Con il lock in mano nessun altro processo può avere una corsa viva.
            stale = self.store.mark_interrupted()
            if stale:
                logger.warning("auditor nightly: %d corse 'running' senza processo marcate interrupted", stale)
            run_uuid = uuid.uuid4().hex
            row_id = self.store.create_run(run_uuid, trigger, self.app_version)
        except Exception:
            if lock is not None:
                lock.release()
            self._local_lock.release()
            raise
        logger.info("auditor nightly started run_id=%s trigger=%s", run_uuid, trigger)
        return _RunHandle(run_id=row_id, run_uuid=run_uuid, trigger=trigger, lock=lock)

    def _running_run_uuid(self) -> str | None:
        try:
            running = self.store.running_run()
            return running["run_uuid"] if running else None
        except Exception:
            return None

    def start_in_background(self, trigger: str = "external"):
        """Lock e riga ora, la corsa in un thread daemon: RunStarted oppure AlreadyRunning."""
        handle = self.try_begin(trigger)
        if isinstance(handle, AlreadyRunning):
            return handle
        try:
            thread = self._thread_factory(
                target=self._execute, args=(handle,), name=f"auditor-nightly-{handle.run_uuid[:8]}", daemon=True,
            )
            thread.start()
        except Exception as exc:
            try:
                self.store.update_run(handle.run_id, status="failed", finished_at=_utcnow(), error_type=_error_type(exc))
            finally:
                self._finish_lock(handle)
            raise
        return RunStarted(run_id=handle.run_uuid)

    def run_now(self, trigger: str = "manual"):
        """Corsa intera in questo thread: RunOutcome oppure AlreadyRunning."""
        handle = self.try_begin(trigger)
        if isinstance(handle, AlreadyRunning):
            return handle
        return self._execute(handle)

    def mark_interrupted_runs(self) -> int:
        """All'avvio dell'app: le corse 'running' lasciate da un processo morto diventano 'interrupted'.

        Solo se il lock è libero (un altro processo vivo potrebbe avere una corsa in corso).
        """
        if not self._local_lock.acquire(blocking=False):
            return 0
        try:
            lock = self._lock_factory()
            if not lock.acquire():
                return 0
            try:
                count = self.store.mark_interrupted()
            finally:
                lock.release()
        finally:
            self._local_lock.release()
        if count:
            logger.warning("auditor nightly: %d corse interrotte marcate come tali all'avvio", count)
        return count

    def _finish_lock(self, handle: _RunHandle) -> None:
        try:
            handle.lock.release()
        finally:
            self._local_lock.release()

    # -- esecuzione --

    def _audit_one(self, handle: _RunHandle, deps, rules, user_id: str, deadline: float) -> UserOutcome:
        """Un utente: mai eccezioni verso l'orchestratore."""
        from .report import privacy_rows
        from .runner import RunOptions

        remaining = deadline - self._monotonic()
        if remaining <= 0:
            return UserOutcome(ok=False, deadline_exceeded=True, error_type="DeadlineExceeded")
        options = RunOptions(
            mode="nightly",
            rule_timeout_s=self.rule_timeout_s,
            max_duration_s=max(0.001, min(self.user_max_duration_s, remaining)),
            max_workers=1,
        )
        try:
            report = self._audit_user_fn(deps, rules, user_id, handle.run_uuid, options)
            rows = privacy_rows(report)
            saved = self.store.save_results(handle.run_id, rows)
        except Exception as exc:  # utente fallito prima della valutazione o salvataggio non riuscito
            logger.warning("auditor nightly run_id=%s: un utente non è stato valutato (%s)",
                           handle.run_uuid, _error_type(exc))
            return UserOutcome(ok=False, error_type=_error_type(exc))
        by_status = (report.get("counts") or {}).get("by_status") or {}
        stats = report.get("tool_calls") or {}
        return UserOutcome(
            ok=True,
            counts={k: int(by_status.get(k, 0)) for k in RESULT_STATUSES},
            portfolio_ids={int(s["scope"]["portfolio_id"]) for s in report.get("scopes") or []
                           if (s.get("scope") or {}).get("kind") == "portfolio"},
            rows=saved,
            deadline_exceeded=bool(report.get("deadline_exceeded")),
            tool_calls={k: int(stats.get(k, 0)) for k in ("total", "cache_hits", "errors")},
        )

    def _execute(self, handle: _RunHandle) -> RunOutcome:
        started = self._monotonic()
        deadline = started + self.max_duration_s
        outcome = RunOutcome(run_id=handle.run_uuid, status="failed")
        portfolios: set[int] = set()
        tool_calls: Counter[str] = Counter()
        user_errors: Counter[str] = Counter()
        try:
            try:
                rules = list(self._rules_loader())
                outcome.rules_total = len(rules)
                if not rules:
                    raise _SetupFailed("NoRulesLoaded")
                users = self.store.list_audit_user_ids()
                deps = self._deps_factory()
            except _SetupFailed:
                raise
            except Exception as exc:
                logger.error("auditor nightly run_id=%s: preparazione fallita (%s)", handle.run_uuid, _error_type(exc))
                raise _SetupFailed(_error_type(exc)) from exc
            outcome.users_total = len(users)
            self._save_progress(handle, outcome, portfolios)
            workers = max(1, min(self.max_concurrency, len(users) or 1))
            with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="auditor-nightly") as pool:
                futures = [pool.submit(self._audit_one, handle, deps, rules, uid, deadline) for uid in users]
                for future in as_completed(futures):
                    user = future.result()
                    if user.ok:
                        for key in RESULT_STATUSES:
                            outcome.counts[key] += user.counts.get(key, 0)
                        portfolios |= user.portfolio_ids
                        tool_calls.update(user.tool_calls)
                    else:
                        outcome.users_failed += 1
                        user_errors[user.error_type or "Exception"] += 1
                    outcome.deadline_exceeded = outcome.deadline_exceeded or user.deadline_exceeded
                    handle.lock.heartbeat()
                    self._save_progress(handle, outcome, portfolios)
            outcome.status = self._final_status(outcome)
            if outcome.status == "failed" and user_errors:
                outcome.error_type = user_errors.most_common(1)[0][0]
        except _SetupFailed as exc:
            outcome.status, outcome.error_type = "failed", exc.error_type
        except Exception as exc:  # mai lasciare una corsa 'running'
            outcome.status, outcome.error_type = "failed", _error_type(exc)
            logger.error("auditor nightly run_id=%s: errore inatteso (%s)", handle.run_uuid, outcome.error_type)
        finally:
            outcome.portfolios_total = len(portfolios)
            outcome.tool_calls = dict(tool_calls)
            try:
                self.store.update_run(
                    handle.run_id, status=outcome.status, finished_at=_utcnow(), **self._columns(outcome),
                    error_type=outcome.error_type,
                )
            except Exception as exc:
                logger.error("auditor nightly run_id=%s: esito non registrato (%s)", handle.run_uuid, _error_type(exc))
            self._finish_lock(handle)
        failing = []
        try:
            failing = [r["rule_id"] for r in self.store.failing_rules(handle.run_id)]
        except Exception:
            pass
        log = logger.info if outcome.status == "success" else logger.warning
        log(
            "auditor nightly finished run_id=%s status=%s duration=%.1fs users=%d users_failed=%d portfolios=%d "
            "rules=%d pass=%d fail=%d skip=%d error=%d deadline_exceeded=%s tool_calls=%d tool_errors=%d "
            "failing_rules=%s%s",
            handle.run_uuid, outcome.status, self._monotonic() - started, outcome.users_total, outcome.users_failed,
            outcome.portfolios_total, outcome.rules_total, outcome.counts["pass"], outcome.counts["fail"],
            outcome.counts["skip"], outcome.counts["error"], outcome.deadline_exceeded,
            tool_calls.get("total", 0), tool_calls.get("errors", 0), ",".join(failing) or "-",
            f" error_type={outcome.error_type}" if outcome.error_type else "",
        )
        return outcome

    @staticmethod
    def _final_status(outcome: RunOutcome) -> str:
        if outcome.users_total and outcome.users_failed == outcome.users_total:
            return "failed"
        if (outcome.counts["fail"] or outcome.counts["error"] or outcome.users_failed
                or outcome.deadline_exceeded):
            return "completed_with_failures"
        return "success"

    @staticmethod
    def _columns(outcome: RunOutcome) -> dict[str, Any]:
        return {
            "users_total": outcome.users_total,
            "users_failed": outcome.users_failed,
            "portfolios_total": outcome.portfolios_total,
            "rules_total": outcome.rules_total,
            "pass_count": outcome.counts["pass"],
            "fail_count": outcome.counts["fail"],
            "skip_count": outcome.counts["skip"],
            "error_count": outcome.counts["error"],
            "deadline_exceeded": outcome.deadline_exceeded,
        }

    def _save_progress(self, handle: _RunHandle, outcome: RunOutcome, portfolios: set[int]) -> None:
        try:
            columns = self._columns(outcome)
            columns["portfolios_total"] = len(portfolios)
            self.store.update_run(handle.run_id, **columns)
        except Exception as exc:
            logger.warning("auditor nightly run_id=%s: avanzamento non salvato (%s)", handle.run_uuid, _error_type(exc))

    # -- letture per gli endpoint --

    def _summary(self, run: dict | None) -> dict | None:
        if not run:
            return None
        return run_summary(run, self.store.failing_rules(run["id"]))

    def status_payload(self) -> dict:
        """GET /api/internal/auditor/run/status: {running, last_run} (solo conteggi e id di regole)."""
        return {
            "running": self._summary(self.store.running_run()),
            "last_run": self._summary(self.store.last_finished_run()),
        }

    def admin_latest(self, rules: Sequence[Any] | None = None) -> dict:
        """GET /api/admin/auditor/latest: ultima corsa finita, regole che falliscono, da quando."""
        run = self.store.last_finished_run()
        if run is None:
            return {"run": None, "failing": [], "errors": []}
        failing = self.store.failing_rules(run["id"])
        errors = self.store.error_rules(run["id"])
        if rules is None:
            try:
                rules = self._rules_loader()
            except Exception as exc:
                logger.warning("auditor admin: registro delle regole non disponibile (%s)", _error_type(exc))
                rules = []
        by_id = {r.id: r for r in rules}
        runs, history = self.store.fail_history([f["rule_id"] for f in failing], up_to_run_id=run["id"])
        items = []
        for item in failing:
            rule = by_id.get(item["rule_id"])
            items.append({
                "rule_id": item["rule_id"],
                "title": rule.title if rule else item["rule_id"],
                "area": rule.area if rule else None,
                "severity": item["severity"],
                "portfolios_failing": item["portfolios"],
                "since": compute_since(item["rule_id"], runs, history) or _iso(run["started_at"]),
            })
        return {"run": run_summary(run, failing), "failing": items, "errors": errors}


def launch_interrupted_check(service: AuditorNightlyService, *, thread_factory=threading.Thread):
    """All'avvio dell'app, in un thread daemon (l'avvio non aspetta il DB): corse interrotte → 'interrupted'."""

    def work() -> None:
        try:
            service.mark_interrupted_runs()
        except Exception as exc:
            logger.warning("auditor nightly: controllo delle corse interrotte fallito (%s)", _error_type(exc))

    thread = thread_factory(target=work, name="auditor-interrupted-check", daemon=True)
    thread.start()
    return thread
