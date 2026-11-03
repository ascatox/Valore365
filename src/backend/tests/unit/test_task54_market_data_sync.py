"""TASK-54: sincronizzazione affidabile dei dati di mercato.

Nessun database né rete: repository, servizi prezzi/storico e lock sono
fake in memoria; il lock condiviso simula pg_try_advisory_xact_lock fra due
processi.
"""

import threading
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import yaml
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_internal import register_internal_routes
from app.mcp_server import tools as mcp_tools
from app.mcp_server.freshness import FRESHNESS_TOOLS
from app.models import PriceRefreshItem, PriceRefreshResponse
from app.repository import PricingAsset
from app.scheduler import PriceRefreshScheduler
from app.services import market_data_sync as mds
from app.services.historical_service import DailyBarsJobResult, FxRatesJobResult
from app.services.market_hours import last_completed_session_close

REPO_ROOT = Path(__file__).resolve().parents[4]

VWCE = PricingAsset(asset_id=1, symbol="VWCE", provider_symbol="VWCE.MI", market_symbol="VWCE.MI")
AAPL = PricingAsset(asset_id=2, symbol="AAPL", provider_symbol="AAPL", market_symbol="AAPL")
ISIN_ONLY = PricingAsset(asset_id=3, symbol="", provider_symbol="IE00B4L5Y983", market_symbol=None)


def _utc(text: str) -> datetime:
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


# --- fakes --------------------------------------------------------------------


class FakeSyncRepo:
    """In-memory market_data_sync_runs / market_data_asset_sync + the reads the sync needs."""

    def __init__(self, assets, latest=None, fx_pairs=(), clock=None) -> None:
        self.assets = list(assets)
        self.latest = dict(latest or {})
        self.fx_pairs = list(fx_pairs)
        self.runs: list[dict] = []
        self.asset_state: dict[int, dict] = {}
        self.clock = clock or (lambda: datetime.now(UTC))

    def get_held_assets_for_daily_bars(self, provider):
        return list(self.assets)

    def get_latest_daily_bars(self, asset_ids):
        return {aid: self.latest[aid] for aid in asset_ids if aid in self.latest}

    def get_fx_pairs_in_use(self):
        return list(self.fx_pairs)

    def create_market_data_sync_run(self, trigger):
        for run in self.runs:
            if run["status"] == "running":
                run.update(status="failed", finished_at=self.clock(), error="interrotta")
        run = {
            "id": len(self.runs) + 1, "trigger": trigger, "status": "running", "started_at": self.clock(),
            "finished_at": None, "steps": [], "assets_requested": 0, "assets_updated": 0, "assets_failed": 0,
            "error": None,
        }
        self.runs.append(run)
        return run["id"]

    def update_market_data_sync_run(self, run_id, *, steps, **fields):
        run = self.runs[run_id - 1]
        run["steps"] = list(steps)
        for key, value in fields.items():
            if value is not None:
                run[key] = value

    def get_market_data_sync_overview(self):
        def latest(rows, key):
            rows = [r for r in rows if r.get(key) is not None]
            return dict(max(rows, key=lambda r: (r[key], r["id"]))) if rows else None

        return {
            "last_run": latest(self.runs, "started_at"),
            "last_success": latest([r for r in self.runs if r["status"] == "success"], "finished_at"),
            "last_finished": latest([r for r in self.runs if r["status"] != "running"], "finished_at"),
            "running": latest([r for r in self.runs if r["status"] == "running"], "started_at"),
        }

    def upsert_market_data_asset_sync(self, rows):
        for row in rows:
            state = self.asset_state.setdefault(row["asset_id"], {})
            for key in ("last_success_at", "last_bar_date", "last_tick_at"):
                if row.get(key) is not None:
                    state[key] = row[key]
            if row.get("last_error") is not None:
                state["last_error"], state["last_error_at"] = row["last_error"], row.get("last_error_at")
            elif row.get("last_success_at") is not None:
                state["last_error"] = state["last_error_at"] = None

    def get_market_data_asset_sync(self, asset_ids):
        return {aid: dict(self.asset_state[aid]) for aid in asset_ids if aid in self.asset_state}

    @property
    def last_successful_price_sync(self):
        success = self.get_market_data_sync_overview()["last_success"]
        return success["finished_at"] if success else None


class FakePricing:
    def __init__(self, fail=()) -> None:
        self.fail = set(fail)
        self.calls = []

    def refresh_prices(self, *, assets):
        self.calls.append([a.provider_symbol for a in assets])
        ok = [a for a in assets if a.provider_symbol not in self.fail]
        return PriceRefreshResponse(
            provider="yfinance", requested_assets=len(assets), refreshed_assets=len(ok),
            failed_assets=len(assets) - len(ok),
            items=[
                PriceRefreshItem(asset_id=a.asset_id, symbol=a.symbol, provider_symbol=a.provider_symbol,
                                 price=100.0, ts=_utc("2026-11-03T21:00:00"))
                for a in ok
            ],
            errors=[f"{s}: timeout" for s in sorted(self.fail)],
        )


