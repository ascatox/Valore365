"""REST /api/doctor/scenarios/preview|compare with the real DoctorPolicyService (fake repo/store)."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.routes_doctor import register_doctor_routes
from app.auth import AuthContext
from app.errors import AppError
from app.rate_limit import require_auth_rate_limited
from app.repository._scope import NOT_FOUND_MESSAGE
from app.services.doctor_policy import service as service_module
from app.services.doctor_policy.service import DoctorPolicyService
from app.services.doctor_policy.store import PolicySetRecord

from test_doctor_scenario import DOC, prd_snapshot  # same rootdir (no packages)

NOW = datetime(2026, 11, 4, tzinfo=UTC)
OWNED = {1: "EUR", 2: "EUR"}


class _Repo:
    def resolve_portfolio_scope(self, ids, user_id):
        if user_id != "u1" or any(i not in OWNED for i in ids):
            raise ValueError(NOT_FOUND_MESSAGE)

    def get_etf_enrichment_bulk(self, ids):
        return {}

    def get_asset_metadata_bulk(self, ids):
        return {}

    @property
    def engine(self):  # the Lab never opens a DB connection
        raise AssertionError("Scenario Lab must not use the database engine")


class _ReadOnlyStore:
    def __init__(self):
        self.records = {}

    def get_policy_set(self, owner, fp, *, conn=None):
        rec = self.records.get(fp)
        return rec if rec and rec.owner_user_id == owner else None

    @contextmanager
    def transaction(self, conn=None):
        raise AssertionError("no transaction in the Lab")
        yield  # pragma: no cover

    def save_version(self, **_kw):
        raise AssertionError("no write in the Lab")


@pytest.fixture()
def env(monkeypatch):
    settings = SimpleNamespace(doctor_policy_enabled=True, doctor_simulator_enabled=True)
    store = _ReadOnlyStore()
    store.records["p:1"] = PolicySetRecord(
        id=7, owner_user_id="u1", scope_type="single", scope_fingerprint="p:1", name="Mia", active=True,
        current_version=3, created_at=NOW, updated_at=NOW, archived_at=None, portfolio_ids=(1,), document=DOC,
    )
    state = {"snapshot_builds": 0, "cash": 0.0}

    def fake_snapshot(_repo, ids, user_id):
        state["snapshot_builds"] += 1
        return prd_snapshot(portfolio_ids=ids, cash=state["cash"])

    def no_token(*_a, **_kw):
        raise AssertionError("the Lab never issues tokens")

    monkeypatch.setattr(service_module, "build_snapshot", fake_snapshot)
    monkeypatch.setattr(service_module, "issue_token", no_token)
    # Fixed clock: prd_snapshot() prices are dated 2026-11-03 (max_data_age_days = 5).
    service = DoctorPolicyService(_Repo(), store=store, clock=lambda: NOW)

    app = FastAPI()

    @app.exception_handler(AppError)
    async def _handler(_: Request, exc: AppError):
        return JSONResponse(
            status_code=exc.status_code,
            content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
        )

    router = APIRouter()
    register_doctor_routes(router, repo=None, settings=settings, service_getter=lambda: service)
    app.include_router(router, prefix="/api")
    user = {"id": "u1"}
    app.dependency_overrides[require_auth_rate_limited] = lambda: AuthContext(user_id=user["id"])
    return SimpleNamespace(client=TestClient(app), app=app, settings=settings, user=user, state=state, service=service)


GOLDEN = {"portfolio_ids": [1], "mode": "new_cash_only", "new_cash": 0, "label": "Solo versamenti"}


def test_preview_golden_over_rest(env):
    r = env.client.post("/api/doctor/scenarios/preview", json=GOLDEN)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["feasible"] is False and body["infeasible_code"] == "insufficient_cash"
    assert round(body["required_new_cash"]) == 227_029
    assert body["label"] == "Solo versamenti"
    assert body["policy_id"] == 7 and body["policy_version"] == 3
    assert body["snapshot_id"] == prd_snapshot().snapshot_id
    assert body["disclaimer"] == "Simulazione teorica; nessun ordine eseguito."
    assert set(body["before"]["metrics"]) >= {"max_single_position_pct", "equity_weight_pct"}
    assert body["before"]["evaluation_summary"]["failed"] == 1

    ok = env.client.post(
        "/api/doctor/scenarios/preview",
        json={**GOLDEN, "new_cash": body["required_new_cash"], "snapshot_id": body["snapshot_id"], "policy_version": 3},
    ).json()
    assert ok["feasible"] is True
    assert [v["rule_id"] for v in ok["violations_resolved"]] == ["max-single"]
    assert set(ok["violations_resolved"][0]) >= {"rule_id", "metric_code", "label", "reason"}
    assert ok["after"]["volatility"]["value"] is None


def test_preview_is_cached_by_input_and_snapshot(env):
    env.client.post("/api/doctor/scenarios/preview", json=GOLDEN)
    env.client.post("/api/doctor/scenarios/preview", json=GOLDEN)
    assert env.service.cache.hits == 1
    env.client.post("/api/doctor/scenarios/preview", json={**GOLDEN, "new_cash": 1})
    assert env.service.cache.hits == 1
    env.state["cash"] = 50.0  # new snapshot -> new key
    env.client.post("/api/doctor/scenarios/preview", json=GOLDEN)
    assert env.service.cache.hits == 1


def test_snapshot_changed_409(env):
    r = env.client.post("/api/doctor/scenarios/preview", json={**GOLDEN, "snapshot_id": "0123456789abcdef"})
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "snapshot_changed"
    assert err["details"]["current_snapshot_id"] == prd_snapshot().snapshot_id
    assert err["details"]["retryable"] is True and err["details"]["request_id"]


def test_policy_version_conflict_409(env):
    r = env.client.post("/api/doctor/scenarios/preview", json={**GOLDEN, "policy_version": 2})
    assert r.status_code == 409 and r.json()["error"]["code"] == "version_conflict"


def test_cross_user_and_unowned_scope_are_404(env):
    env.user["id"] = "intruder"
    r = env.client.post("/api/doctor/scenarios/preview", json=GOLDEN)
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    env.user["id"] = "u1"
    r = env.client.post("/api/doctor/scenarios/compare", json={
        "portfolio_ids": [1, 99], "scenarios": [{"mode": "new_cash_only"}, {"mode": "new_cash_only", "new_cash": 5}],
    })
    assert r.status_code == 404
    assert env.state["snapshot_builds"] == 0


def test_flag_disabled_404(env):
    env.settings.doctor_simulator_enabled = False
    for path in ("/api/doctor/scenarios/preview", "/api/doctor/scenarios/compare"):
        r = env.client.post(path, json=GOLDEN)
        assert r.status_code == 404 and r.json()["error"]["code"] == "feature_disabled"
    assert env.state["snapshot_builds"] == 0


def test_requires_authentication(env, monkeypatch):
    import app.auth as auth_module

    env.app.dependency_overrides.clear()
    monkeypatch.setattr(auth_module, "get_settings", lambda: SimpleNamespace(clerk_auth_enabled=True))
    for path in ("/api/doctor/scenarios/preview", "/api/doctor/scenarios/compare"):
        r = env.client.post(path, json=GOLDEN)
        assert r.status_code == 401 and r.json()["error"]["code"] == "auth_error"
    assert env.state["snapshot_builds"] == 0


@pytest.mark.parametrize("body", [
    [1, 2],
    {"mode": "new_cash_only"},  # no scope
    {**GOLDEN, "new_cash": -1},
    {**GOLDEN, "mode": "manual", "operations": [{"symbol": "NOPE", "action": "buy", "amount": 1}]},
    {**GOLDEN, "unexpected": True},
])
def test_invalid_bodies_are_400(env, body):
    r = env.client.post("/api/doctor/scenarios/preview", json=body)
    assert r.status_code == 400, r.text
    assert r.json()["error"]["code"] == "invalid_request"


@pytest.mark.parametrize("key", ["²", "١", "1²", "9" * 30, "9" * 41, ""])
def test_unusual_target_weight_keys_are_400_field_errors(env, key):
    body = {**GOLDEN, "mode": "rebalance", "target_weights": {key: 10}}
    r = env.client.post("/api/doctor/scenarios/preview", json=body)
    assert r.status_code == 400, r.text
    error = r.json()["error"]
    assert error["code"] == "invalid_request"
    assert error["details"]["field_errors"][0]["field"].startswith("target_weights")


@pytest.mark.parametrize("value", [2_147_483_648, -1])
def test_policy_version_outside_int4_is_400(env, value):
    r = env.client.post("/api/doctor/scenarios/preview", json={**GOLDEN, "policy_version": value})
    assert r.status_code == 400, r.text
    r = env.client.post("/api/doctor/scenarios/compare", json={
        "portfolio_ids": [1], "policy_version": value,
        "scenarios": [{"mode": "new_cash_only"}, {"mode": "new_cash_only", "new_cash": 10}],
    })
    assert r.status_code == 400, r.text


def test_compare_over_rest(env):
    r = env.client.post("/api/doctor/scenarios/compare", json={
        "portfolio_ids": [1],
        "snapshot_id": prd_snapshot().snapshot_id,
        "policy_version": 3,
        "scenarios": [
            {"mode": "rebalance", "target_weights": {"1": 35}, "constraints": {"no_sell": True}, "label": "C"},
            {"mode": "new_cash_only", "new_cash": 230_000, "label": "Versa"},
        ],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert env.state["snapshot_builds"] == 1  # one snapshot for every scenario
    assert {"current", "scenarios", "snapshot_id", "methodology_version", "disclaimer", "ranking"} <= set(body)
    assert set(body["current"]) >= {"metrics", "evaluation_summary"}
    assert [s["label"] for s in body["scenarios"]] == ["C", "Versa"]
    assert body["best_index"] == 1
    bad = env.client.post("/api/doctor/scenarios/compare", json={"portfolio_ids": [1], "scenarios": [{"mode": "new_cash_only"}]})
    assert bad.status_code == 400
    stale = env.client.post("/api/doctor/scenarios/compare", json={
        "portfolio_ids": [1], "snapshot_id": "ffffffffffffffff",
        "scenarios": [{"mode": "new_cash_only"}, {"mode": "new_cash_only", "new_cash": 1}],
    })
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "snapshot_changed"


def test_aggregate_scope_over_rest(env):
    r = env.client.post("/api/doctor/scenarios/preview", json={**GOLDEN, "portfolio_ids": [2, 1]})
    body = r.json()
    assert r.status_code == 200
    assert body["scope"] == {"portfolio_ids": [1, 2], "scope_type": "aggregate", "fingerprint": "p:1,2"}
    assert body["policy_id"] is None  # aggregate policies are independent of the single ones
    swapped = env.client.post("/api/doctor/scenarios/preview", json={**GOLDEN, "portfolio_ids": [1, 2]}).json()
    swapped.pop("calculated_at"), body.pop("calculated_at")
    for side in (swapped, body):
        for rr in side["before"]["rule_results"]:
            rr["evidence"].pop("calculated_at")
    assert swapped == body
