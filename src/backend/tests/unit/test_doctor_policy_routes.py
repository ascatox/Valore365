"""Doctor 2.0 REST layer with a fake service: flags, error shape, parsing."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from app.api.routes_doctor import register_doctor_routes
from app.auth import AuthContext
from app.errors import AppError
from app.rate_limit import require_auth_rate_limited
from app.schemas.doctor_policy import PolicyRead, PolicyScope, ValidateResponse
from app.services.doctor_policy.errors import ConfirmationInvalid, NotFound, VersionConflict
from app.services.doctor_policy.service import DoctorPolicyService

DOC = {"schema_version": 1, "rules": []}


class _FakeService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.raise_on_save: Exception | None = None

    def get_policy(self, user_id, ids):
        self.calls.append(("get_policy", user_id, list(ids)))
        if "99" in [str(i) for i in ids]:
            raise NotFound("Portfolio non trovato")
        return None

    def validate(self, user_id, ids, document):
        self.calls.append(("validate", user_id, list(ids), document))
        return ValidateResponse(valid=True, field_errors=[], normalized_document=document)

    def save(self, user_id, ids, *, name, document, base_version, confirmation_token):
        self.calls.append(("save", user_id, list(ids), name, base_version, confirmation_token))
        if self.raise_on_save:
            raise self.raise_on_save
        return PolicyRead(
            id=1, name=name, scope=PolicyScope(portfolio_ids=list(ids), scope_type="single", fingerprint="p:1"),
            current_version=1, document=document, updated_at="t", created_at="t",
        )

    def evaluate(self, user_id, ids):
        self.calls.append(("evaluate", user_id, list(ids)))
        raise NotFound("Portfolio non trovato")

    def preview_scenario(self, user_id, payload):
        return DoctorPolicyService.preview_scenario(self, user_id, payload)

    def compare_scenarios(self, user_id, payload):
        return DoctorPolicyService.compare_scenarios(self, user_id, payload)


@pytest.fixture()
def setup():
    settings = SimpleNamespace(doctor_policy_enabled=True, doctor_simulator_enabled=True)
    service = _FakeService()
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
    app.dependency_overrides[require_auth_rate_limited] = lambda: AuthContext(user_id="u1")
    return TestClient(app), service, settings


def test_features_reflect_flags(setup):
    client, _service, settings = setup
    assert client.get("/api/doctor/features").json() == {"policy_enabled": True, "simulator_enabled": True}
    settings.doctor_simulator_enabled = False
    assert client.get("/api/doctor/features").json() == {"policy_enabled": True, "simulator_enabled": False}


def test_policy_flag_off_is_404_feature_disabled(setup):
    client, service, settings = setup
    settings.doctor_policy_enabled = False
    for r in (
        client.get("/api/doctor/policies?portfolio_ids=1"),
        client.get("/api/doctor/metrics"),
        client.get("/api/doctor/templates"),
        client.get("/api/doctor/evaluation?portfolio_id=1"),
        client.post("/api/doctor/policies/validate", json={"portfolio_ids": [1], "document": DOC}),
    ):
        assert r.status_code == 404
        assert r.json()["error"]["code"] == "feature_disabled"
    assert service.calls == []


def test_simulator_flag_off_and_not_implemented(setup):
    client, _service, settings = setup
    r = client.post("/api/doctor/scenarios/preview", json={"portfolio_ids": [1]})
    assert r.status_code == 501 and r.json()["error"]["code"] == "not_implemented"
    settings.doctor_simulator_enabled = False
    for path in ("/api/doctor/scenarios/preview", "/api/doctor/scenarios/compare"):
        r = client.post(path, json={"portfolio_ids": [1]})
        assert r.status_code == 404 and r.json()["error"]["code"] == "feature_disabled"


def test_query_accepts_portfolio_id_and_repeated_ids(setup):
    client, service, _settings = setup
    assert client.get("/api/doctor/policies?portfolio_id=26").json() == {"policy": None}
    client.get("/api/doctor/policies?portfolio_ids=19&portfolio_ids=26")
    assert service.calls[0][2] == ["26"]
    assert service.calls[1][2] == ["19", "26"]


def test_error_details_shape_and_request_id(setup):
    client, _service, _settings = setup
    r = client.get("/api/doctor/evaluation?portfolio_ids=99", headers={"x-request-id": "req-123"})
    assert r.status_code == 404
    err = r.json()["error"]
    assert err["code"] == "not_found"
    assert err["details"] == {"field_errors": [], "retryable": False, "request_id": "req-123"}
    r = client.get("/api/doctor/policies?portfolio_ids=99", headers={"x-request-id": "bad id with spaces"})
    assert len(r.json()["error"]["details"]["request_id"]) == 32  # uuid4 hex


def test_malformed_body_is_400_with_field_errors(setup):
    client, service, _settings = setup
    r = client.post("/api/doctor/policies/validate", json={"portfolio_ids": "x", "document": DOC})
    assert r.status_code == 400
    err = r.json()["error"]
    assert err["code"] == "invalid_request"
    assert err["details"]["field_errors"][0]["field"].startswith("portfolio_ids")
    r = client.post("/api/doctor/policies/validate", json={"portfolio_ids": list(range(1, 22)), "document": DOC})
    assert r.status_code == 400
    r = client.post("/api/doctor/policies/validate")
    assert r.status_code == 400
    # portfolio_id spelling accepted in bodies too.
    assert client.post("/api/doctor/policies/validate", json={"portfolio_id": 5, "document": DOC}).status_code == 200
    assert service.calls[-1][2] == [5]


def test_save_without_token_is_confirmation_invalid(setup):
    client, service, _settings = setup
    r = client.post("/api/doctor/policies", json={"portfolio_ids": [1], "document": DOC, "base_version": None})
    assert r.status_code == 409 and r.json()["error"]["code"] == "confirmation_invalid"
    assert service.calls == []


@pytest.mark.parametrize("exc, code", [
    (VersionConflict("conflict"), "version_conflict"),
    (ConfirmationInvalid("bad token"), "confirmation_invalid"),
])
def test_save_conflicts_are_409(setup, exc, code):
    client, service, _settings = setup
    service.raise_on_save = exc
    r = client.post(
        "/api/doctor/policies",
        json={"portfolio_ids": [1], "document": DOC, "base_version": 2, "confirmation_token": "t"},
    )
    assert r.status_code == 409 and r.json()["error"]["code"] == code


def test_save_created_201(setup):
    client, service, _settings = setup
    r = client.post(
        "/api/doctor/policies",
        json={"portfolio_ids": [1], "name": "Mia", "document": DOC, "base_version": None, "confirmation_token": "t"},
    )
    assert r.status_code == 201 and r.json()["current_version"] == 1
    assert service.calls[-1] == ("save", "u1", [1], "Mia", None, "t")


def test_metrics_and_templates_endpoints_use_core(setup):
    client, _service, _settings = setup
    metrics = client.get("/api/doctor/metrics").json()
    assert len(metrics["metrics"]) == 8 and metrics["methodology_version"]
    templates = client.get("/api/doctor/templates").json()
    assert templates["templates"] and all(t["illustrative"] for t in templates["templates"])


def test_main_registers_doctor_routes_before_health_routes():
    import app.main as api_main

    paths = [getattr(r, "path", None) for r in api_main.router.routes]
    first_doctor = paths.index("/doctor/features")
    first_portfolio_param = next(i for i, p in enumerate(paths) if p and p.startswith("/portfolios/{portfolio_id}"))
    assert first_doctor < first_portfolio_param
    assert "/doctor/scenarios/compare" in paths