class FakeHistorical:
    """Writes the configured last bar per symbol into the fake repo."""

    def __init__(self, repo, bars=None, fail=(), fx_fail=(), raise_on_bars=None, gate=None) -> None:
        self.repo = repo
        self.bars = dict(bars or {})
        self.fail = set(fail)
        self.fx_fail = set(fx_fail)
        self.raise_on_bars = raise_on_bars
        self.gate = gate
        self.bar_calls = []
        self.fx_calls = []

    def refresh_recent_daily_bars(self, *, days, now, assets):
        self.bar_calls.append({"days": days, "now": now, "symbols": [a.provider_symbol for a in assets]})
        if self.gate is not None:
            self.gate.wait(5)
        if self.raise_on_bars:
            raise self.raise_on_bars
        result = DailyBarsJobResult(requested=len(assets))
        for asset in assets:
            if asset.provider_symbol in self.fail:
                result.failed.append(asset.provider_symbol)
                continue
            day = self.bars.get(asset.provider_symbol)
            if day is not None:
                self.repo.latest[asset.asset_id] = (day, 100.0)
                result.updated.append(asset.provider_symbol)
            else:
                result.no_new_bar.append(asset.provider_symbol)
        return result

    def refresh_recent_fx_rates(self, pairs, *, days, now):
        self.fx_calls.append({"pairs": list(pairs), "days": days})
        result = FxRatesJobResult(requested=len(pairs))
        for from_ccy, to_ccy in pairs:
            label = f"{from_ccy}/{to_ccy}"
            if label in self.fx_fail:
                result.failed.append(label)
                result.errors.append(f"{label}: timeout")
            else:
                result.updated.append(label)
                result.last_dates[label] = now.date()
        return result


class SharedAdvisoryLock:
    """pg_try_advisory_xact_lock shared by several 'processes' (service instances)."""

    def __init__(self) -> None:
        self.held = False
        self._guard = threading.Lock()
        self.acquired = 0

    def factory(self):
        shared = self

        class _Lock:
            def acquire(self):
                with shared._guard:
                    if shared.held:
                        return False
                    shared.held = True
                    shared.acquired += 1
                    return True

            def heartbeat(self):
                pass

            def release(self):
                shared.held = False

        return _Lock()


def _settings(**overrides):
    values = dict(
        finance_provider="yfinance",
        market_data_sync_grace_minutes=60,
        market_data_sync_max_lookback_days=30,
        market_data_sync_on_startup=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


class SyncThread:
    """Thread factory that runs the target inline (deterministic tests)."""

    def __init__(self, target, args=(), name=None, daemon=None) -> None:
        self.target, self.args, self.started = target, args, False

    def start(self):
        self.started = True
        self.target(*self.args)


def _service(repo, *, pricing=None, historical=None, lock=None, clock=None, thread_factory=SyncThread, **settings):
    lock = lock or SharedAdvisoryLock()
    return mds.MarketDataSyncService(
        _settings(**settings), repo, pricing or FakePricing(), historical or FakeHistorical(repo),
        lock_factory=lock.factory, thread_factory=thread_factory, clock=clock or repo.clock,
    )


# Tuesday 03/11/2026, 23:00 UTC: Milan (16:30 UTC) and NYSE (21:00 UTC) closed
# their 03/11 sessions more than the 60 minutes of grace ago.
TUESDAY_NIGHT = _utc("2026-11-03T23:00:00")


def _fresh_repo(now=TUESDAY_NIGHT, latest=None, assets=(VWCE, AAPL), fx_pairs=(("USD", "EUR"),)):
    clock = Clock(now)
    return FakeSyncRepo(assets, latest=latest or {1: (date(2026, 11, 2), 99.0), 2: (date(2026, 11, 2), 99.0)},
                        fx_pairs=fx_pairs, clock=clock), clock


# --- calendars ------------------------------------------------------------------


def test_last_completed_session_close_skips_weekends_and_holidays():
    # Monday morning: the last completed Milan session is Friday's.
    assert last_completed_session_close("VWCE.MI", _utc("2026-11-02T08:00:00")) == _utc("2026-10-30T16:30:00")
    assert last_completed_session_close("VWCE.MI", _utc("2026-11-02T17:00:00")) == _utc("2026-11-02T16:30:00")
    # NYSE: Thanksgiving 26/11/2026 is not a session.
    assert last_completed_session_close("AAPL", _utc("2026-11-27T10:00:00")) == _utc("2026-11-25T21:00:00")
    # Xetra over Christmas 2026 (24, 25 holidays, 26 Saturday): Wednesday 23/12.
    assert last_completed_session_close("XAD1.DE", _utc("2026-12-27T12:00:00")) == _utc("2026-12-23T16:30:00")


# --- runs: status and last_successful_price_sync ---------------------------------


def test_success_run_advances_last_successful_price_sync_and_asset_state():
    repo, clock = _fresh_repo()
    historical = FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 3), "AAPL": date(2026, 11, 3)})
    svc = _service(repo, historical=historical)

    outcome = svc.run_sync("external")

    assert outcome.status == "success"
    assert [s["name"] for s in outcome.steps] == ["quotes", "bars", "fx"]
    assert all(s["status"] == "ok" for s in outcome.steps)
    assert (outcome.assets_requested, outcome.assets_updated, outcome.assets_failed) == (2, 2, 0)
    assert repo.last_successful_price_sync == TUESDAY_NIGHT
    assert repo.runs[0]["trigger"] == "external" and repo.runs[0]["status"] == "success"
    assert repo.asset_state[1]["last_bar_date"] == date(2026, 11, 3)
    assert repo.asset_state[1]["last_tick_at"] == _utc("2026-11-03T21:00:00")
    assert repo.asset_state[1]["last_success_at"] is not None
    # Window from the oldest last bar (02/11), never under the minimum.
    assert historical.bar_calls[0]["days"] == mds.MIN_LOOKBACK_DAYS
    assert historical.fx_calls[0]["pairs"] == [("USD", "EUR")]
    assert not svc.needs_sync(TUESDAY_NIGHT + timedelta(minutes=5))


