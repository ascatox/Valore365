"""TASK-80: corsa notturna dell'Auditor e storico degli esiti su un PostgreSQL 16 reale.

Applica ``database/schema.sql``, tutte le migrazioni e ``scripts/auditor/audit_seed.sql`` in un
database dedicato del cluster della fixture ``pg_engine`` e verifica:

- tabelle ``auditor_runs``/``auditor_results`` con RLS attiva e solo colonne chiuse;
- una corsa notturna completa (``AuditorNightlyService`` con ``AuditorStore`` e lock advisory veri)
  sul seed: esiti salvati per corsa, portafoglio e regola, conteggi uguali al report del motore,
  nessun importo, simbolo, nome o testo nelle tabelle;
- lock fra processi (advisory lock tenuto da un'altra connessione), corsa interrotta marcata
  all'avvio, endpoint amministrativo con ``since``, letture per TASK-81, vincoli delle tabelle.

I tool del Doctor usano il servizio di processo legato al ``DATABASE_URL`` dell'app: qui viene
sostituito con uno legato al database del seed (architecture.md, Deviazioni TASK-78). La rete è
bloccata durante le corse. Saltato quando i binari di Postgres mancano.
"""

from __future__ import annotations

import socket
import subprocess
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.mcp_server.tools import ToolDependencies
from app.repository import PortfolioRepository
from app.services.auditor import store as st
from app.services.auditor.context import AuditContext, OfflineFinanceClient
from app.services.auditor.registry import load_rules
from app.services.auditor.report import privacy_rows
from app.services.auditor.runner import RunOptions, run_audit
from app.services.market_data_sync import PgAdvisoryLock
from app.services.performance_service import PerformanceService

REPO_ROOT = Path(__file__).resolve().parents[4]
DATABASE_DIR = REPO_ROOT / "database"
SEED = REPO_ROOT / "scripts" / "auditor" / "audit_seed.sql"
DB_NAME = "auditor_store"
USER = "auditor-seed-user"
PORTFOLIO_IDS = [9101, 9102, 9103, 9104, 9105, 9106, 9107]


def _psql_base(pg_engine) -> list[str]:
    url = pg_engine.url
    return ["psql", "-q", "-h", url.query["host"], "-p", str(url.query.get("port") or url.port),
            "-U", "postgres", "-v", "ON_ERROR_STOP=1"]


def _run_psql(psql: list[str], *args: str) -> None:
    subprocess.run([*psql, *args], check=True, capture_output=True, text=True, cwd="/")


def _db_url(pg_engine) -> str:
    url = pg_engine.url
    return f"postgresql+psycopg://postgres@/{DB_NAME}?host={url.query['host']}&port={url.query.get('port') or url.port}"


@pytest.fixture(scope="module")
def seed_engine(pg_engine):
    psql = _psql_base(pg_engine)
    _run_psql(psql, "-d", "postgres", "-c", f"drop database if exists {DB_NAME}")
    _run_psql(psql, "-d", "postgres", "-c", f"create database {DB_NAME}")
    _run_psql(psql, "-d", DB_NAME, "-f", str(DATABASE_DIR / "schema.sql"))
    for migration in sorted((DATABASE_DIR / "migrations").glob("*.sql")):
        _run_psql(psql, "-d", DB_NAME, "-f", str(migration))
    # Idempotente: la copia applicata all'avvio può girare di nuovo.
    _run_psql(psql, "-d", DB_NAME, "-f", str(REPO_ROOT / "src/backend/app/sql/migrations/create_auditor.sql"))
    _run_psql(psql, "-d", DB_NAME, "-f", str(SEED))
    engine = create_engine(_db_url(pg_engine), pool_size=5, max_overflow=5)
    yield engine
    engine.dispose()
    subprocess.run([*psql, "-d", "postgres", "-c", f"drop database if exists {DB_NAME}"], capture_output=True, cwd="/")


