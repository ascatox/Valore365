"""TASK-57: backfill automatico della cifratura dei campi all'avvio.

Nessun database: lock, backfill e connessioni sono fake in memoria.
"""

from __future__ import annotations

import base64
import os
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.crypto.backfill import TARGETS, TableResult, backfill_all, backfill_table
from app.services import field_encryption_backfill as feb
from app.services.field_encryption_backfill import FIELD_ENCRYPTION_BACKFILL_LOCK_KEY, FieldEncryptionBackfillRunner
from app.services.market_data_sync import MARKET_DATA_SYNC_LOCK_KEY


ENABLED = SimpleNamespace(enabled=True)
DISABLED = SimpleNamespace(enabled=False)


def _settings(**kw):
    values = {"data_backfill_on_startup": True, "data_backfill_batch_size": 50, "data_backfill_batch_pause_seconds": 0.0}
    values.update(kw)
    return SimpleNamespace(**values)


class FakeLock:
    def __init__(self, acquired=True, error=None):
        self.acquired = acquired
        self.error = error
        self.heartbeats = 0
        self.released = False

    def acquire(self):
        if self.error:
            raise self.error
        return self.acquired

    def heartbeat(self):
        self.heartbeats += 1

    def release(self):
        self.released = True


class FakeEngine:
    def begin(self):  # pragma: no cover - the fake backfill never opens connections
        raise AssertionError("unexpected connection")


class RecordingThread:
    started: list = []

    def __init__(self, target, args=(), kwargs=None, name=None, daemon=None):
        self.target, self.args, self.kwargs, self.name, self.daemon = target, args, kwargs or {}, name, daemon
        self.alive = False

    def start(self):
        RecordingThread.started.append(self)

    def is_alive(self):
        return self.alive

    def join(self, timeout=None):
        pass


@pytest.fixture(autouse=True)
def _reset_threads():
    RecordingThread.started = []


def _runner(lock=None, backfill=None, **kw):
    lock = lock or FakeLock()
    calls = []

    def fake_backfill(crypto, conn_factory, **kwargs):
        calls.append(kwargs)
        if backfill is not None:
            return backfill(crypto, conn_factory, **kwargs)
        return [TableResult(t.table) for t in TARGETS]

    runner = FieldEncryptionBackfillRunner(
        FakeEngine(), lock_factory=lambda engine: lock, backfill=fake_backfill, thread_factory=RecordingThread, **kw
    )
    return runner, lock, calls


# --- start --------------------------------------------------------------------------


def test_thread_started_only_when_enabled_and_keys_configured():
    runner, _, _ = _runner()
    assert runner.start(ENABLED, _settings(data_backfill_on_startup=False)) is None
    assert runner.status()["status"] == "disabled"
    assert runner.start(DISABLED, _settings()) is None
    assert runner.start(None, _settings()) is None
    assert RecordingThread.started == []

    thread = runner.start(ENABLED, _settings(data_backfill_batch_size=77, data_backfill_batch_pause_seconds=0.5))
    assert RecordingThread.started == [thread]
    assert thread.daemon is True and thread.name == "field-encryption-backfill"
    assert thread.args == (ENABLED,)
    assert thread.kwargs == {"batch_size": 77, "batch_pause_seconds": 0.5}


def test_start_does_not_start_twice_while_running():
    runner, _, _ = _runner()
    thread = runner.start(ENABLED, _settings())
    thread.alive = True
    assert runner.start(ENABLED, _settings()) is None
    assert len(RecordingThread.started) == 1


def test_start_never_raises():
    def boom(**kw):
        raise RuntimeError("no threads")

    runner = FieldEncryptionBackfillRunner(FakeEngine(), thread_factory=boom)
    assert runner.start(ENABLED, _settings()) is None
    assert runner.status()["status"] == "failed"


def test_distinct_lock_key():
    assert FIELD_ENCRYPTION_BACKFILL_LOCK_KEY != MARKET_DATA_SYNC_LOCK_KEY
    runner = FieldEncryptionBackfillRunner(FakeEngine())
    assert runner._lock_factory(FakeEngine()).key == FIELD_ENCRYPTION_BACKFILL_LOCK_KEY


# --- run ----------------------------------------------------------------------------