def test_partial_run_does_not_advance_last_successful_price_sync():
    repo, clock = _fresh_repo()
    svc = _service(repo, historical=FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 3), "AAPL": date(2026, 11, 3)}))
    assert svc.run_sync("external").status == "success"
    first_success = repo.last_successful_price_sync

    clock.now = _utc("2026-11-04T23:00:00")
    # AAPL: the provider has no 04/11 bar yet; VWCE ok.
    svc.historical_service = FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 4)})
    outcome = svc.run_sync("scheduler")

    assert outcome.status == "partial"
    assert (outcome.assets_updated, outcome.assets_failed) == (1, 1)
    assert "AAPL" in outcome.error
    assert repo.last_successful_price_sync == first_success
    # Per-asset state advances anyway.
    assert repo.asset_state[1]["last_bar_date"] == date(2026, 11, 4)
    assert repo.asset_state[2]["last_error"].startswith("barre:")
    assert svc.needs_sync(clock.now)


def test_failed_runs_do_not_advance_last_successful_price_sync():
    repo, clock = _fresh_repo()
    # Provider down for every asset: no data at all.
    svc = _service(repo, historical=FakeHistorical(repo, fail={"VWCE.MI", "AAPL"}))
    assert svc.run_sync("startup").status == "failed"
    # A step that raises is a failed run too, even if the others are fine.
    svc.historical_service = FakeHistorical(repo, raise_on_bars=RuntimeError("db gone"))
    outcome = svc.run_sync("manual")
    assert outcome.status == "failed"
    bars = next(s for s in outcome.steps if s["name"] == "bars")
    assert bars["status"] == "failed" and "db gone" in bars["errors"][0]
    assert repo.last_successful_price_sync is None
    assert [r["status"] for r in repo.runs] == ["failed", "failed"]
    assert all(r["finished_at"] is not None for r in repo.runs)


def test_fx_pair_failure_makes_the_run_partial_and_quotes_are_best_effort():
    repo, _ = _fresh_repo(fx_pairs=(("USD", "EUR"), ("GBP", "EUR")))
    historical = FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 3), "AAPL": date(2026, 11, 3)}, fx_fail={"GBP/EUR"})
    svc = _service(repo, pricing=FakePricing(fail={"AAPL"}), historical=historical)
    outcome = svc.run_sync("external")
    steps = {s["name"]: s for s in outcome.steps}
    assert steps["fx"]["status"] == "partial"
    assert steps["quotes"]["status"] == "partial" and steps["quotes"]["blocking"] is False
    assert outcome.status == "partial"
    assert repo.last_successful_price_sync is None

    # Quote failures alone (bars complete) do not block success.
    repo2, _ = _fresh_repo()
    svc2 = _service(repo2, pricing=FakePricing(fail={"AAPL"}),
                    historical=FakeHistorical(repo2, bars={"VWCE.MI": date(2026, 11, 3), "AAPL": date(2026, 11, 3)}))
    assert svc2.run_sync("external").status == "success"
    assert repo2.asset_state[2]["last_bar_date"] == date(2026, 11, 3)


def test_isin_only_assets_are_skipped_not_counted_as_missed():
    repo, _ = _fresh_repo(assets=(VWCE, ISIN_ONLY), latest={1: (date(2026, 11, 2), 1.0)})
    pricing = FakePricing()
    svc = _service(repo, pricing=pricing, historical=FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 3)}))
    outcome = svc.run_sync("external")
    assert outcome.status == "success"
    assert outcome.assets_requested == 2 and outcome.assets_updated == 1
    assert pricing.calls == [["VWCE.MI"]]
    assert svc.status_payload()["skipped_symbols"] == ["IE00B4L5Y983"]