@pytest.fixture(scope="module")
def env(seed_engine):
    """Dipendenze sul DB del seed, Doctor rilegato, rete bloccata."""
    import app.services.doctor_policy.service as doctor_service

    repo = PortfolioRepository(seed_engine)
    deps = ToolDependencies(repo=repo, performance_service=PerformanceService(repo), finance_client=OfflineFinanceClient())
    patcher = pytest.MonkeyPatch()
    patcher.setattr(doctor_service, "_default_service", doctor_service.DoctorPolicyService(repo))
    real_connect = socket.socket.connect

    def _no_network(sock, address):
        if sock.family in (socket.AF_INET, socket.AF_INET6):
            raise AssertionError(f"rete non ammessa durante l'audit: {address!r}")
        return real_connect(sock, address)

    patcher.setattr(socket.socket, "connect", _no_network)
    yield {"engine": seed_engine, "deps": deps}
    patcher.undo()


def _settings(**values):
    from types import SimpleNamespace

    base = dict(auditor_max_concurrency=2, auditor_max_duration_s=1800.0, auditor_user_max_duration_s=600.0,
                auditor_rule_timeout_s=30.0)
    base.update(values)
    return SimpleNamespace(**base)


def _service(env, **kw) -> st.AuditorNightlyService:
    return st.AuditorNightlyService(
        _settings(), env["engine"], deps_factory=lambda: env["deps"], app_version="test", **kw,
    )


@pytest.fixture(scope="module")
def nightly(env):
    """Una corsa notturna completa sul seed (thread in background, come dall'endpoint)."""
    threads = []

    def factory(**kwargs):
        import threading

        thread = threading.Thread(**kwargs)
        threads.append(thread)
        return thread

    service = _service(env, thread_factory=factory)
    started = service.start_in_background("external")
    assert isinstance(started, st.RunStarted)
    threads[0].join(900)
    assert not threads[0].is_alive()
    run = service.store.get_run(started.run_id)
    return {"service": service, "run": run, "run_uuid": started.run_id}


def _rows(engine, sql, **params):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), params).mappings().all()]


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------


def test_tables_have_rls_and_only_closed_columns(seed_engine):
    rls = _rows(seed_engine, "select relname, relrowsecurity from pg_class "
                             "where relname in ('auditor_runs', 'auditor_results') order by relname")
    assert rls == [{"relname": "auditor_results", "relrowsecurity": True},
                   {"relname": "auditor_runs", "relrowsecurity": True}]
    columns = {
        (r["table_name"], r["column_name"]): r["data_type"]
        for r in _rows(seed_engine, "select table_name, column_name, data_type from information_schema.columns "
                                    "where table_name in ('auditor_runs', 'auditor_results')")
    }
    assert {c for t, c in columns if t == "auditor_results"} == {
        "run_id", "portfolio_id", "rule_id", "scope_kind", "status", "severity", "created_at"}
    # Nessuna colonna numerica decimale (importi) né json/testo libero.
    assert not [k for k, v in columns.items() if v in ("numeric", "jsonb", "json", "double precision", "real")]


def test_constraints_reject_free_text(seed_engine):
    with seed_engine.begin() as conn:
        run_id = conn.execute(text(
            "insert into auditor_runs (run_uuid, trigger, app_version) values (:u, 'manual', 't') returning id"
        ), {"u": uuid.uuid4().hex}).scalar_one()
    bad_rows = [
        {"rule_id": "VWCE 1234.56 EUR", "scope_kind": "portfolio", "status": "fail", "severity": "P1"},
        {"rule_id": "A-ONE", "scope_kind": "AUDEQ.MI", "status": "fail", "severity": "P1"},
        {"rule_id": "A-ONE", "scope_kind": "portfolio", "status": "1234.56", "severity": "P1"},
        {"rule_id": "A-ONE", "scope_kind": "portfolio", "status": "fail", "severity": "high"},
    ]
    for row in bad_rows:
        with pytest.raises(IntegrityError):
            with seed_engine.begin() as conn:
                conn.execute(text(
                    "insert into auditor_results (run_id, portfolio_id, rule_id, scope_kind, status, severity) "
                    "values (:run_id, 9101, :rule_id, :scope_kind, :status, :severity)"), {"run_id": run_id, **row})
    for column, value in (("error_type", "boom: 1234.56 AUDEQ.MI"), ("status", "weird"), ("trigger", "startup")):
        with pytest.raises(IntegrityError):
            with seed_engine.begin() as conn:
                conn.execute(text(f"update auditor_runs set {column} = :v where id = :id"), {"v": value, "id": run_id})
    with seed_engine.begin() as conn:
        conn.execute(text("delete from auditor_runs where id = :id"), {"id": run_id})


