"""Copilot X-Ray: justETF auto-enrichment follows JUSTETF_XRAY_AUTO_ENRICH_ENABLED."""

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api import routes_copilot
from app.auth import AuthContext
from app.config import Settings
from app.copilot.config import CopilotConfig
from app.rate_limit import require_auth_rate_limited

JUSTETF = object()


class _Repo:
    def get_user_settings(self, user_id):
        class _S:
            copilot_provider = None
            copilot_model = None
            copilot_api_key_set = False

        return _S()

    def get_user_copilot_api_key_enc(self, user_id):
        return None

    def memoize_positions(self):
        import contextlib

        return contextlib.nullcontext()


def _client(monkeypatch, settings, captured):
    monkeypatch.setattr(
        routes_copilot, "resolve_copilot_config",
        lambda *a, **k: CopilotConfig(provider="openai", model="m", api_key="k"),
    )
    monkeypatch.setattr(routes_copilot, "build_portfolio_snapshot_light", lambda *a, **k: {})

    def fake_stream(*args, **kwargs):
        captured.update(kwargs)
        yield "data: {}\n\n"

    monkeypatch.setattr(routes_copilot, "stream_copilot_response_agentic", fake_stream)

    app = FastAPI()
    router = APIRouter()
    routes_copilot.register_copilot_routes(
        router, _Repo(), settings, performance_service=None, finance_client=None, justetf_client=JUSTETF,
    )
    app.include_router(router)
    app.dependency_overrides[require_auth_rate_limited] = lambda: AuthContext(user_id="u")
    return TestClient(app)


@pytest.mark.parametrize(
    "app_env, flag, expected",
    [
        ("dev", None, JUSTETF),     # default: on in dev
        ("prod", None, None),       # default: off outside dev
        ("prod", True, JUSTETF),    # explicit on
        ("dev", False, None),       # explicit off
    ],
)
def test_copilot_xray_respects_auto_enrich_setting(monkeypatch, app_env, flag, expected):
    settings = Settings(app_env=app_env, justetf_xray_auto_enrich_enabled=flag)
    captured: dict = {}
    client = _client(monkeypatch, settings, captured)

    response = client.post(
        "/copilot/chat",
        json={"portfolio_id": 1, "messages": [{"role": "user", "content": "x-ray?"}]},
    )

    assert response.status_code == 200
    assert captured["justetf_client"] is expected
