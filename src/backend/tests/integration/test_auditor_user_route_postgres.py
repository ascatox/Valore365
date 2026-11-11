"""TASK-81: endpoint utente dell'Auditor (``GET /api/doctor/auditor/summary``) su un PostgreSQL 16 reale.

Database dedicato del cluster della fixture ``pg_engine`` (schema, migrazioni, copia di avvio di
``create_auditor.sql``), con ``PortfolioRepository`` e ``AuditorStore`` veri e il registro reale
delle regole. Verifica:

- proprietà dello scope singolo e aggregato con le query vere (portafoglio altrui → 404, valute
  diverse → 400);
- solo l'ultima corsa **conclusa** conta (una ``failed``, una ``interrupted`` e una ``running``
  più recenti sono ignorate);
- esito peggiore per regola sull'unione delle righe dell'aggregato, ``skip``/``error`` esclusi;
- regola delle 48 ore sulla ``finished_at`` salvata;
- nessun id di regola, severità, id della corsa o del portafoglio nel payload.

Saltato quando i binari di Postgres mancano.
"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text

from app.api.routes_auditor_user import register_auditor_user_routes, unavailable
from app.auth import AuthContext, require_auth
from app.errors import AppError
from app.repository import PortfolioRepository
from app.services.auditor.registry import AREAS, RULE_ID_PATTERN, load_rules
from app.services.auditor.store import AuditorStore

REPO_ROOT = Path(__file__).resolve().parents[4]
DATABASE_DIR = REPO_ROOT / "database"
DB_NAME = "auditor_user_route"
PATH = "/api/doctor/auditor/summary"
OWNER = "auditor-user-a"
OTHER = "auditor-user-b"


def _psql_base(pg_engine) -> list[str]:
    url = pg_engine.url
    return ["psql", "-q", "-h", url.query["host"], "-p", str(url.query.get("port") or url.port),
            "-U", "postgres", "-v", "ON_ERROR_STOP=1"]


def _run_psql(psql: list[str], *args: str) -> None:
    subprocess.run([*psql, *args], check=True, capture_output=True, text=True, cwd="/")


@pytest.fixture(scope="module")
def engine(pg_engine):
    psql = _psql_base(pg_engine)
    _run_psql(psql, "-d", "postgres", "-c", f"drop database if exists {DB_NAME}")
    _run_psql(psql, "-d", "postgres", "-c", f"create database {DB_NAME}")
    _run_psql(psql, "-d", DB_NAME, "-f", str(DATABASE_DIR / "schema.sql"))
    for migration in sorted((DATABASE_DIR / "migrations").glob("*.sql")):
        _run_psql(psql, "-d", DB_NAME, "-f", str(migration))
    _run_psql(psql, "-d", DB_NAME, "-f", str(REPO_ROOT / "src/backend/app/sql/migrations/create_auditor.sql"))
    url = pg_engine.url
    eng = create_engine(
        f"postgresql+psycopg://postgres@/{DB_NAME}?host={url.query['host']}&port={url.query.get('port') or url.port}",
        pool_size=3, max_overflow=2,
    )
    yield eng
    eng.dispose()
    subprocess.run([*psql, "-d", "postgres", "-c", f"drop database if exists {DB_NAME}"], capture_output=True, cwd="/")


RULES = {r.id: r for r in load_rules()}
PAC = "B-PAC-SUM"
STRESS = "A-STRESS-CONTRIB-SUM"
AGG = "D-AGG-SUMS"
COST = "C-COST-COHERENCE"
WEIGHTS = "D-WEIGHTS-SUM"


def _insert_run(conn, uuid_hex: str, status: str, started: str, finished: str | None) -> int:
    return conn.execute(
        text(
            "insert into auditor_runs (run_uuid, status, trigger, app_version, started_at, finished_at) "
            "values (:u, :s, 'external', 'test', cast(:st as timestamptz), cast(:fi as timestamptz)) returning id"
        ),
        {"u": uuid_hex, "s": status, "st": started, "fi": finished},
    ).scalar_one()


def _insert_results(conn, run_id: int, rows: list[tuple[int, str, str, str]]) -> None:
    for pid, rule_id, scope_kind, status in rows:
        conn.execute(
            text(
                "insert into auditor_results (run_id, portfolio_id, rule_id, scope_kind, status, severity) "
                "values (:r, :p, :rule, :k, :s, :sev)"
            ),
            {"r": run_id, "p": pid, "rule": rule_id, "k": scope_kind, "s": status, "sev": RULES[rule_id].severity},
        )


@pytest.fixture(scope="module")
def data(engine):
    for rule_id in (PAC, STRESS, AGG, COST, WEIGHTS):
        assert rule_id in RULES, rule_id
    with engine.begin() as conn:
        conn.execute(text("delete from auditor_runs"))
        ids = {}
        for key, owner, currency in (("a1", OWNER, "EUR"), ("a2", OWNER, "EUR"), ("a3", OWNER, "USD"), ("b1", OTHER, "EUR")):
            ids[key] = conn.execute(
                text("insert into portfolios (name, base_currency, owner_user_id) values (:n, :c, :o) returning id"),
                {"n": f"Portafoglio {key}", "c": currency, "o": owner},
            ).scalar_one()
        a1, a2, b1 = ids["a1"], ids["a2"], ids["b1"]
        old = _insert_run(conn, "1" * 32, "success", "2026-11-08T23:35:00+00", "2026-11-09T00:10:00+00")
        _insert_results(conn, old, [(a1, PAC, "portfolio", "fail")])
        latest = _insert_run(conn, "2" * 32, "completed_with_failures", "2026-11-10T23:35:00+00",
                             "2026-11-11T00:05:00+00")
        _insert_results(conn, latest, [
            (a1, PAC, "portfolio", "pass"), (a1, STRESS, "portfolio", "pass"), (a1, COST, "portfolio", "skip"),
            (a1, WEIGHTS, "portfolio", "error"), (a1, AGG, "aggregate", "pass"),
            (a2, PAC, "portfolio", "fail"), (a2, STRESS, "portfolio", "pass"), (a2, AGG, "aggregate", "pass"),
            (b1, STRESS, "portfolio", "fail"),
        ])
        # Corse più recenti che non devono contare per l'utente.
        failed = _insert_run(conn, "3" * 32, "failed", "2026-11-11T01:00:00+00", "2026-11-11T01:01:00+00")
        _insert_results(conn, failed, [(a1, STRESS, "portfolio", "fail")])
        interrupted = _insert_run(conn, "4" * 32, "interrupted", "2026-11-11T02:00:00+00", "2026-11-11T02:30:00+00")
        _insert_results(conn, interrupted, [(a1, PAC, "portfolio", "fail")])
        _insert_run(conn, "5" * 32, "running", "2026-11-11T03:00:00+00", None)
    return ids


def _client(engine, *, user=OWNER, now=None):
    from datetime import UTC, datetime

    now = now or datetime(2026, 11, 11, 9, 0, tzinfo=UTC)
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _app_error(_request, exc: AppError):
        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code}})

    router = APIRouter()
    register_auditor_user_routes(
        router, PortfolioRepository(engine), store_getter=lambda: AuditorStore(engine), now=lambda: now,
    )
    app.include_router(router, prefix="/api")
    app.dependency_overrides[require_auth] = lambda: AuthContext(user_id=user, org_id=None, email=None, claims={})
    return TestClient(app)


def _no_internals(body: dict) -> None:
    dumped = json.dumps(body)
    assert not re.search(RULE_ID_PATTERN.strip("^$"), dumped)
    for forbidden in ("rule_id", "severity", "run_id", "portfolio_id", "1" * 32, "2" * 32):
        assert forbidden not in dumped


def test_single_portfolio_uses_the_latest_concluded_run(engine, data):
    body = _client(engine).get(PATH, params={"portfolio_id": data["a1"]}).json()
    assert body["available"] is True
    assert body["run_finished_at"] == "2026-11-11T00:05:00+00:00"
    # pass: PAC, STRESS, AGG; skip (COST) ed error (WEIGHTS) non contano; failed/interrupted ignorate.
    assert (body["checks_passed"], body["checks_in_review"]) == (3, 0)
    titles = {c["title"] for a in body["areas"] for c in a["checks"]}
    assert titles == {RULES[PAC].title, RULES[STRESS].title, RULES[AGG].title}
    assert {a["label"] for a in body["areas"]} == {AREAS[RULES[r].area] for r in (PAC, STRESS, AGG)}
    _no_internals(body)


def test_aggregate_is_the_union_with_the_worst_outcome(engine, data):
    body = _client(engine).get(PATH, params={"portfolio_ids": f"{data['a2']},{data['a1']}"}).json()
    assert (body["checks_passed"], body["checks_in_review"]) == (2, 1)
    first = body["areas"][0]
    assert first["label"] == AREAS[RULES[PAC].area] and first["status"] == "in_review"
    assert {"title": RULES[PAC].title, "status": "in_review"} in first["checks"]
    _no_internals(body)


def test_other_users_portfolio_is_404_and_mixed_currency_400(engine, data):
    client = _client(engine)
    assert client.get(PATH, params={"portfolio_id": data["b1"]}).status_code == 404
    assert client.get(PATH, params={"portfolio_ids": f"{data['a1']},{data['b1']}"}).status_code == 404
    assert client.get(PATH, params={"portfolio_ids": f"{data['a1']},{data['a3']}"}).status_code == 400
    # Il proprietario di b1 vede solo il suo esito.
    other = _client(engine, user=OTHER).get(PATH, params={"portfolio_id": data["b1"]}).json()
    assert (other["checks_passed"], other["checks_in_review"]) == (0, 1)


def test_48_hours_after_the_finished_at(engine, data):
    from datetime import UTC, datetime

    finished = datetime(2026, 11, 11, 0, 5, tzinfo=UTC)
    ok = _client(engine, now=finished + timedelta(hours=48)).get(PATH, params={"portfolio_id": data["a1"]}).json()
    assert ok["available"] is True
    stale = _client(engine, now=finished + timedelta(hours=48, minutes=1)).get(
        PATH, params={"portfolio_id": data["a1"]},
    ).json()
    assert stale == unavailable()


def test_portfolio_without_rows_is_unavailable(engine, data):
    body = _client(engine).get(PATH, params={"portfolio_id": data["a3"]}).json()
    assert body == unavailable()
