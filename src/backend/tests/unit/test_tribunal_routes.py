"""REST/SSE del Tribunale (TASK-65, docs/tribunale/api-contracts.md §2, §3, §9).

App FastAPI di test con l'orchestratore reale, LLM finto (risposte ``raw`` della fixture),
servizio del Doctor e repository finti. Nessuna chiamata di rete.
"""

from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.routes_doctor import register_doctor_routes
from app.api.routes_tribunal import register_tribunal_routes
from app.auth import AuthContext
from app.errors import AppError
from app.rate_limit import require_auth_rate_limited
from app.services.tribunal import orchestrator as orch_module
from app.services.tribunal.orchestrator import TribunalOrchestrator
from tests.unit.test_tribunal_orchestrator import (
    FIXTURE,
    USER,
    CaseFileBuilder,
    FakeLLM,
    FakeRepo,
    FakeService,
    RecordingStore,
    canonical_order,
    check_grammar,
    fixture_events,
    make_settings,
    normalize,
    parse_sse,
)

NOW = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)


class _Env:
    def __init__(self) -> None:
        self.settings = make_settings()
        self.llm = FakeLLM()
        self.store = RecordingStore()
        self.builder = CaseFileBuilder()
        self.service = FakeService()
        self.user = USER
        self.orchestrator = TribunalOrchestrator(
            FakeRepo(), self.settings, store=self.store, llm_call=self.llm,
            service_getter=lambda: self.service, case_file_builder=self.builder, clock=lambda: NOW,
        )
        app = FastAPI()

        @app.exception_handler(AppError)
        async def _handler(_: Request, exc: AppError):
            return JSONResponse(
                status_code=exc.status_code,
                content={"error": {"code": exc.code, "message": exc.message, "details": exc.details}},
            )

        router = APIRouter()
        register_doctor_routes(router, repo=None, settings=self.settings, service_getter=lambda: self.service)
        register_tribunal_routes(router, None, settings=self.settings, orchestrator_getter=lambda: self.orchestrator)
        app.include_router(router, prefix="/api")
        app.dependency_overrides[require_auth_rate_limited] = lambda: AuthContext(user_id=self.user)
        self.client = TestClient(app)


@pytest.fixture()
def env():
    yield _Env()
    orch_module._LOCKS._active.clear()


def _events(response):
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    events, _ = parse_sse([response.text])
    return events


def test_post_single_scope_streams_fixture_session(env):
    events = _events(env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]}))
    check_grammar(events)
    assert normalize(canonical_order(events)) == normalize(canonical_order(fixture_events()))
    assert len(env.store.saved) == 1


def test_post_portfolio_id_and_aggregate_scope(env):
    events = _events(env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_id": 19}))
    assert events[0]["content"]["scope"]["fingerprint"] == "p:19" and events[-1]["type"] == "done"
    events = _events(env.client.post("/api/doctor/tribunal/sessions",
                                     json={"portfolio_ids": [26, 19], "force_new": True}))
    check_grammar(events)
    assert events[0]["content"]["scope"] == {"portfolio_ids": [19, 26], "scope_type": "aggregate",
                                             "fingerprint": "p:19,26"}
    assert events[1]["content"]["notes"][0] == "Vista aggregata di 2 portafogli."
    assert events[-1]["type"] == "done"


def test_feature_disabled_on_all_endpoints_and_features(env):
    assert env.client.get("/api/doctor/features").json()["tribunal_enabled"] is True
    env.settings.doctor_tribunal_enabled = False
    assert env.client.get("/api/doctor/features").json() == {
        "policy_enabled": True, "simulator_enabled": True, "tribunal_enabled": False,
    }
    for r in (
        env.client.get("/api/doctor/tribunal/status?portfolio_ids=19"),
        env.client.get("/api/doctor/tribunal/sessions/latest?portfolio_ids=19"),
        env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]}),
        env.client.post("/api/doctor/tribunal/sessions", json={"bogus": 1}),   # flag prima del corpo
    ):
        assert r.status_code == 404
        err = r.json()["error"]
        assert err["code"] == "feature_disabled" and err["details"]["retryable"] is False
        assert err["details"]["request_id"]
    assert env.llm.calls == [] and env.builder.calls == []


