"""Doctor 2.0 policies against a real PostgreSQL 16 (throwaway cluster).

Runs store + confirmation tokens + DoctorPolicyService + REST routes on the
real schema (database/schema.sql + migrations) and the real
PortfolioRepository. Skipped when the Postgres binaries are missing (see
tests/integration/conftest.py).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.routes_doctor import register_doctor_routes
from app.auth import AuthContext
from app.errors import AppError
from app.rate_limit import require_auth_rate_limited
from app.repository import PortfolioRepository
from app.services.doctor_policy import confirmation
from app.services.doctor_policy.errors import ConfirmationInvalid, NotFound, VersionConflict
from app.services.doctor_policy.service import DoctorPolicyService
from app.services.doctor_policy.store import DoctorPolicyStore, StoreVersionConflict
from app.sql import load_sql

ALICE = "user_alice"
BOB = "user_bob"

DOC_35 = {
    "schema_version": 1,
    "rules": [{"rule_id": "max-single", "metric_code": "max_single_position_pct", "operator": "max", "max_value": 35}],
}
DOC_40 = {
    "schema_version": 1,
    "rules": [
        {"rule_id": "max-single", "metric_code": "max_single_position_pct", "operator": "max", "max_value": 40},
        {"rule_id": "equity", "metric_code": "equity_weight_pct", "operator": "range", "min_value": 50, "max_value": 90},
    ],
}
DOC_EMPTY = {"schema_version": 1, "rules": []}

PROTECTED_TABLES = (
    "portfolios", "assets", "transactions", "price_ticks", "price_bars_1d", "price_bars_1m",
    "fx_rates_1d", "portfolio_target_allocations", "pac_rules", "pac_executions",
)


@pytest.fixture(scope="module")
def world(pg_engine):
    """Seed users, portfolios, assets, transactions and fresh prices once."""
    now = datetime.now(timezone.utc)
    with pg_engine.begin() as conn:
        # The startup copy of the migration is idempotent on top of the schema.
        conn.execute(text(load_sql("migrations/create_doctor_policies")))
        conn.execute(text(load_sql("migrations/create_doctor_policies")))

        def portfolio(name, owner, ccy="EUR"):
            return conn.execute(
                text(
                    "insert into portfolios (name, base_currency, owner_user_id) values (:n, :c, :o) returning id"
                ),
                {"n": name, "c": ccy, "o": owner},
            ).scalar_one()

        def asset(symbol, asset_type, isin):
            return conn.execute(
                text(
                    "insert into assets (symbol, name, asset_type, exchange_code, quote_currency, isin) "
                    "values (:s, :s, :t, 'XAMS', 'EUR', :i) returning id"
                ),
                {"s": symbol, "t": asset_type, "i": isin},
            ).scalar_one()

        ids = {
            "parent": portfolio("Parent", ALICE),
            "wealth": portfolio("Wealth", ALICE),
            "usd": portfolio("Dollari", ALICE, "USD"),
            "bob": portfolio("Bob", BOB),
            "doomed": portfolio("Da cancellare", ALICE),
        }
        vwra = asset("VWRA", "etf", "IE00BK5BQT80")
        agg = asset("AGGH", "etf", "IE00BDBRDM35")
        for pid_key, asset_id, qty in (("parent", vwra, 10), ("parent", agg, 5), ("wealth", vwra, 3), ("bob", vwra, 1), ("doomed", agg, 2)):
            conn.execute(
                text(
                    "insert into transactions (portfolio_id, asset_id, side, trade_at, quantity, price, trade_currency, owner_user_id) "
                    "values (:p, :a, 'buy', :t, :q, 100, 'EUR', (select owner_user_id from portfolios where id = :p))"
                ),
                {"p": ids[pid_key], "a": asset_id, "t": now - timedelta(days=30), "q": qty},
            )
        for asset_id, price in ((vwra, 120), (agg, 95)):
            conn.execute(
                text("insert into price_ticks (asset_id, provider, ts, last) values (:a, 'yfinance', :ts, :p)"),
                {"a": asset_id, "ts": now - timedelta(hours=1), "p": price},
            )
    return {"engine": pg_engine, "ids": ids}


@pytest.fixture()
def env(world):
    engine = world["engine"]
    with engine.begin() as conn:
        conn.execute(text(
            "truncate doctor_confirmation_tokens, doctor_policy_versions, doctor_policy_scope_members, "
            "doctor_policy_sets restart identity cascade"
        ))
    repo = PortfolioRepository(engine)
    service = DoctorPolicyService(repo)
    return {**world, "repo": repo, "service": service}


@pytest.fixture()
def client(env):
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _handler(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    def _auth(request: Request) -> AuthContext:
        return AuthContext(user_id=request.headers.get("x-test-user", ALICE))

    class _Settings:
        doctor_policy_enabled = True
        doctor_simulator_enabled = True

    router = APIRouter()
    register_doctor_routes(router, env["repo"], settings=_Settings(), service=env["service"])
    app.include_router(router, prefix="/api")
    app.dependency_overrides[require_auth_rate_limited] = _auth
    return TestClient(app)


def _counts(engine) -> dict[str, int]:
    with engine.connect() as conn:
        return {t: conn.execute(text(f"select count(*) from {t}")).scalar_one() for t in PROTECTED_TABLES}


def _preview(client, ids, doc, base_version=None, user=ALICE, source="manual"):
    r = client.post(
        "/api/doctor/policies/preview",
        json={"portfolio_ids": ids, "document": doc, "base_version": base_version, "source": source},
        headers={"x-test-user": user},
    )
    assert r.status_code == 200, r.text
    return r.json()


def _save(client, ids, doc, base_version, token, user=ALICE, name="Policy"):
    return client.post(
        "/api/doctor/policies",
        json={"portfolio_ids": ids, "name": name, "document": doc, "base_version": base_version, "confirmation_token": token},
        headers={"x-test-user": user},
    )


def _create(client, ids, doc, base_version=None, user=ALICE, source="manual"):
    p = _preview(client, ids, doc, base_version, user, source)
    r = _save(client, ids, doc, base_version, p["confirmation_token"], user)
    assert r.status_code == 201, r.text
    return r.json()


# --- schema / migration ---------------------------------------------------


def test_tables_have_rls_and_unique_index(env):
    with env["engine"].connect() as conn:
        rls = dict(conn.execute(text(
            "select relname, relrowsecurity from pg_class where relname like 'doctor_%' and relkind = 'r'"
        )).all())
        assert rls == {
            "doctor_policy_sets": True, "doctor_policy_scope_members": True,
            "doctor_policy_versions": True, "doctor_confirmation_tokens": True,
        }
        fks = conn.execute(text(
            "select confrelid::regclass::text from pg_constraint "
            "where conrelid = 'doctor_policy_scope_members'::regclass and contype = 'f'"
        )).scalars().all()
        assert fks == ["doctor_policy_sets"]  # no FK to portfolios


# --- create / read / versions --------------------------------------------


def test_create_gives_version_1_and_get_reads_it(client, env):
    pid = env["ids"]["parent"]
    preview = _preview(client, [pid], DOC_35)
    assert preview["valid"] is True
    assert preview["evaluation_before"] is None
    assert preview["evaluation_after"]["status"] == "ready"
    assert [d["change"] for d in preview["diff"]] == ["added"]
    assert preview["confirmation_token"] and preview["document_hash"]

    saved = _save(client, [pid], DOC_35, None, preview["confirmation_token"])
    assert saved.status_code == 201, saved.text
    body = saved.json()
    assert body["current_version"] == 1
    assert body["scope"] == {"portfolio_ids": [pid], "scope_type": "single", "fingerprint": f"p:{pid}"}

    got = client.get(f"/api/doctor/policies?portfolio_id={pid}").json()["policy"]
    assert got["id"] == body["id"] and got["document"]["rules"][0]["max_value"] == 35.0
    evaluation = client.get(f"/api/doctor/evaluation?portfolio_ids={pid}").json()
    assert evaluation["policy_version"] == 1 and evaluation["summary"]["total"] == 1

    with env["engine"].connect() as conn:
        stored = conn.execute(text("select token_hash from doctor_confirmation_tokens")).scalars().all()
    assert preview["confirmation_token"] not in stored  # only the sha256 is stored
    assert confirmation.hash_token(preview["confirmation_token"]) in stored


def test_no_policy_evaluation(client, env):
    pid = env["ids"]["wealth"]
    assert client.get(f"/api/doctor/policies?portfolio_ids={pid}").json() == {"policy": None}
    assert client.get(f"/api/doctor/evaluation?portfolio_ids={pid}").json()["status"] == "no_policy"


def test_two_tabs_stale_base_version_gets_409(client, env):
    """PRD example F: v2 open in two tabs, one saves v3, the other gets 409."""
    pid = env["ids"]["parent"]
    _create(client, [pid], DOC_35)
    p2 = _preview(client, [pid], DOC_40, base_version=1)
    assert _save(client, [pid], DOC_40, 1, p2["confirmation_token"]).json()["current_version"] == 2

    tab_a = _preview(client, [pid], DOC_EMPTY, base_version=2)
    tab_b = _preview(client, [pid], DOC_35, base_version=2)
    assert _save(client, [pid], DOC_EMPTY, 2, tab_a["confirmation_token"]).json()["current_version"] == 3

    r = _save(client, [pid], DOC_35, 2, tab_b["confirmation_token"])
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "version_conflict"
    assert err["details"]["current_version"] == 3 and err["details"]["request_id"]
    assert client.get(f"/api/doctor/policies?portfolio_ids={pid}").json()["policy"]["document"]["rules"] == []


def test_create_twice_with_null_base_conflicts(client, env):
    pid = env["ids"]["parent"]
    a = _preview(client, [pid], DOC_35)
    b = _preview(client, [pid], DOC_40)
    assert _save(client, [pid], DOC_35, None, a["confirmation_token"]).status_code == 201
    r = _save(client, [pid], DOC_40, None, b["confirmation_token"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


def test_versions_diff_and_restore(client, env):
    pid = env["ids"]["parent"]
    policy = _create(client, [pid], DOC_35)
    p = _preview(client, [pid], DOC_40, base_version=1, source="copilot")
    assert [d["change"] for d in p["diff"]] == ["modified", "added"]
    assert p["evaluation_before"]["policy_version"] == 1
    assert p["evaluation_before"]["snapshot_id"] == p["evaluation_after"]["snapshot_id"]
    assert _save(client, [pid], DOC_40, 1, p["confirmation_token"]).status_code == 201

    versions = client.get(f"/api/doctor/policies/{policy['id']}/versions").json()
    assert versions["current_version"] == 2
    assert [v["version_number"] for v in versions["versions"]] == [2, 1]
    assert versions["versions"][0]["source"] == "copilot"
    assert versions["versions"][1]["source"] == "manual"
    assert {d["change"] for d in versions["versions"][0]["diff"]} == {"modified", "added"}
    assert versions["versions"][0]["actor"] == ALICE

    stale = client.post(f"/api/doctor/policies/{policy['id']}/restore", json={"version_number": 1, "base_version": 1})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "version_conflict"
    restored = client.post(f"/api/doctor/policies/{policy['id']}/restore", json={"version_number": 1, "base_version": 2})
    assert restored.status_code == 200, restored.text
    assert restored.json()["current_version"] == 3
    assert restored.json()["document"]["rules"][0]["max_value"] == 35.0
    v3 = client.get(f"/api/doctor/policies/{policy['id']}/versions").json()["versions"][0]
    assert v3["source"] == "restore" and {d["change"] for d in v3["diff"]} == {"modified", "removed"}
    missing = client.post(f"/api/doctor/policies/{policy['id']}/restore", json={"version_number": 9, "base_version": 3})
    assert missing.status_code == 404


# --- confirmation tokens ----------------------------------------------------


def test_token_is_one_shot(client, env):
    pid = env["ids"]["parent"]
    p = _preview(client, [pid], DOC_35)
    assert _save(client, [pid], DOC_35, None, p["confirmation_token"]).status_code == 201
    # Reuse for the next version (right base): already used.
    r = _save(client, [pid], DOC_35, 1, p["confirmation_token"])
    assert r.status_code == 409 and r.json()["error"]["code"] == "confirmation_invalid"


def test_token_bound_to_document_scope_base_and_user(client, env):
    parent, wealth = env["ids"]["parent"], env["ids"]["wealth"]
    p = _preview(client, [parent], DOC_35)
    token = p["confirmation_token"]
    for ids, doc, base, user in (
        ([parent], DOC_40, None, ALICE),          # other document
        ([wealth], DOC_35, None, ALICE),          # other scope
        ([parent, wealth], DOC_35, None, ALICE),  # aggregate scope
        ([parent], DOC_35, 0, ALICE),             # other base_version
    ):
        r = _save(client, ids, doc, base, token, user=user)
        assert r.status_code == 409, (ids, doc, base, r.text)
        assert r.json()["error"]["code"] == "confirmation_invalid"
    # Another user cannot even reach the scope.
    assert _save(client, [parent], DOC_35, None, token, user=BOB).status_code == 404
    # Missing token.
    r = _save(client, [parent], DOC_35, None, "")
    assert r.status_code == 409 and r.json()["error"]["code"] == "confirmation_invalid"
    # Still valid for the exact binding (failed attempts did not burn it);
    # an equivalent document (35 vs 35.0, defaults spelled out) hashes the same.
    equivalent = {"schema_version": 1, "rules": [dict(DOC_35["rules"][0], max_value=35.0, enabled=True)]}
    assert _save(client, [parent], equivalent, None, token).status_code == 201


def test_expired_token_fails(env):
    pid = env["ids"]["parent"]
    service: DoctorPolicyService = env["service"]
    from app.services.doctor_policy import document_hash, normalize_policy_document

    doc_hash = document_hash(normalize_policy_document(DOC_35))
    issued = confirmation.issue_token(
        env["engine"], user_id=ALICE, scope_fingerprint=f"p:{pid}", document_hash=doc_hash,
        base_version=None, ttl=timedelta(seconds=-1),
    )
    with pytest.raises(ConfirmationInvalid):
        service.save(ALICE, [pid], name="x", document=DOC_35, base_version=None, confirmation_token=issued.token)


def test_failed_save_does_not_consume_token(env):
    """A version conflict rolls back the token consumption."""
    pid = env["ids"]["parent"]
    service: DoctorPolicyService = env["service"]
    first = service.preview(ALICE, [pid], DOC_35)
    stale = service.preview(ALICE, [pid], DOC_40)
    service.save(ALICE, [pid], name="x", document=DOC_35, base_version=None, confirmation_token=first.confirmation_token)
    with pytest.raises(VersionConflict):
        service.save(ALICE, [pid], name="x", document=DOC_40, base_version=None, confirmation_token=stale.confirmation_token)
    with env["engine"].connect() as conn:
        used = conn.execute(
            text("select used_at from doctor_confirmation_tokens where token_hash = :h"),
            {"h": confirmation.hash_token(stale.confirmation_token)},
        ).scalar_one()
    assert used is None


def test_invalid_preview_has_no_token(client, env):
    pid = env["ids"]["parent"]
    bad = {"schema_version": 1, "rules": [
        {"rule_id": "eq", "metric_code": "equity_weight_pct", "operator": "min", "min_value": 55},
        {"rule_id": "bd", "metric_code": "bond_weight_pct", "operator": "min", "min_value": 50},
        {"rule_id": "gd", "metric_code": "gold_weight_pct", "operator": "min", "min_value": 10},
    ]}
    p = _preview(client, [pid], bad)
    assert p["valid"] is False and p["confirmation_token"] is None and p["field_errors"]
    v = client.post("/api/doctor/policies/validate", json={"portfolio_ids": [pid], "document": bad}).json()
    assert v["valid"] is False and any(e["code"] == "infeasible" for e in v["field_errors"])
    r = _save(client, [pid], bad, None, "whatever")
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"
    assert r.json()["error"]["details"]["field_errors"]


# --- authorization / scope ------------------------------------------------


def test_cross_user_access_is_404(client, env):
    parent = env["ids"]["parent"]
    policy = _create(client, [parent], DOC_35)
    for r in (
        client.get(f"/api/doctor/policies?portfolio_ids={parent}", headers={"x-test-user": BOB}),
        client.get(f"/api/doctor/evaluation?portfolio_ids={parent}", headers={"x-test-user": BOB}),
        client.get(f"/api/doctor/policies/{policy['id']}/versions", headers={"x-test-user": BOB}),
        client.post(f"/api/doctor/policies/{policy['id']}/restore", json={"version_number": 1, "base_version": 1},
                    headers={"x-test-user": BOB}),
        client.post("/api/doctor/policies/preview", json={"portfolio_ids": [parent], "document": DOC_35},
                    headers={"x-test-user": BOB}),
    ):
        assert r.status_code == 404, r.text
        assert r.json()["error"]["code"] == "not_found"


def test_aggregate_with_unowned_member_is_404(client, env):
    parent, bob = env["ids"]["parent"], env["ids"]["bob"]
    r = client.get(f"/api/doctor/policies?portfolio_ids={parent}&portfolio_ids={bob}")
    assert r.status_code == 404
    r = client.post("/api/doctor/policies/preview", json={"portfolio_ids": [parent, bob], "document": DOC_35})
    assert r.status_code == 404


def test_aggregate_policy_independent_from_single(client, env):
    """PRD example H: Parent+Wealth policy stored apart; single policies untouched."""
    parent, wealth = env["ids"]["parent"], env["ids"]["wealth"]
    single = _create(client, [parent], DOC_35)
    aggregate = _create(client, [wealth, parent, parent], DOC_40)
    assert aggregate["id"] != single["id"]
    assert aggregate["scope"] == {
        "portfolio_ids": sorted([parent, wealth]), "scope_type": "aggregate",
        "fingerprint": f"p:{min(parent, wealth)},{max(parent, wealth)}",
    }
    assert client.get(f"/api/doctor/policies?portfolio_ids={parent}").json()["policy"]["document"]["rules"][0]["max_value"] == 35.0
    assert client.get(f"/api/doctor/policies?portfolio_ids={wealth}").json()["policy"] is None
    agg = client.get(f"/api/doctor/policies?portfolio_ids={parent}&portfolio_ids={wealth}").json()["policy"]
    assert agg["id"] == aggregate["id"] and len(agg["document"]["rules"]) == 2
    evaluation = client.get(f"/api/doctor/evaluation?portfolio_ids={wealth}&portfolio_ids={parent}").json()
    assert evaluation["policy_id"] == aggregate["id"] and evaluation["scope"]["scope_type"] == "aggregate"


def test_mixed_currency_and_too_many_and_malformed_are_400(client, env):
    parent, usd = env["ids"]["parent"], env["ids"]["usd"]
    assert client.get(f"/api/doctor/policies?portfolio_ids={parent}&portfolio_ids={usd}").status_code == 400
    many = "&".join(f"portfolio_ids={i}" for i in range(1, 23))
    r = client.get(f"/api/doctor/policies?{many}")
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"
    r = client.post("/api/doctor/policies/preview", json={"portfolio_ids": list(range(1, 23)), "document": DOC_35})
    assert r.status_code == 400
    assert client.get("/api/doctor/policies").status_code == 400
    assert client.get("/api/doctor/policies?portfolio_ids=abc").status_code == 400
    r = client.post("/api/doctor/policies/validate", json={"portfolio_ids": [parent], "document": "nope"})
    assert r.status_code == 400 and r.json()["error"]["details"]["field_errors"]
    r = client.post("/api/doctor/policies/validate", content=b"[1,2]", headers={"content-type": "application/json"})
    assert r.status_code == 400
    r = client.post(f"/api/doctor/policies/1/restore", json={"version_number": 0})
    assert r.status_code == 400


def test_deleted_portfolio_makes_aggregate_unreadable(client, env):
    parent, doomed = env["ids"]["parent"], env["ids"]["doomed"]
    aggregate = _create(client, [parent, doomed], DOC_35)
    with env["engine"].begin() as conn:
        conn.execute(text("delete from portfolios where id = :id"), {"id": doomed})
    try:
        assert client.get(f"/api/doctor/policies/{aggregate['id']}/versions").status_code == 404
        assert client.get(f"/api/doctor/policies?portfolio_ids={parent}&portfolio_ids={doomed}").status_code == 404
        assert client.get(f"/api/doctor/evaluation?portfolio_ids={parent}&portfolio_ids={doomed}").status_code == 404
        r = client.post(f"/api/doctor/policies/{aggregate['id']}/restore", json={"version_number": 1, "base_version": 1})
        assert r.status_code == 404
        # The members are still there (no FK cascade), the policy is just unreadable.
        with env["engine"].connect() as conn:
            members = conn.execute(
                text("select count(*) from doctor_policy_scope_members where policy_set_id = :id"),
                {"id": aggregate["id"]},
            ).scalar_one()
        assert members == 2
    finally:
        with env["engine"].begin() as conn:
            conn.execute(
                text("insert into portfolios (id, name, base_currency, owner_user_id) values (:id, 'Da cancellare', 'EUR', :o)"),
                {"id": doomed, "o": ALICE},
            )


def test_doctor_endpoints_do_not_touch_portfolio_data(client, env):
    parent, wealth = env["ids"]["parent"], env["ids"]["wealth"]
    before = _counts(env["engine"])
    policy = _create(client, [parent], DOC_35)
    p = _preview(client, [parent], DOC_40, base_version=1)
    _save(client, [parent], DOC_40, 1, p["confirmation_token"])
    client.post(f"/api/doctor/policies/{policy['id']}/restore", json={"version_number": 1, "base_version": 2})
    client.get(f"/api/doctor/evaluation?portfolio_ids={parent}&portfolio_ids={wealth}")
    client.get(f"/api/doctor/policies/{policy['id']}/versions")
    client.post("/api/doctor/policies/validate", json={"portfolio_ids": [parent], "document": DOC_35})
    client.get("/api/doctor/metrics")
    client.get("/api/doctor/templates")
    assert _counts(env["engine"]) == before


# --- store level ----------------------------------------------------------


def test_store_locking_rules(env):
    store = DoctorPolicyStore(env["engine"])
    kw = dict(
        owner_user_id=ALICE, scope_type="single", scope_fingerprint="p:999999", portfolio_ids=[999999],
        name="S", document=DOC_EMPTY, document_hash="h", schema_version=1, source="manual", diff=[],
    )
    with pytest.raises(StoreVersionConflict):
        store.save_version(base_version=1, **kw)  # nothing to update
    rec = store.save_version(base_version=None, **kw)
    assert rec.current_version == 1 and rec.portfolio_ids == (999999,)
    with pytest.raises(StoreVersionConflict) as info:
        store.save_version(base_version=None, **kw)
    assert info.value.current_version == 1
    assert store.save_version(base_version=1, **{**kw, "name": None}).current_version == 2
    assert store.get_policy_set(ALICE, "p:999999").name == "S"
    assert store.get_policy_set_by_id(BOB, rec.id) is None
    assert store.archive(ALICE, rec.id) is True
    assert store.get_policy_set(ALICE, "p:999999") is None
    # Archived: the scope is free again (partial unique index).
    assert store.save_version(base_version=None, **kw).current_version == 1


def test_service_not_found_for_unknown_policy(env):
    with pytest.raises(NotFound):
        env["service"].list_versions(ALICE, 123456)