def test_weekend_and_holidays_are_not_missed_sessions():
    # Saturday: Friday's bars are complete, a sync is a success and not needed again.
    repo, clock = _fresh_repo(now=_utc("2026-11-07T10:00:00"),
                              latest={1: (date(2026, 11, 6), 1.0), 2: (date(2026, 11, 6), 1.0)})
    svc = _service(repo, historical=FakeHistorical(repo))  # provider returns nothing new
    assert svc.run_sync("external").status == "success"
    clock.now = _utc("2026-11-09T08:00:00")  # Monday before the open
    assert not svc.needs_sync()

    # Xetra over Christmas: bar of Wednesday 23/12 is complete on Sunday 27/12.
    xad1 = PricingAsset(asset_id=5, symbol="XAD1", provider_symbol="XAD1.DE", market_symbol="XAD1.DE")
    repo2, clock2 = _fresh_repo(now=_utc("2026-12-27T12:00:00"), assets=(xad1,), latest={5: (date(2026, 12, 23), 1.0)})
    svc2 = _service(repo2, historical=FakeHistorical(repo2))
    assert svc2.run_sync("startup").status == "success"
    assert svc2.lagging_assets() == []
    clock2.now = _utc("2026-12-28T18:00:00")  # Monday after the close: 28/12 is due
    assert [r["symbol"] for r in svc2.lagging_assets()] == ["XAD1"]


# --- needs_sync -------------------------------------------------------------------


def test_needs_sync_without_any_success_run():
    repo, _ = _fresh_repo()
    assert _service(repo).needs_sync()


def test_needs_sync_compares_the_last_success_with_the_latest_close_plus_grace():
    repo, clock = _fresh_repo(latest={1: (date(2026, 11, 3), 1.0), 2: (date(2026, 11, 3), 1.0)})
    svc = _service(repo)
    # Success at 21:40 UTC: NYSE closed at 21:00, so 03/11 was not yet due (grace 60).
    clock.now = _utc("2026-11-03T21:40:00")
    repo.latest = {1: (date(2026, 11, 3), 1.0), 2: (date(2026, 11, 2), 1.0)}
    assert svc.run_sync("external").status == "success"
    # 21:50: the NYSE session is not complete yet (close + grace = 22:00).
    assert not svc.needs_sync(_utc("2026-11-03T21:50:00"))
    # Next morning: the success predates the 03/11 NYSE close + grace -> sync needed.
    assert svc.needs_sync(_utc("2026-11-04T06:15:00"))


def test_needs_sync_for_an_asset_behind_its_own_session_until_it_was_attempted():
    repo, clock = _fresh_repo(latest={1: (date(2026, 11, 3), 1.0), 2: (date(2026, 11, 3), 1.0)})
    svc = _service(repo)
    assert svc.run_sync("external").status == "success"
    # A new asset with no bars is added after the success.
    new = PricingAsset(asset_id=9, symbol="MSFT", provider_symbol="MSFT", market_symbol="MSFT")
    repo.assets.append(new)
    clock.now = TUESDAY_NIGHT + timedelta(minutes=30)
    assert svc.needs_sync()
    # Attempted after its last session closed (+ grace): not needed again.
    repo.asset_state[9] = {"last_error": "barre: nessuna", "last_error_at": clock.now}
    assert not svc.needs_sync()


def test_needs_sync_startup_cooldown_after_a_recent_run():
    repo, clock = _fresh_repo()
    svc = _service(repo, historical=FakeHistorical(repo, fail={"VWCE.MI", "AAPL"}))
    assert svc.run_sync("external").status == "failed"
    clock.now = TUESDAY_NIGHT + timedelta(minutes=10)
    assert svc.needs_sync()
    assert not svc.needs_sync(retry_cooldown_minutes=mds.STARTUP_RETRY_COOLDOWN_MINUTES)
    clock.now = TUESDAY_NIGHT + timedelta(minutes=mds.STARTUP_RETRY_COOLDOWN_MINUTES + 1)
    assert svc.needs_sync(retry_cooldown_minutes=mds.STARTUP_RETRY_COOLDOWN_MINUTES)


# --- concurrency ---------------------------------------------------------------------


def test_two_simultaneous_triggers_run_a_single_sync():
    repo, _ = _fresh_repo()
    gate = threading.Event()
    lock = SharedAdvisoryLock()
    threads = []

    def real_thread(**kwargs):
        thread = threading.Thread(**kwargs)
        threads.append(thread)
        return thread

    historical = FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 3), "AAPL": date(2026, 11, 3)}, gate=gate)
    process_a = _service(repo, historical=historical, lock=lock, thread_factory=real_thread)
    # A second process (another instance, the startup catch-up) with its own in-process lock.
    process_b = _service(repo, historical=historical, lock=lock)

    started = process_a.start_in_background("external")
    assert isinstance(started, mds.SyncStarted) and started.run_id == 1

    second_same_process = process_a.start_in_background("external")
    second_other_process = process_b.run_sync("startup")
    assert isinstance(second_same_process, mds.AlreadyRunning) and second_same_process.run_id == 1
    assert isinstance(second_other_process, mds.AlreadyRunning) and second_other_process.run_id == 1

    gate.set()
    for thread in threads:
        thread.join(5)
    assert len(repo.runs) == 1 and repo.runs[0]["status"] == "success"
    assert lock.acquired == 1 and not lock.held
    assert len(historical.bar_calls) == 1
    # Lock released: the next trigger runs.
    assert isinstance(process_b.run_sync("manual"), mds.SyncOutcome)