def test_scope_of_another_user_is_404_not_found(env):
    for r in (
        env.client.get("/api/doctor/tribunal/status?portfolio_ids=19&portfolio_ids=99"),
        env.client.get("/api/doctor/tribunal/sessions/latest?portfolio_id=99"),
        env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [99]}),
    ):
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    env.user = "intruder"
    r = env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]})
    assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"
    assert env.llm.calls == [] and env.builder.calls == []


@pytest.mark.parametrize("body", [
    {"portfolio_ids": [19], "extra": 1},
    {"portfolio_ids": [19], "force_new": "yes"},
    {"portfolio_ids": ["x"]},
    {"portfolio_ids": []},
    {"portfolio_ids": [0]},
    [19],
])
def test_invalid_body_is_400(env, body):
    r = env.client.post("/api/doctor/tribunal/sessions", json=body, headers={"x-request-id": "req-1"})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "invalid_request" and err["details"]["request_id"] == "req-1"
    assert "field_errors" in err["details"]


def test_invalid_query_scope_is_400(env):
    for q in ("portfolio_ids=abc", "portfolio_ids=19,30", ""):
        r = env.client.get(f"/api/doctor/tribunal/status?{q}")
        assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


def test_status_endpoint(env):
    r = env.client.get("/api/doctor/tribunal/status?portfolio_ids=19,26")
    assert r.status_code == 200
    assert r.json() == {
        "available": True, "reason": None, "message": None, "provider": "openai", "model": "gpt-4o-mini",
        "key_source": "server",
        "limit": {"daily_limit": 3, "used_today": 0, "remaining": 3, "resets_at": "2026-11-10T23:00:00Z"},
        "scope": {"portfolio_ids": [19, 26], "scope_type": "aggregate", "fingerprint": "p:19,26"},
    }
    assert env.builder.calls == [] and env.llm.calls == []   # niente fascicolo né modello
    env.settings.copilot_provider = "local"
    assert env.client.get("/api/doctor/tribunal/status?portfolio_id=19").json()["reason"] == "provider_not_supported"


def test_latest_endpoint_null_and_saved(env):
    r = env.client.get("/api/doctor/tribunal/sessions/latest?portfolio_ids=19")
    assert r.json() == {"session": None, "current_case_file_hash": None, "data_changed": None}
    env.store.latest = copy.deepcopy(FIXTURE["session"])
    body = env.client.get("/api/doctor/tribunal/sessions/latest?portfolio_ids=19").json()
    assert body["session"]["session_id"] == FIXTURE["session"]["session_id"]
    assert body["data_changed"] is False


def test_pre_stream_errors(env):
    env.settings.copilot_provider = ""
    r = env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]})
    assert (r.status_code, r.json()["error"]["code"]) == (503, "copilot_unavailable")
    env.settings.copilot_provider = "local"
    r = env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "provider_not_supported")
    assert r.json()["error"]["details"]["provider"] == "local"
    env.settings.copilot_provider = "openai"
    env.builder.case_file["counts"] = {"total": 37, "citable": 2}
    r = env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]})
    assert (r.status_code, r.json()["error"]["code"]) == (409, "insufficient_data")
    assert r.json()["error"]["details"]["citable_facts"] == 2


def test_session_in_progress_is_409(env):
    stream = env.orchestrator.start(USER, [26])
    r = env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]})
    assert r.status_code == 409
    err = r.json()["error"]
    assert err["code"] == "session_in_progress" and err["details"]["retryable"] is True
    stream.close()
    assert env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]}).status_code == 200


def test_daily_limit_429_with_retry_after_and_replay_still_served(env):
    env.store.used_today = 3
    r = env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]})
    assert r.status_code == 429
    assert r.headers["retry-after"] == str(9 * 3600)
    err = r.json()["error"]
    assert err["code"] == "daily_limit_reached" and err["details"]["retryable"] is False
    assert err["details"]["daily_limit"] == 3 and err["details"]["used_today"] == 3
    assert err["details"]["resets_at"] == "2026-11-10T23:00:00Z" and err["details"]["request_id"]
    st = env.client.get("/api/doctor/tribunal/status?portfolio_ids=19").json()
    assert (st["available"], st["reason"]) == (False, "daily_limit_reached")
    # Fascicolo invariato: la seduta salvata viene riprodotta anche a limite esaurito.
    env.store.latest = copy.deepcopy(FIXTURE["session"])
    events = _events(env.client.post("/api/doctor/tribunal/sessions", json={"portfolio_ids": [19]}))
    assert events[0]["content"]["reused"] is True and events[-1]["content"]["reused"] is True
    assert env.llm.calls == []
