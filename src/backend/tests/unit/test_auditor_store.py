"""TASK-80: orchestrazione della corsa notturna dell'Auditor (services/auditor/store.py).

Store in memoria con la stessa interfaccia di ``AuditorStore`` (l'SQL vero è coperto da
``tests/integration/test_auditor_store_postgres.py``), lock finto e ``audit_user`` finto che
restituisce report con evidenze piene di dati sensibili: nulla di questo deve arrivare allo store
o ai log.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.services.auditor import store as st
from app.services.auditor.context import AuditToolError, ScopeSelectionError

SECRET_SYMBOL = "SECRETSYM.MI"
SECRET_AMOUNT = 123456.78
SECRET_USER = "user_secret_owner_42"


class FakeStore:
    def __init__(self, users=("u1", "u2")) -> None:
        self.users = list(users)
        self.runs: list[dict] = []
        self.results: list[dict] = []
        self.lock = threading.Lock()
        self.existing_portfolios: set[int] | None = None

    def create_run(self, run_uuid, trigger, app_version):
        row = {
            "id": len(self.runs) + 1, "run_uuid": run_uuid, "status": "running", "trigger": trigger,
            "app_version": app_version, "started_at": datetime.now(UTC) + timedelta(seconds=len(self.runs)),
            "finished_at": None, "users_total": 0, "users_failed": 0, "portfolios_total": 0, "rules_total": 0,
            "pass_count": 0, "fail_count": 0, "skip_count": 0, "error_count": 0, "deadline_exceeded": False,
            "error_type": None,
        }
        self.runs.append(row)
        return row["id"]

    def update_run(self, run_id, **values):
        unknown = set(values) - set(st.AuditorStore._UPDATABLE)
        assert not unknown, unknown
        self.runs[run_id - 1].update(values)

    def mark_interrupted(self):
        count = 0
        for run in self.runs:
            if run["status"] == "running":
                run["status"], run["finished_at"] = "interrupted", datetime.now(UTC)
                count += 1
        return count

    def save_results(self, run_id, rows):
        clean = [st.clean_result_row(r) for r in rows]
        with self.lock:
            for row in clean:
                if self.existing_portfolios is None or row["portfolio_id"] in self.existing_portfolios:
                    self.results.append({"run_id": run_id, **row})
        return len(clean)

    def list_audit_user_ids(self):
        return list(self.users)

    def _last(self, pred):
        rows = [r for r in self.runs if pred(r)]
        return dict(max(rows, key=lambda r: (r["started_at"], r["id"]))) if rows else None

    def get_run(self, run_uuid):
        return self._last(lambda r: r["run_uuid"] == run_uuid)

    def running_run(self):
        return self._last(lambda r: r["status"] == "running")

    def last_finished_run(self):
        return self._last(lambda r: r["status"] != "running")

    def last_concluded_run(self):
        return self._last(lambda r: r["status"] in st.CONCLUDED_STATUSES)

    def _rules(self, run_id, status):
        out: dict[str, dict] = {}
        for row in self.results:
            if row["run_id"] == run_id and row["status"] == status:
                item = out.setdefault(row["rule_id"], {"rule_id": row["rule_id"], "severity": row["severity"], "p": set()})
                item["p"].add(row["portfolio_id"])
                item["severity"] = min(item["severity"], row["severity"])
        return sorted(out.values(), key=lambda i: (i["severity"], i["rule_id"]))

    def failing_rules(self, run_id):
        return [{"rule_id": i["rule_id"], "severity": i["severity"], "portfolios": len(i["p"])}
                for i in self._rules(run_id, "fail")]

    def error_rules(self, run_id):
        return [{"rule_id": i["rule_id"], "portfolios": len(i["p"])} for i in self._rules(run_id, "error")]

    def fail_history(self, rule_ids, *, up_to_run_id, limit=400):
        runs = [r for r in self.runs
                if (r["status"] in st.CONCLUDED_STATUSES and r["id"] <= up_to_run_id) or r["id"] == up_to_run_id]
        runs = sorted(runs, key=lambda r: (r["started_at"], r["id"]), reverse=True)[:limit]
        failing = {(r["run_id"], r["rule_id"]) for r in self.results if r["status"] == "fail" and r["rule_id"] in rule_ids}
        return [{"id": r["id"], "status": r["status"], "started_at": r["started_at"]} for r in runs], failing


class FakeLock:
    """Lock advisory condiviso: held=True simula un altro processo con la corsa."""

    def __init__(self) -> None:
        self.held = False
        self.acquired = 0
        self.released = 0
        self.heartbeats = 0

    def factory(self):
        lock = self

        class _Handle:
            def acquire(self_inner):
                if lock.held:
                    return False
                lock.held = True
                lock.acquired += 1
                return True

            def heartbeat(self_inner):
                lock.heartbeats += 1

            def release(self_inner):
                lock.held = False
                lock.released += 1

        return _Handle()


def _rule(rule_id, area="stress"):
    return SimpleNamespace(id=rule_id, title=f"Titolo {rule_id}", area=area)


RULES = [_rule("A-ONE"), _rule("B-TWO", "rebalance"), _rule("D-THREE", "consistency")]


def _result(rule_id, scope, status, severity="P1"):
    return {
        "rule_id": rule_id, "scope": scope, "status": status, "severity": severity,
        "reason": f"{SECRET_SYMBOL} vale {SECRET_AMOUNT}",
        "evidence": [{"tool": "get_positions", "path": "positions[0].market_value",
                      "observed": SECRET_AMOUNT, "expected": 1.0, "note": SECRET_SYMBOL}],
    }


def _report(pids, *, fail=False, deadline=False):
    results = []
    scopes = []
    for pid in pids:
        scope = {"kind": "portfolio", "portfolio_id": pid}
        scopes.append({"scope": scope, "scope_key": f"portfolio:{pid}"})
        results.append(_result("A-ONE", scope, "pass"))
        results.append(_result("B-TWO", scope, "fail" if fail else "pass", "P0"))
        inst = {"kind": "instrument", "portfolio_id": pid, "symbol": SECRET_SYMBOL}
        results.append(_result("D-THREE", inst, "skip", "P2"))
    if len(pids) >= 2:
        results.append(_result("D-THREE", {"kind": "aggregate", "portfolio_ids": list(pids)}, "error", "P2"))
    by_status = {k: sum(1 for r in results if r["status"] == k) for k in ("pass", "fail", "skip", "error")}
    return {
        "results": results, "scopes": scopes, "counts": {"total": len(results), "by_status": by_status},
        "tool_calls": {"total": 10, "cache_hits": 3, "errors": 1, "by_tool": {}}, "deadline_exceeded": deadline,
    }


def _settings(**values):
    base = dict(auditor_max_concurrency=2, auditor_max_duration_s=1800.0, auditor_user_max_duration_s=300.0,
                auditor_rule_timeout_s=30.0)
    base.update(values)
    return SimpleNamespace(**base)


def _service(store, lock, audit_user, *, settings=None, rules_loader=None, monotonic=time.monotonic, **kw):
    return st.AuditorNightlyService(
        settings or _settings(), engine=None, store=store, lock_factory=lock.factory,
        rules_loader=rules_loader or (lambda: RULES), deps_factory=lambda: "deps", audit_user=audit_user,
        app_version="9.9.9", monotonic=monotonic, **kw,
    )


PORTFOLIOS = {"u1": [11, 12], "u2": [21], SECRET_USER: [31]}


def _audit_ok(calls=None, fail_users=()):
    def audit(deps, rules, user_id, run_uuid, options):
        if calls is not None:
            calls.append((deps, len(rules), user_id, run_uuid, options))
        return _report(PORTFOLIOS[user_id], fail=user_id in fail_users)
    return audit


# --- corsa -------------------------------------------------------------------------------------


def test_run_saves_only_privacy_rows_and_sums_counts():
    store, lock, calls = FakeStore(), FakeLock(), []
    outcome = _service(store, lock, _audit_ok(calls, fail_users={"u1"})).run_now("manual")

    assert outcome.status == "completed_with_failures"
    run = store.runs[0]
    assert run["status"] == "completed_with_failures" and run["finished_at"] is not None
    assert run["trigger"] == "manual" and run["app_version"] == "9.9.9"
    assert run["users_total"] == 2 and run["users_failed"] == 0
    assert run["portfolios_total"] == 3 and run["rules_total"] == 3
    # u1: 2 portafogli (2 pass, 2 fail, 2 skip, 1 error); u2: 1 portafoglio (2 pass, 1 skip).
    assert (run["pass_count"], run["fail_count"], run["skip_count"], run["error_count"]) == (4, 2, 3, 1)
    assert outcome.tool_calls == {"total": 20, "cache_hits": 6, "errors": 2}
    assert run["error_type"] is None
    # Righe: solo le colonne ammesse; instrument collassato, aggregate per membro.
    assert all(set(r) == {"run_id", *st.RESULT_COLUMNS} for r in store.results)
    keys = {(r["portfolio_id"], r["rule_id"], r["scope_kind"], r["status"]) for r in store.results}
    assert (11, "D-THREE", "instrument", "skip") in keys
    assert (11, "D-THREE", "aggregate", "error") in keys and (12, "D-THREE", "aggregate", "error") in keys
    assert (11, "B-TWO", "portfolio", "fail") in keys and (21, "B-TWO", "portfolio", "pass") in keys
    flat = repr(store.results) + repr(store.runs)
    assert SECRET_SYMBOL not in flat and str(SECRET_AMOUNT) not in flat and "u1" not in flat
    # Una chiamata per utente, modalità notturna, stesso run_id della riga, limiti dalla configurazione.
    assert sorted(c[2] for c in calls) == ["u1", "u2"]
    for deps, n_rules, _uid, run_uuid, options in calls:
        assert deps == "deps" and n_rules == 3 and run_uuid == run["run_uuid"]
        assert options.mode == "nightly" and options.rule_timeout_s == 30.0 and options.max_workers == 1
        assert 0 < options.max_duration_s <= 300.0
    assert lock.acquired == 1 and lock.released == 1 and lock.held is False
    assert lock.heartbeats == 2


def test_success_when_no_fail_or_error():
    store, lock = FakeStore(users=["u2"]), FakeLock()
    outcome = _service(store, lock, _audit_ok()).run_now()
    assert outcome.status == "success" and store.runs[0]["status"] == "success"


def test_no_users_is_success_with_zero_counts():
    store, lock = FakeStore(users=[]), FakeLock()
    outcome = _service(store, lock, _audit_ok()).run_now()
    assert outcome.status == "success" and store.runs[0]["users_total"] == 0 and store.results == []


def test_failing_user_does_not_stop_the_others(caplog):
    store, lock = FakeStore(users=["u1", "boom", "u2", "tool"]), FakeLock()

    def audit(deps, rules, user_id, run_uuid, options):
        if user_id == "boom":
            raise ScopeSelectionError("portafogli non trovati per l'utente: 999 " + SECRET_SYMBOL)
        if user_id == "tool":
            raise AuditToolError("list_portfolios", {}, "db down " + SECRET_SYMBOL)
        return _report(PORTFOLIOS[user_id])

    caplog.set_level(logging.INFO, logger="app.services.auditor.store")
    outcome = _service(store, lock, audit).run_now()
    run = store.runs[0]
    assert outcome.status == "completed_with_failures"
    assert run["users_total"] == 4 and run["users_failed"] == 2 and run["portfolios_total"] == 3
    assert {r["portfolio_id"] for r in store.results} == {11, 12, 21}
    assert run["error_type"] is None
    assert SECRET_SYMBOL not in caplog.text and "999" not in caplog.text and "boom" not in caplog.text
    assert "ScopeSelectionError" in caplog.text and "AuditToolError" in caplog.text


def test_every_user_failing_marks_the_run_failed_with_exception_name_only():
    store, lock = FakeStore(users=["a", "b"]), FakeLock()

    def audit(*_args):
        raise RuntimeError("password=hunter2 " + SECRET_SYMBOL)

    outcome = _service(store, lock, audit).run_now()
    run = store.runs[0]
    assert outcome.status == "failed" and run["status"] == "failed"
    assert run["error_type"] == "RuntimeError"
    assert "hunter2" not in repr(store.runs)
    assert lock.held is False


def test_rule_loading_failure_marks_run_failed():
    store, lock = FakeStore(), FakeLock()

    def broken():
        raise ImportError("modulo rotto con " + SECRET_SYMBOL)

    outcome = _service(store, lock, _audit_ok(), rules_loader=broken).run_now()
    assert outcome.status == "failed" and store.runs[0]["error_type"] == "ImportError"
    assert store.runs[0]["finished_at"] is not None and lock.held is False
    no_rules = _service(FakeStore(), FakeLock(), _audit_ok(), rules_loader=lambda: []).run_now()
    assert no_rules.status == "failed" and no_rules.error_type == "NoRulesLoaded"


def test_saving_failure_counts_as_failed_user():
    store, lock = FakeStore(users=["u1", "u2"]), FakeLock()
    original = store.save_results

    def flaky(run_id, rows):
        rows = list(rows)
        if any(r["portfolio_id"] == 21 for r in rows):
            raise ConnectionError("db")
        return original(run_id, rows)

    store.save_results = flaky
    outcome = _service(store, lock, _audit_ok()).run_now()
    assert outcome.status == "completed_with_failures" and outcome.users_failed == 1


def test_global_deadline_skips_remaining_users_and_caps_each_user():
    store, lock = FakeStore(users=["u1", "u2"]), FakeLock()
    clock = {"t": 1000.0}
    seen = []

    def audit(deps, rules, user_id, run_uuid, options):
        seen.append((user_id, options.max_duration_s))
        clock["t"] += 50.0  # ogni utente consuma 50 s
        return _report(PORTFOLIOS[user_id])

    svc = _service(store, lock, audit, monotonic=lambda: clock["t"],
                   settings=_settings(auditor_max_concurrency=1, auditor_max_duration_s=40.0,
                                      auditor_user_max_duration_s=300.0))
    outcome = svc.run_now()
    assert seen == [("u1", 40.0)]  # tetto = tempo residuo della corsa
    assert outcome.deadline_exceeded is True and outcome.users_failed == 1
    assert outcome.status == "completed_with_failures" and store.runs[0]["deadline_exceeded"] is True


def test_concurrency_limit_is_respected():
    users = [f"x{i}" for i in range(6)]
    for uid in users:
        PORTFOLIOS.setdefault(uid, [100 + int(uid[1:])])
    for limit in (1, 3):
        active, peak, guard = [0], [0], threading.Lock()

        def audit(deps, rules, user_id, run_uuid, options):
            with guard:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.05)
            with guard:
                active[0] -= 1
            return _report(PORTFOLIOS[user_id])

        store = FakeStore(users=users)
        _service(store, FakeLock(), audit, settings=_settings(auditor_max_concurrency=limit)).run_now()
        assert peak[0] <= limit
        if limit == 3:
            assert peak[0] >= 2
        assert store.runs[0]["users_total"] == 6 and store.runs[0]["users_failed"] == 0


def test_deleted_portfolio_rows_are_skipped():
    store, lock = FakeStore(users=["u1"]), FakeLock()
    store.existing_portfolios = {11}
    _service(store, lock, _audit_ok()).run_now()
    assert {r["portfolio_id"] for r in store.results} == {11}


def test_logs_never_contain_users_portfolios_or_values(caplog):
    store, lock = FakeStore(users=[SECRET_USER]), FakeLock()
    caplog.set_level(logging.DEBUG)
    _service(store, lock, _audit_ok(fail_users={SECRET_USER})).run_now()
    assert SECRET_USER not in caplog.text and SECRET_SYMBOL not in caplog.text
    assert str(SECRET_AMOUNT) not in caplog.text
    assert "B-TWO" in caplog.text  # id delle regole che falliscono sì


# --- lock e corse interrotte ---------------------------------------------------------------------


def test_lock_held_elsewhere_returns_already_running():
    store, lock = FakeStore(), FakeLock()
    other = store.create_run("a" * 32, "external", "1")
    lock.held = True
    svc = _service(store, lock, _audit_ok())
    result = svc.start_in_background("external")
    assert isinstance(result, st.AlreadyRunning) and result.run_id == "a" * 32
    assert len(store.runs) == 1 and store.runs[other - 1]["status"] == "running"
    # mark_interrupted_runs non tocca la corsa di un processo vivo.
    assert svc.mark_interrupted_runs() == 0 and store.runs[0]["status"] == "running"


def test_running_run_in_this_process_blocks_a_second_start():
    store, lock = FakeStore(users=["u2"]), FakeLock()
    gate, entered = threading.Event(), threading.Event()

    def audit(deps, rules, user_id, run_uuid, options):
        entered.set()
        gate.wait(5)
        return _report(PORTFOLIOS[user_id])

    threads = []

    def factory(**kwargs):
        thread = threading.Thread(**kwargs)
        threads.append((thread, kwargs))
        return thread

    svc = _service(store, lock, audit, thread_factory=factory)
    first = svc.start_in_background("external")
    assert isinstance(first, st.RunStarted) and first.status == "running"
    assert threads[0][1]["daemon"] is True
    assert entered.wait(5)
    second = svc.start_in_background("external")
    assert isinstance(second, st.AlreadyRunning) and second.run_id == first.run_id
    assert svc.status_payload()["running"]["run_id"] == first.run_id
    gate.set()
    threads[0][0].join(5)
    assert store.runs[0]["status"] == "success"
    third = svc.start_in_background("external")
    assert isinstance(third, st.RunStarted) and third.run_id != first.run_id
    threads[-1][0].join(5)


def test_interrupted_run_is_marked_at_startup_and_on_next_start():
    store, lock = FakeStore(users=["u2"]), FakeLock()
    store.create_run("b" * 32, "external", "1")  # processo morto: lock libero, riga 'running'
    svc = _service(store, lock, _audit_ok())
    assert svc.mark_interrupted_runs() == 1
    assert store.runs[0]["status"] == "interrupted" and store.runs[0]["finished_at"] is not None
    assert lock.held is False

    store.create_run("c" * 32, "external", "1")
    svc.run_now("external")
    assert store.runs[1]["status"] == "interrupted"
    assert store.runs[2]["status"] == "success"


def test_launch_interrupted_check_runs_in_a_daemon_thread_and_never_raises():
    created = []

    def factory(**kwargs):
        created.append(kwargs)
        return threading.Thread(**kwargs)

    service = SimpleNamespace(mark_interrupted_runs=lambda: (_ for _ in ()).throw(RuntimeError("db down")))
    thread = st.launch_interrupted_check(service, thread_factory=factory)
    thread.join(5)
    assert created[0]["daemon"] is True


def test_invalid_trigger_rejected():
    with pytest.raises(ValueError):
        _service(FakeStore(), FakeLock(), _audit_ok()).try_begin("startup")


def test_thread_start_failure_releases_lock_and_marks_failed():
    store, lock = FakeStore(), FakeLock()

    def factory(**kwargs):
        raise RuntimeError("no threads")

    svc = _service(store, lock, _audit_ok(), thread_factory=factory)
    with pytest.raises(RuntimeError):
        svc.start_in_background("external")
    assert lock.held is False and store.runs[0]["status"] == "failed"
    assert store.runs[0]["error_type"] == "RuntimeError"


# --- letture -------------------------------------------------------------------------------------


def test_status_payload_and_admin_latest_with_since():
    store, lock = FakeStore(users=["u1", "u2"]), FakeLock()
    svc = _service(store, lock, _audit_ok())
    svc.run_now()                                   # 1: success
    svc._audit_user_fn = _audit_ok(fail_users={"u1"})
    svc.run_now()                                   # 2: B-TWO fallisce
    store.create_run("d" * 32, "external", "1")
    svc.mark_interrupted_runs()                     # 3: interrupted (ignorata nella serie)
    svc.run_now()                                   # 4: B-TWO fallisce ancora

    status = svc.status_payload()
    assert status["running"] is None
    last = status["last_run"]
    assert last["run_id"] == store.runs[3]["run_uuid"] and last["status"] == "completed_with_failures"
    assert last["counts"] == {"pass": 4, "fail": 2, "skip": 3, "error": 1}
    assert last["failing_rules"] == [{"rule_id": "B-TWO", "severity": "P0", "portfolios": 2}]
    assert set(last) >= {"run_id", "status", "trigger", "app_version", "started_at", "finished_at",
                         "portfolios_total", "rules_total", "counts", "failing_rules"}

    latest = svc.admin_latest()
    assert latest["run"]["run_id"] == store.runs[3]["run_uuid"]
    [failing] = latest["failing"]
    assert failing == {
        "rule_id": "B-TWO", "title": "Titolo B-TWO", "area": "rebalance", "severity": "P0",
        "portfolios_failing": 2, "since": store.runs[1]["started_at"].isoformat(),
    }
    assert latest["errors"] == [{"rule_id": "D-THREE", "portfolios": 2}]
    text = repr(status) + repr(latest)
    assert "u1" not in text and "u2" not in text and "portfolio_id" not in text


def test_admin_latest_without_runs():
    svc = _service(FakeStore(), FakeLock(), _audit_ok())
    assert svc.admin_latest() == {"run": None, "failing": [], "errors": []}
    assert svc.status_payload() == {"running": None, "last_run": None}


def test_compute_since_stops_at_first_run_without_failure():
    t0 = datetime(2026, 11, 1, tzinfo=UTC)
    runs = [{"id": i, "started_at": t0 + timedelta(days=i)} for i in (5, 4, 3, 2)]
    failing = {(5, "R"), (4, "R"), (2, "R")}
    assert st.compute_since("R", runs, failing) == (t0 + timedelta(days=4)).isoformat()
    assert st.compute_since("X", runs, failing) is None


def test_clean_result_row_rejects_unknown_values_and_drops_extra_keys():
    row = {"portfolio_id": "7", "rule_id": "A-ONE", "scope_kind": "portfolio", "status": "fail",
           "severity": "P1", "symbol": SECRET_SYMBOL, "evidence": [SECRET_AMOUNT]}
    assert st.clean_result_row(row) == {"portfolio_id": 7, "rule_id": "A-ONE", "scope_kind": "portfolio",
                                        "status": "fail", "severity": "P1"}
    for key, bad in (("scope_kind", "symbol"), ("status", "boom"), ("severity", "P9")):
        with pytest.raises(ValueError):
            st.clean_result_row({**row, key: bad})


def test_update_run_rejects_unknown_columns():
    with pytest.raises(ValueError):
        st.AuditorStore(engine=None).update_run(1, reason="testo libero")


def test_settings_defaults_match_contract():
    from app.config import Settings

    s = Settings(_env_file=None)
    assert s.auditor_run_token == ""
    assert s.auditor_max_concurrency == 2 and s.auditor_max_duration_s == 1800
    assert s.auditor_rule_timeout_s == 30 and s.auditor_user_max_duration_s == 300
    assert (s.auditor_run_rate_limit_requests, s.auditor_run_rate_limit_window_seconds) == (4, 3600)
    assert s.auditor_status_rate_limit_requests == 240 and s.auditor_auth_failure_limit_requests == 30


def test_startup_migration_copy_is_identical():
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    repo_root = backend.parents[1]
    copy = (backend / "app" / "sql" / "migrations" / "create_auditor.sql").read_text(encoding="utf-8")
    original = (repo_root / "database" / "migrations" / "20261111_01_auditor.sql").read_text(encoding="utf-8")
    assert copy == original
    assert "enable row level security" in original