def test_lock_is_released_when_a_run_crashes():
    repo, _ = _fresh_repo()
    lock = SharedAdvisoryLock()
    svc = _service(repo, lock=lock)
    svc.repository.get_held_assets_for_daily_bars = MagicMock(side_effect=RuntimeError("boom"))
    outcome = svc.run_sync("external")
    assert outcome.status == "failed" and "boom" in outcome.error
    assert not lock.held and repo.runs[0]["status"] == "failed"


def test_steps_registry_is_extensible():
    repo, _ = _fresh_repo()
    svc = _service(repo, historical=FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 3), "AAPL": date(2026, 11, 3)}))
    seen = []
    svc.register_step(mds.SyncStep("etf_enrichment", lambda s, ctx: seen.append(len(ctx.assets)) or {"status": "ok", "updated": 2}))
    with pytest.raises(ValueError):
        svc.register_step(mds.SyncStep("bars", lambda s, ctx: {}))
    outcome = svc.run_sync("manual")
    assert [s["name"] for s in outcome.steps] == ["quotes", "bars", "fx", "etf_enrichment"]
    assert seen == [2] and outcome.status == "success"


def test_pg_advisory_lock_uses_a_transaction_lock_on_a_dedicated_connection():
    executed = []

    class _Conn:
        def __init__(self, granted):
            self.granted, self.closed = granted, False
            self.trans = MagicMock(is_active=True)

        def begin(self):
            return self.trans

        def execute(self, statement, params=None):
            executed.append(str(statement))
            return MagicMock(scalar=lambda: self.granted)

        def close(self):
            self.closed = True

    denied = _Conn(False)
    lock = mds.PgAdvisoryLock(SimpleNamespace(connect=lambda: denied))
    assert lock.acquire() is False and denied.closed and denied.trans.rollback.called
    assert "pg_try_advisory_xact_lock" in executed[0]

    granted = _Conn(True)
    lock = mds.PgAdvisoryLock(SimpleNamespace(connect=lambda: granted))
    assert lock.acquire() is True and not granted.closed
    lock.heartbeat()
    lock.release()
    assert granted.closed and granted.trans.rollback.called


# --- startup catch-up and scheduler ---------------------------------------------------


def test_startup_catch_up_runs_in_background_only_when_needed():
    service = MagicMock()
    service.needs_sync.return_value = True
    thread = mds.launch_startup_catch_up(service, _settings(), thread_factory=SyncThread)
    assert thread.started
    service.run_sync.assert_called_once_with("startup")
    assert service.needs_sync.call_args.kwargs["retry_cooldown_minutes"] == mds.STARTUP_RETRY_COOLDOWN_MINUTES

    service = MagicMock()
    service.needs_sync.return_value = False
    mds.launch_startup_catch_up(service, _settings(), thread_factory=SyncThread)
    service.run_sync.assert_not_called()

    service = MagicMock()
    assert mds.launch_startup_catch_up(service, _settings(market_data_sync_on_startup=False)) is None
    service.needs_sync.assert_not_called()


def test_startup_catch_up_never_blocks_nor_raises():
    service = MagicMock()
    service.needs_sync.side_effect = RuntimeError("db down")
    created = []

    def factory(**kwargs):
        thread = threading.Thread(**kwargs)
        created.append(kwargs)
        return thread

    thread = mds.launch_startup_catch_up(service, _settings(), thread_factory=factory)
    thread.join(5)
    assert created[0]["daemon"] is True
    service.run_sync.assert_not_called()


def test_app_lifespan_launches_the_catch_up(monkeypatch):
    import app.main as api_main

    calls = []
    monkeypatch.setattr(api_main, "launch_startup_catch_up", lambda svc, settings: calls.append(svc))
    monkeypatch.setattr(api_main, "_apply_pending_migrations", lambda: None)
    monkeypatch.setattr(api_main.scheduler, "start", lambda: None)
    monkeypatch.setattr(api_main.scheduler, "shutdown", lambda: None)
    with TestClient(api_main.app):
        pass
    assert calls == [api_main.market_data_sync]


def test_scheduler_daily_job_goes_through_run_sync():
    sync = MagicMock()
    sync.run_sync.return_value = mds.SyncOutcome(run_id=7, status="success", steps=[])
    historical = MagicMock()
    settings = SimpleNamespace(price_scheduler_enabled=False, daily_bars_scheduler_enabled=True, daily_bars_lookback_days=10)
    scheduler = PriceRefreshScheduler(settings, MagicMock(), None, historical, MagicMock(), market_data_sync=sync)
    scheduler._run_daily_bars()
    sync.run_sync.assert_called_once_with("scheduler")
    historical.refresh_recent_daily_bars.assert_not_called()


# --- internal endpoints -----------------------------------------------------------------

TOKEN = "s3cret-token-for-tests-0123456789"