# ---------------------------------------------------------------------------
# Corsa notturna sul seed
# ---------------------------------------------------------------------------


def test_nightly_run_on_seed_saves_results_per_run_portfolio_rule(nightly, env):
    run = nightly["run"]
    assert run["status"] in ("success", "completed_with_failures"), run
    assert run["trigger"] == "external" and run["finished_at"] is not None
    assert run["users_total"] == 1 and run["users_failed"] == 0
    assert run["portfolios_total"] == len(PORTFOLIO_IDS)
    assert run["rules_total"] == 52 and run["error_count"] == 0 and run["error_type"] is None
    assert run["deadline_exceeded"] is False
    saved = _rows(env["engine"], "select portfolio_id, rule_id, scope_kind, status, severity "
                                 "from auditor_results where run_id = :id order by portfolio_id, rule_id, scope_kind",
                  id=run["id"])
    assert {r["portfolio_id"] for r in saved} == set(PORTFOLIO_IDS)
    assert len({r["rule_id"] for r in saved}) == 52

    # Stessi esiti di un'esecuzione diretta del motore (stesso codice, stessi dati, modalità notturna).
    ctx = AuditContext(env["deps"], USER, run_id=uuid.uuid4().hex, mode="nightly")
    report = run_audit(ctx, load_rules(), RunOptions(mode="nightly", rule_timeout_s=30.0))
    assert report["user_id"] is None
    expected = sorted(privacy_rows(report), key=lambda r: (r["portfolio_id"], r["rule_id"], r["scope_kind"]))
    assert saved == expected
    by_status = report["counts"]["by_status"]
    assert (run["pass_count"], run["fail_count"], run["skip_count"], run["error_count"]) == (
        by_status["pass"], by_status["fail"], by_status["skip"], by_status["error"])
    expected_status = "success" if by_status["fail"] == 0 else "completed_with_failures"
    assert run["status"] == expected_status


def test_no_personal_data_in_the_tables(nightly, env):
    engine = env["engine"]
    symbols = [r["symbol"] for r in _rows(engine, "select symbol from assets where symbol is not null")]
    names = [r["name"] for r in _rows(engine, "select name from portfolios where id between 9101 and 9107")]
    amounts = [str(r["v"]) for r in _rows(
        engine, "select distinct round(cash_balance::numeric, 2) as v from portfolios "
                "where id between 9101 and 9107 and cash_balance <> 0")]
    dump = repr(_rows(engine, "select * from auditor_runs")) + repr(_rows(engine, "select * from auditor_results"))
    assert symbols and names
    for needle in [*symbols, *names, *amounts, USER]:
        assert needle not in dump, needle
    # Una sola colonna di testo libero possibile in auditor_runs: error_type (nome di eccezione o null).
    assert all(r["error_type"] is None for r in _rows(engine, "select error_type from auditor_runs "
                                                              "where status in ('success','completed_with_failures')"))


def test_status_payload_and_admin_latest(nightly, env):
    service = nightly["service"]
    payload = service.status_payload()
    assert payload["running"] is None
    assert payload["last_run"]["run_id"] == nightly["run_uuid"]
    assert payload["last_run"]["counts"]["error"] == 0
    latest = service.admin_latest()
    assert latest["run"]["run_id"] == nightly["run_uuid"]
    assert latest["errors"] == []
    for item in latest["failing"]:
        assert set(item) == {"rule_id", "title", "area", "severity", "portfolios_failing", "since"}
        assert item["portfolios_failing"] >= 1 and item["since"]