def test_run_with_nothing_to_do_logs_one_summary(caplog):
    runner, lock, calls = _runner()
    caplog.set_level("INFO", logger=feb.logger.name)
    status = runner.run(ENABLED, batch_size=10, batch_pause_seconds=0.1)
    assert status["status"] == "completed"
    assert status["rows_updated"] == 0 and status["error"] is None
    assert set(status["tables"]) == {t.table for t in TARGETS}
    assert lock.released
    assert calls[0]["isolate_errors"] is True and calls[0]["batch_size"] == 10
    assert calls[0]["batch_pause_seconds"] == 0.1 and calls[0]["on_batch"] == lock.heartbeat
    summaries = [r.message for r in caplog.records if "rows updated" in r.message]
    assert len(summaries) == 1
    assert not [r for r in caplog.records if "updated=" in r.message and "rows" not in r.message]


def test_run_reports_per_table_counts_and_errors():
    def backfill(crypto, conn_factory, **kw):
        return [
            TableResult("portfolios", scanned=3, updated=3),
            TableResult("transactions", scanned=2, updated=1, failed=["9"]),
            TableResult("app_users", error="OperationalError: boom"),
        ]

    runner, lock, _ = _runner(backfill=backfill)
    status = runner.run(ENABLED)
    assert status["status"] == "completed_with_errors"
    assert status["rows_updated"] == 4 and status["rows_failed"] == 1
    assert status["tables"]["portfolios"]["updated"] == 3
    assert status["tables"]["app_users"]["error"] == "OperationalError: boom"
    assert "app_users" in status["error"]
    assert status["started_at"] and status["finished_at"]
    assert lock.released


def test_lock_not_acquired_skips():
    runner, lock, calls = _runner(lock=FakeLock(acquired=False))
    status = runner.run(ENABLED)
    assert status["status"] == "skipped_locked"
    assert calls == []


def test_exceptions_do_not_propagate():
    runner, _, _ = _runner(lock=FakeLock(error=RuntimeError("db down")))
    assert runner.run(ENABLED)["status"] == "failed"

    def explode(crypto, conn_factory, **kw):
        raise RuntimeError("unexpected")

    runner, lock, _ = _runner(backfill=explode)
    status = runner.run(ENABLED)
    assert status["status"] == "failed" and "unexpected" in status["error"]
    assert lock.released


def test_stop_sets_the_event_seen_by_the_backfill():
    seen = {}

    def backfill(crypto, conn_factory, **kw):
        seen["event"] = kw["stop_event"]
        return [TableResult("portfolios", stopped=kw["stop_event"].is_set())]

    runner, _, _ = _runner(backfill=backfill)
    runner.start(ENABLED, _settings())
    runner.stop(timeout=0)
    status = runner.run(ENABLED)
    assert seen["event"].is_set()
    assert status["status"] == "stopped"
    # A new start clears the stop request.
    runner.start(ENABLED, _settings())
    assert not seen["event"].is_set()


def test_real_thread_runs_to_completion():
    done = threading.Event()

    def backfill(crypto, conn_factory, **kw):
        done.set()
        return []

    runner = FieldEncryptionBackfillRunner(FakeEngine(), lock_factory=lambda e: FakeLock(), backfill=backfill)
    thread = runner.start(ENABLED, _settings())
    thread.join(5)
    assert done.is_set() and runner.status()["status"] == "completed"


# --- backfill_table: stop / pause / error isolation ----------------------------------


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class FakeConn:
    def __init__(self, db, fail_on_update=False):
        self.db = db
        self.fail_on_update = fail_on_update

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, stmt, params=None):
        sql = str(stmt)
        if sql.startswith("select"):
            after = params.get("_after")
            rows = [r for r in self.db if r["name"] == "plain" and (after is None or r["id"] > after)]
            return _Result(rows[: params["_limit"]])
        if self.fail_on_update:
            raise RuntimeError("connection lost")
        for r in self.db:
            if r["id"] == params["_key"]:
                r["name"] = params["name"]
        return _Result([])


PORTFOLIOS = next(t for t in TARGETS if t.table == "portfolios")


class FakeCrypto:
    enabled = True

    def encrypt(self, conn, table, column, owner, value):
        return "enc:v1:x"


def _db(n):
    return [{"id": i, "owner_user_id": "u", "name": "plain"} for i in range(1, n + 1)]


def test_backfill_table_stop_event_stops_after_current_batch():
    db = _db(10)
    stop = threading.Event()
    beats = []

    def on_batch():
        beats.append(1)
        stop.set()

    result = backfill_table(FakeCrypto(), lambda: FakeConn(db), PORTFOLIOS, batch_size=3, stop_event=stop, on_batch=on_batch)
    assert result.stopped and result.updated == 3 and beats == [1]
    assert sum(r["name"] == "plain" for r in db) == 7