def _internal_client(service, **settings):
    values = dict(
        market_data_sync_token=TOKEN, trusted_proxy_ips_list=[],
        market_data_sync_rate_limit_requests=10, market_data_sync_status_rate_limit_requests=240,
        market_data_sync_auth_failure_limit_requests=30, market_data_sync_rate_limit_window_seconds=3600,
    )
    values.update(settings)
    app = FastAPI()
    router = APIRouter()
    register_internal_routes(router, settings=SimpleNamespace(**values), market_data_sync=service)
    app.include_router(router, prefix="/api")
    return TestClient(app), app


def _auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_internal_endpoints_disabled_without_token():
    repo, _ = _fresh_repo()
    client, _ = _internal_client(_service(repo), market_data_sync_token="")
    assert client.post("/api/internal/market-data/sync", headers=_auth()).status_code == 404
    assert client.get("/api/internal/market-data/sync/status", headers=_auth()).status_code == 404
    assert repo.runs == []


def test_internal_endpoints_reject_missing_or_wrong_token():
    repo, _ = _fresh_repo()
    client, _ = _internal_client(_service(repo))
    assert client.post("/api/internal/market-data/sync").status_code == 401
    response = client.post("/api/internal/market-data/sync", headers=_auth("wrong"))
    assert response.status_code == 401 and response.headers["WWW-Authenticate"] == "Bearer"
    assert client.post("/api/internal/market-data/sync", headers={"Authorization": TOKEN}).status_code == 401
    assert client.get("/api/internal/market-data/sync/status", headers=_auth("wrong")).status_code == 401
    assert repo.runs == []


def test_internal_sync_starts_a_run_then_reports_up_to_date_or_already_running():
    repo, clock = _fresh_repo()
    lock = SharedAdvisoryLock()
    historical = FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 3), "AAPL": date(2026, 11, 3)})
    client, _ = _internal_client(_service(repo, historical=historical, lock=lock))

    started = client.post("/api/internal/market-data/sync", headers=_auth())
    assert started.status_code == 202
    assert started.json() == {"run_id": 1, "status": "running"}
    assert repo.runs[0]["trigger"] == "external" and repo.runs[0]["status"] == "success"

    up_to_date = client.post("/api/internal/market-data/sync", headers=_auth())
    assert up_to_date.status_code == 200
    assert up_to_date.json() == {"status": "up_to_date", "last_successful_price_sync": TUESDAY_NIGHT.isoformat()}

    # force=true runs anyway; while another process holds the lock -> 409.
    repo.runs.append({**repo.runs[0], "id": 2, "status": "running", "finished_at": None})
    lock.held = True
    conflict = client.post("/api/internal/market-data/sync?force=true", headers=_auth())
    assert conflict.status_code == 409
    assert conflict.json()["code"] == "already_running" and conflict.json()["run_id"] == 2
    lock.held = False
    repo.runs[1]["status"] = "failed"
    repo.runs[1]["finished_at"] = clock.now
    forced = client.post("/api/internal/market-data/sync?force=true", headers=_auth())
    assert forced.status_code == 202 and forced.json()["run_id"] == 3


def test_internal_status_lists_last_run_success_and_lagging_symbols_only():
    repo, _ = _fresh_repo()
    svc = _service(repo, historical=FakeHistorical(repo, bars={"VWCE.MI": date(2026, 11, 3)}))
    svc.run_sync("external")
    client, _ = _internal_client(svc)
    body = client.get("/api/internal/market-data/sync/status", headers=_auth()).json()
    assert body["last_run"]["status"] == "partial" and body["last_run"]["run_id"] == 1
    assert body["last_successful_price_sync"] is None
    assert body["needs_sync"] is True
    assert body["held_assets"] == 2
    assert [row["symbol"] for row in body["lagging"]] == ["AAPL"]
    assert body["lagging"][0]["last_bar_date"] == "2026-11-02"
    assert set(body["lagging"][0]) == {"symbol", "last_bar_date", "missed_sessions", "last_attempt_at", "last_error"}
    assert {s["name"] for s in body["last_run"]["steps"]} == {"quotes", "bars", "fx"}


def test_internal_endpoints_rate_limits():
    repo, _ = _fresh_repo()
    client, _ = _internal_client(
        _service(repo), market_data_sync_rate_limit_requests=2, market_data_sync_auth_failure_limit_requests=3,
    )
    codes = [client.post("/api/internal/market-data/sync", headers=_auth()).status_code for _ in range(3)]
    assert codes[:2] != [429, 429] and codes[2] == 429
    limited = client.post("/api/internal/market-data/sync", headers=_auth())
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    # Status has its own budget.
    assert client.get("/api/internal/market-data/sync/status", headers=_auth()).status_code == 200
    # Failed auth is limited separately and never blocks the valid token's status calls.
    bad = [client.get("/api/internal/market-data/sync/status", headers=_auth("x")).status_code for _ in range(4)]
    assert bad == [401, 401, 401, 429]
    assert client.get("/api/internal/market-data/sync/status", headers=_auth()).status_code == 200


def test_internal_endpoints_are_not_in_the_openapi_schema():
    repo, _ = _fresh_repo()
    _, app = _internal_client(_service(repo))
    assert not any("internal" in path for path in app.openapi()["paths"])

    import app.main as api_main

    assert not any("internal" in path for path in api_main.app.openapi().get("paths", {}))