def test_since_follows_the_uninterrupted_series(env):
    """Serie: fail, pass, fail, (interrupted), fail → since = inizio della terza corsa."""
    store = st.AuditorStore(env["engine"])
    ids = []
    for status in ("fail", "pass", "fail", None, "fail"):
        run_id = store.create_run(uuid.uuid4().hex, "manual", "t")
        ids.append(run_id)
        if status is None:
            store.update_run(run_id, status="interrupted")
            continue
        store.save_results(run_id, [{"portfolio_id": 9101, "rule_id": "D-RULE",
                                     "scope_kind": "portfolio", "status": status, "severity": "P1"}])
        store.update_run(run_id, status="completed_with_failures" if status == "fail" else "success")
    service = _service(env)
    latest = service.admin_latest()
    assert latest["run"]["run_id"] == store._one_run("id = :i", {"i": ids[-1]})["run_uuid"]
    [item] = latest["failing"]
    third = store._one_run("id = :i", {"i": ids[2]})
    assert item["rule_id"] == "D-RULE" and item["title"] == "D-RULE" and item["area"] is None
    assert item["since"] == st._iso(third["started_at"])
    with env["engine"].begin() as conn:
        conn.execute(text("delete from auditor_runs where id = any(:ids)"), {"ids": ids})


def test_latest_results_for_portfolios_for_task81(nightly, env):
    store = st.AuditorStore(env["engine"])
    data = store.latest_results_for_portfolios([9101, 9105])
    assert data["run"]["run_id"] == nightly["run_uuid"] and data["run"]["finished_at"]
    assert {r["portfolio_id"] for r in data["rows"]} == {9101, 9105}
    assert set(data["rows"][0]) == {"portfolio_id", "rule_id", "scope_kind", "status", "severity"}
    assert store.latest_results_for_portfolios([])["rows"] == []


# ---------------------------------------------------------------------------
# Lock e corsa interrotta
# ---------------------------------------------------------------------------


def test_lock_held_by_another_process_blocks_start_and_interrupted_marking(env, nightly):
    engine = env["engine"]
    store = st.AuditorStore(engine)
    other_run = uuid.uuid4().hex
    store.create_run(other_run, "external", "t")         # corsa viva di un altro processo
    other = PgAdvisoryLock(engine, st.AUDITOR_LOCK_KEY)
    assert other.acquire()
    try:
        service = _service(env)
        result = service.start_in_background("external")
        assert isinstance(result, st.AlreadyRunning) and result.run_id == other_run
        assert service.mark_interrupted_runs() == 0
        assert store.get_run(other_run)["status"] == "running"
    finally:
        other.release()
    # Il processo è morto (lock libero): al riavvio la corsa diventa 'interrupted'.
    service = _service(env)
    assert service.mark_interrupted_runs() == 1
    stale = store.get_run(other_run)
    assert stale["status"] == "interrupted" and stale["finished_at"] is not None
    payload = service.status_payload()
    assert payload["running"] is None and payload["last_run"]["status"] == "interrupted"
    # Le letture per l'utente ignorano le corse interrotte.
    assert store.latest_results_for_portfolios([9101])["run"]["run_id"] == nightly["run_uuid"]


def test_failed_users_and_deleted_portfolios(env):
    """Un utente che fallisce non ferma gli altri; un portafoglio cancellato durante la corsa è ignorato."""
    engine = env["engine"]
    with engine.begin() as conn:
        conn.execute(text("insert into portfolios (id, name, base_currency, owner_user_id, cash_balance) "
                          "values (9190, 'tmp', 'EUR', 'auditor-tmp-user', 0)"))
    calls = []

    def audit(deps, rules, user_id, run_uuid, options):
        calls.append(user_id)
        if user_id == USER:
            raise RuntimeError("simulato")
        with engine.begin() as conn:  # cancellato durante la valutazione
            conn.execute(text("delete from portfolios where id = 9190"))
        return {"results": [{"rule_id": "D-WEIGHTS-SUM", "severity": "P1", "status": "pass",
                             "scope": {"kind": "portfolio", "portfolio_id": 9190}}],
                "scopes": [{"scope": {"kind": "portfolio", "portfolio_id": 9190}}],
                "counts": {"by_status": {"pass": 1, "fail": 0, "skip": 0, "error": 0}},
                "tool_calls": {"total": 1}, "deadline_exceeded": False}

    service = _service(env, audit_user=audit)
    outcome = service.run_now("manual")
    assert sorted(calls) == sorted(["auditor-tmp-user", USER])
    assert outcome.status == "completed_with_failures" and outcome.users_failed == 1
    run = service.store.get_run(outcome.run_id)
    assert run["status"] == "completed_with_failures" and run["users_total"] == 2
    assert _rows(engine, "select * from auditor_results where run_id = :id", id=run["id"]) == []
