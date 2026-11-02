"""/docs, /redoc and /openapi.json: off in production unless API_DOCS_ENABLED=true."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.main as api_main
from app.config import Settings

DOC_PATHS = ("/docs", "/redoc", "/openapi.json")


@pytest.mark.parametrize(
    "app_env, flag, enabled",
    [
        ("dev", None, True),
        ("staging", None, True),
        ("prod", None, False),
        (" Production ", None, False),
        ("prod", True, True),
        ("dev", False, False),
    ],
)
def test_api_docs_enabled_resolution(app_env, flag, enabled):
    assert Settings(app_env=app_env, api_docs_enabled=flag).api_docs_enabled_resolved is enabled


def test_api_docs_env_var(monkeypatch):
    monkeypatch.setenv("APP_ENV", "prod")
    monkeypatch.setenv("API_DOCS_ENABLED", "true")
    assert Settings().api_docs_enabled_resolved is True


@pytest.mark.parametrize("app_env, expected_status", [("dev", 200), ("prod", 404)])
def test_docs_routes_follow_setting(app_env, expected_status):
    app = FastAPI(**api_main.api_docs_kwargs(Settings(app_env=app_env)))

    @app.get("/ping")
    def ping() -> dict:
        return {"ok": True}

    client = TestClient(app)
    for path in DOC_PATHS:
        assert client.get(path).status_code == expected_status, path
    assert client.get("/ping").status_code == 200


def test_real_app_docs_match_settings():
    client = TestClient(api_main.app)
    enabled = api_main.settings.api_docs_enabled_resolved
    for path in DOC_PATHS:
        assert client.get(path).status_code == (200 if enabled else 404), path
    if enabled:
        # The full schema of the real app still builds with the current FastAPI.
        assert "/api/portfolios/{portfolio_id}/summary" in client.get("/openapi.json").json()["paths"]