def test_main_app_internal_endpoint_is_disabled_by_default(monkeypatch):
    import app.main as api_main

    client = TestClient(api_main.app)
    assert api_main.settings.market_data_sync_token == ""
    response = client.post("/api/internal/market-data/sync", headers=_auth())
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
    assert client.get("/api/internal/market-data/sync/status").status_code == 404
    # Registered on the real app: with a token configured it answers 401, not 404.
    monkeypatch.setattr(api_main.settings, "market_data_sync_token", TOKEN)
    assert client.post("/api/internal/market-data/sync", headers=_auth("wrong")).status_code == 401


# --- MCP data freshness ---------------------------------------------------------------------

OWNER = "user_owner"


class FreshnessRepo:
    def __init__(self, *, overview=None, raise_overview=False):
        self.overview = overview
        self.raise_overview = raise_overview
        self.positions_calls = 0

    def resolve_portfolio_scope(self, portfolio_ids, user_id):
        ids = sorted(portfolio_ids)
        if user_id != OWNER or not set(ids) <= {1, 2}:
            raise ValueError("Portfolio non trovato")
        return SimpleNamespace(portfolio_ids=tuple(ids), base_currency="EUR")

    def _summary(self):
        return SimpleNamespace(
            market_value=1000.0, cost_basis=900.0, unrealized_pl=100.0, unrealized_pl_pct=11.11,
            day_change=5.0, day_change_pct=0.5, cash_balance=10.0, base_currency="EUR",
            stale_price_symbols=["XAD1"],
        )

    def get_summary(self, portfolio_id, user_id):
        self.get_positions(portfolio_id, user_id)
        return self._summary()

    def get_summary_multi(self, ids, user_id):
        return self._summary()

    def _positions(self):
        return [
            SimpleNamespace(asset_id=1, symbol="VWCE", quantity=10, price_stale=False, stale_reason=None,
                            price_date=date(2026, 11, 3), last_price_at=_utc("2026-11-03T16:35:00")),
            SimpleNamespace(asset_id=5, symbol="XAD1", quantity=2, price_stale=True,
                            stale_reason="ultima quotazione del 30/10, 2 sedute fa",
                            price_date=date(2026, 10, 30), last_price_at=None),
            SimpleNamespace(asset_id=6, symbol="SOLD", quantity=0, price_stale=True, stale_reason="x",
                            price_date=None, last_price_at=None),
        ]

    def get_positions(self, portfolio_id, user_id):
        self.positions_calls += 1
        return self._positions()

    def get_positions_multi(self, ids, user_id):
        return self._positions()

    def get_market_data_sync_overview(self):
        if self.raise_overview:
            raise RuntimeError('relation "market_data_sync_runs" does not exist')
        return self.overview

    def get_market_data_asset_sync(self, asset_ids):
        return {5: {"last_success_at": None, "last_error": "barre: il provider non ha la barra dell'ultima seduta conclusa"}}


OVERVIEW = {
    "last_run": {"id": 4, "status": "partial", "finished_at": _utc("2026-11-03T22:45:00")},
    "last_success": {"id": 3, "status": "success", "finished_at": _utc("2026-11-02T22:44:00")},
    "running": None,
}


def _deps(repo):
    return mcp_tools.ToolDependencies(repo=repo, performance_service=None)


def test_mcp_value_tools_carry_a_data_freshness_block():
    repo = FreshnessRepo(overview=OVERVIEW)
    result = mcp_tools.run_tool_sync(_deps(repo), "get_portfolio_summary", {"portfolio_id": 1}, OWNER)
    fresh = result["data_freshness"]
    assert fresh["last_successful_price_sync"] == "2026-11-02T22:44:00+00:00"
    assert fresh["last_sync_status"] == "partial"
    assert fresh["last_sync_finished_at"] == "2026-11-03T22:45:00+00:00"
    assert fresh["stale_symbols"] == ["XAD1"]
    assert fresh["oldest_price_at"] == "2026-10-30"
    assert "parziale" in fresh["note"] and "XAD1" in fresh["note"]
    assert result["market_value"] == 1000.0

    aggregate = mcp_tools.run_tool_sync(_deps(repo), "get_aggregate_summary", {"portfolio_ids": [1, 2]}, OWNER)
    assert aggregate["data_freshness"]["stale_symbols"] == ["XAD1"]

    assert {"get_portfolio_summary", "get_positions", "get_performance", "get_portfolio_health",
            "get_aggregate_summary", "get_aggregate_positions"} <= FRESHNESS_TOOLS
    assert FRESHNESS_TOOLS <= mcp_tools.EXPOSED_TOOL_NAMES


def test_mcp_freshness_reuses_the_positions_of_the_tool():
    from app.repository._positions import PositionsMixin

    class _Pos(SimpleNamespace):
        def model_copy(self):
            return self

    class MemoRepo(FreshnessRepo):
        memoize_positions = PositionsMixin.memoize_positions
        get_positions = PositionsMixin.get_positions

        def _compute_positions(self, portfolio_id, user_id, stale_days):
            self.positions_calls += 1
            return [_Pos(**vars(p)) for p in self._positions()]

    repo = MemoRepo(overview=OVERVIEW)
    result = mcp_tools.run_tool_sync(_deps(repo), "get_portfolio_summary", {"portfolio_id": 1}, OWNER)
    assert result["data_freshness"]["stale_symbols"] == ["XAD1"]
    assert repo.positions_calls == 1  # summary + freshness share one computation


