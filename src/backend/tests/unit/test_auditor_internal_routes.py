"""TASK-80: endpoint interni della corsa notturna dell'Auditor ed endpoint amministrativo.

Autenticazione (token dedicato in tempo costante, 404 senza token, 401 token errato), limiti per IP,
202/409, stato, ``require_admin`` sull'endpoint amministrativo, esclusione dallo schema OpenAPI e
registrazione nell'app vera.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api import routes_auditor_internal as routes
from app.api.routes_auditor_internal import register_auditor_internal_routes
from app.auth import AuthContext, require_admin, require_auth
from app.errors import AppError
from app.services.auditor import store as st

TOKEN = "auditor-token-for-tests-0123456789"
RUN = "/api/internal/auditor/run"
STATUS = "/api/internal/auditor/run/status"
ADMIN = "/api/admin/auditor/latest"


class FakeService:
    def __init__(self) -> None:
        self.started: list[str] = []
        self.busy: str | None = None

    def start_in_background(self, trigger):
        if self.busy:
            return st.AlreadyRunning(run_id=self.busy)
        self.started.append(trigger)
        run_id = f"{len(self.started):032x}"
        return st.RunStarted(run_id=run_id)

    def status_payload(self):
        return {"running": None, "last_run": {"run_id": "f" * 32, "status": "success", "counts": {"pass": 1}}}

    def admin_latest(self):
        return {"run": {"run_id": "f" * 32}, "failing": [{"rule_id": "B-PAC-SUM", "portfolios_failing": 2}],
                "errors": []}


def _client(service=None, **settings):
    values = dict(
        auditor_run_token=TOKEN, trusted_proxy_ips_list=[],
        auditor_run_rate_limit_requests=4, auditor_status_rate_limit_requests=240,
        auditor_auth_failure_limit_requests=30, auditor_run_rate_limit_window_seconds=3600,
    )
    values.update(settings)
    service = service or FakeService()
    app = FastAPI()

    @app.exception_handler(AppError)
    async def _app_error(_request, exc: AppError):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code}})

    router = APIRouter()
    register_auditor_internal_routes(router, settings=SimpleNamespace(**values), service=service)
    app.include_router(router, prefix="/api")
    return TestClient(app), app, service


def _auth(token=TOKEN):
    return {"Authorization": f"Bearer {token}"}


def test_endpoints_disabled_without_token():
    client, _, service = _client(auditor_run_token="")
    assert client.post(RUN, headers=_auth()).status_code == 404
    response = client.get(STATUS, headers=_auth())
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"
    assert service.started == []
    # Spazi soltanto = non impostato.
    client, _, _ = _client(auditor_run_token="   ")
    assert client.post(RUN, headers=_auth("   ")).status_code == 404


def test_missing_or_wrong_token_is_rejected():
    client, _, service = _client()
    assert client.post(RUN).status_code == 401
    wrong = client.post(RUN, headers=_auth("wrong"))
    assert wrong.status_code == 401 and wrong.headers["WWW-Authenticate"] == "Bearer"
    assert client.post(RUN, headers={"Authorization": TOKEN}).status_code == 401
    assert client.post(RUN, headers={"Authorization": f"Basic {TOKEN}"}).status_code == 401
    assert client.get(STATUS, headers=_auth(TOKEN + "x")).status_code == 401
    assert service.started == []


def test_market_data_token_does_not_open_auditor_endpoints():
    client, _, service = _client(market_data_sync_token="other-token")
    assert client.post(RUN, headers=_auth("other-token")).status_code == 401
    assert service.started == []


def test_token_is_compared_in_constant_time():
    client, _, _ = _client()
    with patch.object(routes.hmac, "compare_digest", wraps=routes.hmac.compare_digest) as spy:
        assert client.get(STATUS, headers=_auth()).status_code == 200
    spy.assert_called_once_with(TOKEN.encode("utf-8"), TOKEN.encode("utf-8"))


def test_post_starts_run_and_409_when_already_running():
    client, _, service = _client()
    started = client.post(RUN, headers=_auth())
    assert started.status_code == 202
    assert started.json() == {"run_id": "0" * 31 + "1", "status": "running"}
    assert service.started == ["external"]
    service.busy = "a" * 32
    conflict = client.post(RUN, headers=_auth())
    assert conflict.status_code == 409
    body = conflict.json()
    assert body["code"] == "already_running" and body["run_id"] == "a" * 32
    assert body["error"]["code"] == "already_running"


def test_status_returns_service_payload():
    client, _, _ = _client()
    body = client.get(STATUS, headers=_auth()).json()
    assert body == {"running": None, "last_run": {"run_id": "f" * 32, "status": "success", "counts": {"pass": 1}}}


def test_rate_limits():
    client, _, _ = _client(auditor_run_rate_limit_requests=2, auditor_auth_failure_limit_requests=3)
    codes = [client.post(RUN, headers=_auth()).status_code for _ in range(3)]
    assert codes == [202, 202, 429]
    limited = client.post(RUN, headers=_auth())
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    # Lo stato ha il suo budget.
    assert client.get(STATUS, headers=_auth()).status_code == 200
    # I token errati hanno un limite separato e non bloccano il token valido.
    bad = [client.get(STATUS, headers=_auth("x")).status_code for _ in range(4)]
    assert bad == [401, 401, 401, 429]
    assert client.get(STATUS, headers=_auth()).status_code == 200


def test_admin_endpoint_requires_admin():
    client, app, _ = _client()

    def forbidden():
        raise AppError(code="forbidden", message="Admin access required", status_code=403)

    app.dependency_overrides[require_admin] = forbidden
    assert client.get(ADMIN).status_code == 403
    app.dependency_overrides[require_admin] = lambda: AuthContext(user_id="admin", org_id=None, email=None, claims={})
    response = client.get(ADMIN)
    assert response.status_code == 200
    assert response.json()["failing"] == [{"rule_id": "B-PAC-SUM", "portfolios_failing": 2}]
    # Il token interno non basta per l'endpoint amministrativo.
    app.dependency_overrides.clear()
    app.dependency_overrides[require_auth] = lambda: AuthContext(user_id="someone", org_id=None, email=None, claims={})
    assert client.get(ADMIN, headers=_auth()).status_code == 403


def test_internal_endpoints_not_in_openapi():
    _, app, _ = _client()
    paths = app.openapi()["paths"]
    assert not any("internal" in path for path in paths)
    assert ADMIN in paths


def test_registered_on_the_main_app_and_disabled_by_default(monkeypatch):
    import app.main as api_main

    client = TestClient(api_main.app)
    assert api_main.settings.auditor_run_token == ""
    assert client.post(RUN, headers=_auth()).status_code == 404
    assert client.get(STATUS, headers=_auth()).status_code == 404
    assert not any("internal" in path for path in api_main.app.openapi().get("paths", {}))
    monkeypatch.setattr(api_main.settings, "auditor_run_token", TOKEN)
    assert client.post(RUN, headers=_auth("wrong")).status_code == 401
    assert isinstance(api_main.auditor_nightly, st.AuditorNightlyService)
    # Non amministratore (utente dev senza ADMIN_*): 403.
    assert client.get(ADMIN).status_code == 403


def test_app_lifespan_launches_the_interrupted_check(monkeypatch):
    import app.main as api_main

    calls = []
    monkeypatch.setattr(api_main, "launch_interrupted_check", lambda svc: calls.append(svc))
    monkeypatch.setattr(api_main, "launch_startup_catch_up", lambda svc, settings: None)
    monkeypatch.setattr(api_main, "_apply_pending_migrations", lambda: None)
    monkeypatch.setattr(api_main.scheduler, "start", lambda: None)
    monkeypatch.setattr(api_main.scheduler, "shutdown", lambda: None)
    with TestClient(api_main.app):
        pass
    assert calls == [api_main.auditor_nightly]


def test_startup_migrations_include_auditor(monkeypatch):
    import app.main as api_main

    executed = []

    class _Conn:
        def execute(self, statement, *args):
            executed.append(str(statement))

    class _Begin:
        def __enter__(self):
            return _Conn()

        def __exit__(self, *exc):
            return False

    import app.db as db

    monkeypatch.setattr(db, "engine", SimpleNamespace(begin=lambda: _Begin()))
    api_main._apply_pending_migrations()
    assert any("create table if not exists auditor_runs" in sql for sql in executed)
    assert any("alter table auditor_results enable row level security" in sql for sql in executed)