def test_backfill_table_pause_is_interrupted_by_stop():
    db = _db(10)
    stop = threading.Event()
    threading.Timer(0.05, stop.set).start()
    result = backfill_table(FakeCrypto(), lambda: FakeConn(db), PORTFOLIOS, batch_size=3, stop_event=stop, batch_pause_seconds=30)
    assert result.stopped and result.updated == 3


def test_backfill_table_completes_and_pauses_between_batches(monkeypatch):
    sleeps = []
    monkeypatch.setattr("app.crypto.backfill.time.sleep", sleeps.append)
    db = _db(5)
    result = backfill_table(FakeCrypto(), lambda: FakeConn(db), PORTFOLIOS, batch_size=2, batch_pause_seconds=0.2)
    assert not result.stopped and result.updated == 5 and result.scanned == 5
    assert sleeps == [0.2, 0.2, 0.2]


def test_backfill_all_isolate_errors_goes_on_with_other_tables():
    db = _db(2)
    with pytest.raises(RuntimeError):
        backfill_table(FakeCrypto(), lambda: FakeConn(db, fail_on_update=True), PORTFOLIOS)
    result = backfill_table(FakeCrypto(), lambda: FakeConn(db, fail_on_update=True), PORTFOLIOS, isolate_errors=True)
    assert result.error == "RuntimeError: connection lost"
    assert result.updated == 0  # the failed batch was rolled back: not counted


def test_backfill_all_marks_remaining_tables_stopped():
    stop = threading.Event()
    stop.set()
    results = backfill_all(FakeCrypto(), lambda: pytest.fail("no connection"), stop_event=stop)
    assert [r.table for r in results] == [t.table for t in TARGETS]
    assert all(r.stopped for r in results)


# --- lifespan + admin endpoint --------------------------------------------------------


def _quiet_lifespan(monkeypatch, api_main):
    monkeypatch.setattr(api_main, "_apply_pending_migrations", lambda: None)
    monkeypatch.setattr(api_main.scheduler, "start", lambda: None)
    monkeypatch.setattr(api_main.scheduler, "shutdown", lambda: None)
    monkeypatch.setattr(api_main, "launch_startup_catch_up", lambda svc, settings: None)


def test_lifespan_starts_and_stops_the_backfill(monkeypatch):
    import app.main as api_main

    _quiet_lifespan(monkeypatch, api_main)
    calls = []

    class Runner:
        def start(self, crypto, settings):
            calls.append(("start", crypto.enabled))

        def stop(self, timeout=None):
            calls.append(("stop", timeout))

    monkeypatch.setattr(api_main, "field_encryption_backfill", Runner())
    with TestClient(api_main.app) as client:
        assert client.get("/api/health").status_code == 200
    assert calls[0][0] == "start" and calls[-1] == ("stop", 5.0)


def test_lifespan_with_keys_launches_real_runner_without_blocking(monkeypatch):
    import app.main as api_main
    from app.config import Settings

    _quiet_lifespan(monkeypatch, api_main)
    key = base64.b64encode(os.urandom(32)).decode()
    monkeypatch.setattr(
        api_main, "settings", Settings(app_env="dev", data_encryption_keys=f"k1:{key}", data_backfill_batch_pause_seconds=0)
    )
    ran = threading.Event()

    def backfill(crypto, conn_factory, **kw):
        ran.set()
        raise RuntimeError("db unreachable")  # must not break startup

    runner = FieldEncryptionBackfillRunner(FakeEngine(), lock_factory=lambda e: FakeLock(), backfill=backfill)
    monkeypatch.setattr(api_main, "field_encryption_backfill", runner)
    try:
        with TestClient(api_main.app):
            assert ran.wait(5)
        assert runner.status()["status"] == "failed"
    finally:
        from app.crypto import set_field_crypto

        set_field_crypto(None)


def test_admin_backfill_status_endpoint(monkeypatch):
    import app.main as api_main

    runner, _, _ = _runner()
    runner.run(ENABLED)
    monkeypatch.setattr(api_main, "field_encryption_backfill", runner)
    monkeypatch.setattr(api_main.settings, "admin_user_ids", "dev-user")
    response = TestClient(api_main.app).get("/api/admin/field-encryption/backfill")
    assert response.status_code == 200
    assert response.json()["status"] == "completed"

    monkeypatch.setattr(api_main.settings, "admin_user_ids", "")
    monkeypatch.setattr(api_main.settings, "admin_emails", "")
    assert TestClient(api_main.app).get("/api/admin/field-encryption/backfill").status_code == 403