def test_mcp_freshness_degrades_when_the_sync_tables_are_missing():
    repo = FreshnessRepo(raise_overview=True)
    fresh = mcp_tools.run_tool_sync(_deps(repo), "get_portfolio_summary", {"portfolio_id": 1}, OWNER)["data_freshness"]
    assert fresh["last_successful_price_sync"] is None and fresh["last_sync_status"] is None
    assert fresh["stale_symbols"] == ["XAD1"]
    assert "non disponibile" in fresh["note"]


def test_get_data_freshness_tool_lists_each_position():
    repo = FreshnessRepo(overview=OVERVIEW)
    out = mcp_tools.run_tool_sync(_deps(repo), "get_data_freshness", {"portfolio_id": 1}, OWNER)
    assert out["portfolio_id"] == 1
    assert out["sync"] == {
        "last_successful_price_sync": "2026-11-02T22:44:00+00:00",
        "last_sync_status": "partial",
        "last_sync_finished_at": "2026-11-03T22:45:00+00:00",
        "sync_running": False,
    }
    assert out["positions_count"] == 2  # closed position excluded
    by_symbol = {r["symbol"]: r for r in out["positions"]}
    assert by_symbol["VWCE"] == {
        "symbol": "VWCE", "last_price_at": "2026-11-03T16:35:00+00:00", "last_bar_date": "2026-11-03",
        "stale": False, "stale_reason": None, "last_sync_success_at": None, "last_sync_error": None,
    }
    assert by_symbol["XAD1"]["stale"] is True
    assert by_symbol["XAD1"]["stale_reason"].startswith("ultima quotazione del 30/10")
    assert by_symbol["XAD1"]["last_sync_error"].startswith("barre:")
    assert out["stale_symbols"] == ["XAD1"]

    with pytest.raises(mcp_tools.McpToolError):
        mcp_tools.run_tool_sync(_deps(repo), "get_data_freshness", {"portfolio_id": 1}, "user_other")
    with pytest.raises(mcp_tools.McpToolError):
        mcp_tools.run_tool_sync(_deps(repo), "get_data_freshness", {"portfolio_id": 1, "x": 1}, OWNER)


def test_get_data_freshness_is_listed_read_only_with_a_bounded_schema():
    tool = next(t for t in mcp_tools.build_tool_list() if t.name == "get_data_freshness")
    assert tool.annotations.readOnlyHint is True and tool.annotations.destructiveHint is False
    assert tool.inputSchema["required"] == ["portfolio_id"]
    assert tool.inputSchema["additionalProperties"] is False
    assert "get_data_freshness" not in mcp_tools.HEAVY_TOOLS


# --- files ---------------------------------------------------------------------------------


def test_workflow_file_is_valid_and_never_prints_the_token():
    path = REPO_ROOT / ".github" / "workflows" / "market-data-sync.yml"
    text = path.read_text(encoding="utf-8")
    workflow = yaml.safe_load(text)
    triggers = workflow.get("on", workflow.get(True))
    crons = [entry["cron"] for entry in triggers["schedule"]]
    assert crons and all(c.split()[4] in ("1-5", "2-6") for c in crons)
    assert "workflow_dispatch" in triggers
    job = workflow["jobs"]["sync"]
    assert "secrets.MARKET_DATA_SYNC_TOKEN" in job["env"]["SYNC_TOKEN"]
    assert "secrets.VALORE365_API_BASE_URL" in job["env"]["API_BASE_URL"]
    assert not any("uses" in step for step in job["steps"])
    script = "\n".join(step.get("run", "") for step in job["steps"])
    assert "/api/health" in script and "/api/internal/market-data/sync/status" in script
    assert "sleep 20" in script and "exit 1" in script and "::warning::" in script
    assert 'echo "${SYNC_TOKEN}' not in script and "echo $SYNC_TOKEN" not in script
    assert "-H \"Authorization" not in script  # token via stdin (-K -), never on the command line


def test_app_migration_copy_matches_the_database_migration():
    db = (REPO_ROOT / "database" / "migrations" / "20261103_01_market_data_sync.sql").read_text(encoding="utf-8")
    app_copy = (Path(__file__).resolve().parents[2] / "app" / "sql" / "migrations" / "create_market_data_sync.sql")
    assert app_copy.read_text(encoding="utf-8") == db
    assert "create table if not exists market_data_sync_runs" in db
    assert "create table if not exists market_data_asset_sync" in db
    assert "enable row level security" in db
    assert "alter table" in db and "add column" not in db.lower()  # additive: no change to existing tables
    schema = (REPO_ROOT / "database" / "schema.sql").read_text(encoding="utf-8")
    assert "market_data_sync_runs" in schema and "market_data_asset_sync" in schema
