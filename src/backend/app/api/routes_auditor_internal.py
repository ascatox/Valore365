"""Endpoint della corsa notturna dell'Auditor (TASK-80, docs/auditor/architecture.md §6.1).

POST /api/internal/auditor/run
    202 {run_id, status: 'running'}: corsa avviata in un thread in background;
    409 {code: 'already_running', run_id, error}: un'altra corsa tiene il lock.
GET /api/internal/auditor/run/status
    200 {running: RunSummary | null, last_run: RunSummary | null}.
GET /api/admin/auditor/latest  (require_admin)
    200 {run: RunSummary | null, failing: [{rule_id, title, area, severity, portfolios_failing,
    since}], errors: [{rule_id, portfolios}]}.

Solo conteggi e id di regole: nessun id di utente o portafoglio, nessuna evidenza.

Auth degli endpoint interni: ``Authorization: Bearer <AUDITOR_RUN_TOKEN>`` confrontato in tempo
costante; token non impostato → 404 (endpoint disattivati). Limiti per IP come in
``routes_internal.py``: POST ``auditor_run_rate_limit_requests`` per finestra, stato
``auditor_status_rate_limit_requests``, token errati ``auditor_auth_failure_limit_requests`` (un
token valido non è mai bloccato dagli errori altrui). Esclusi dallo schema OpenAPI.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from ..auth import AuthContext, require_admin
from ..rate_limit import SlidingWindowRateLimiter, client_ip
from ..services.auditor.store import AlreadyRunning

logger = logging.getLogger(__name__)

RUN_PATH = "/internal/auditor/run"
STATUS_PATH = "/internal/auditor/run/status"
ADMIN_LATEST_PATH = "/admin/auditor/latest"


def _error(status_code: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}, **extra})


class AuditorInternalGuard:
    """Token e limiti degli endpoint interni dell'Auditor (uno per app)."""

    def __init__(self, settings) -> None:
        self.settings = settings
        window = int(getattr(settings, "auditor_run_rate_limit_window_seconds", 3600))
        self.run_limiter = SlidingWindowRateLimiter(
            max_requests=int(getattr(settings, "auditor_run_rate_limit_requests", 4)), window_seconds=window,
        )
        self.status_limiter = SlidingWindowRateLimiter(
            max_requests=int(getattr(settings, "auditor_status_rate_limit_requests", 240)), window_seconds=window,
        )
        self.auth_failures = SlidingWindowRateLimiter(
            max_requests=int(getattr(settings, "auditor_auth_failure_limit_requests", 30)), window_seconds=window,
        )

    def check(self, request: Request, limiter: SlidingWindowRateLimiter) -> JSONResponse | None:
        """None se la richiesta può procedere, altrimenti la risposta d'errore."""
        expected = str(getattr(self.settings, "auditor_run_token", "") or "").strip()
        if not expected:
            return _error(404, "not_found", "Not Found")
        ip = client_ip(request, self.settings)
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        valid = scheme.lower() == "bearer" and hmac.compare_digest(
            token.strip().encode("utf-8"), expected.encode("utf-8"),
        )
        if not valid:
            if not self.auth_failures.allow(f"auth:{ip}"):
                return _error(429, "rate_limited", "Too many requests. Please slow down.")
            logger.warning("auditor internal endpoint: invalid token ip=%s path=%s", ip, request.url.path)
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "unauthorized", "message": "Token non valido"}},
                headers={"WWW-Authenticate": "Bearer"},
            )
        if not limiter.allow(f"ok:{ip}"):
            retry_after = max(1, limiter.retry_after(f"ok:{ip}"))
            return JSONResponse(
                status_code=429,
                content={"error": {"code": "rate_limited", "message": "Too many requests. Please slow down."}},
                headers={"Retry-After": str(retry_after)},
            )
        return None


def register_auditor_internal_routes(router: APIRouter, *, settings, service) -> AuditorInternalGuard:
    guard = AuditorInternalGuard(settings)

    @router.post(RUN_PATH, include_in_schema=False)
    def trigger_auditor_run(request: Request) -> JSONResponse:
        denied = guard.check(request, guard.run_limiter)
        if denied is not None:
            return denied
        started = service.start_in_background("external")
        if isinstance(started, AlreadyRunning):
            return JSONResponse(
                status_code=409,
                content={
                    "code": "already_running",
                    "run_id": started.run_id,
                    "error": {"code": "already_running", "message": "Corsa dell'Auditor già in corso"},
                },
            )
        logger.info("auditor nightly external trigger accepted run_id=%s", started.run_id)
        return JSONResponse(status_code=202, content={"run_id": started.run_id, "status": "running"})

    @router.get(STATUS_PATH, include_in_schema=False)
    def auditor_run_status(request: Request) -> JSONResponse:
        denied = guard.check(request, guard.status_limiter)
        if denied is not None:
            return denied
        return JSONResponse(status_code=200, content=jsonable_encoder(service.status_payload()))

    @router.get(ADMIN_LATEST_PATH)
    def auditor_admin_latest(_auth: AuthContext = Depends(require_admin)) -> dict[str, Any]:
        """Ultima corsa notturna: regole che falliscono, su quanti portafogli, da quando."""
        return jsonable_encoder(service.admin_latest())

    return guard
