"""Internal endpoints of the market data sync (TASK-54), for the GitHub Actions cron.

POST /api/internal/market-data/sync[?force=true]
    202 {run_id, status: 'running'}: sync started in a background thread;
    409 {code: 'already_running', run_id}: another sync holds the lock;
    200 {status: 'up_to_date', last_successful_price_sync}: nothing to do
    (needs_sync() false and no force).
GET /api/internal/market-data/sync/status
    last run, running run, last success and the lagging assets (counts and
    symbols only, never user data).

Auth: ``Authorization: Bearer <MARKET_DATA_SYNC_TOKEN>``, compared in
constant time. Token unset -> 404 (endpoints disabled). Rate limits per
caller IP: POST market_data_sync_rate_limit_requests per window, status
market_data_sync_status_rate_limit_requests, failed auth
market_data_sync_auth_failure_limit_requests (a valid token is never
blocked by others' failures). Excluded from the OpenAPI schema.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse

from ..rate_limit import SlidingWindowRateLimiter, client_ip
from ..services.market_data_sync import AlreadyRunning

logger = logging.getLogger(__name__)

SYNC_PATH = "/internal/market-data/sync"
STATUS_PATH = "/internal/market-data/sync/status"


def _error(status_code: int, code: str, message: str, **extra: Any) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": {"code": code, "message": message}, **extra})


class InternalSyncGuard:
    """Token check and rate limits of the internal endpoints (one per app)."""

    def __init__(self, settings) -> None:
        self.settings = settings
        window = int(getattr(settings, "market_data_sync_rate_limit_window_seconds", 3600))
        self.sync_limiter = SlidingWindowRateLimiter(
            max_requests=int(getattr(settings, "market_data_sync_rate_limit_requests", 10)), window_seconds=window,
        )
        self.status_limiter = SlidingWindowRateLimiter(
            max_requests=int(getattr(settings, "market_data_sync_status_rate_limit_requests", 240)),
            window_seconds=window,
        )
        self.auth_failures = SlidingWindowRateLimiter(
            max_requests=int(getattr(settings, "market_data_sync_auth_failure_limit_requests", 30)),
            window_seconds=window,
        )

    def check(self, request: Request, limiter: SlidingWindowRateLimiter) -> JSONResponse | None:
        """None when the request may proceed, else the error response."""
        expected = str(getattr(self.settings, "market_data_sync_token", "") or "").strip()
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
            logger.warning("market_data_sync internal endpoint: invalid token ip=%s path=%s", ip, request.url.path)
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


def register_internal_routes(router: APIRouter, *, settings, market_data_sync) -> InternalSyncGuard:
    guard = InternalSyncGuard(settings)

    @router.post(SYNC_PATH, include_in_schema=False)
    def trigger_market_data_sync(request: Request, force: bool = Query(default=False)) -> JSONResponse:
        denied = guard.check(request, guard.sync_limiter)
        if denied is not None:
            return denied
        if not force and not market_data_sync.needs_sync():
            overview = market_data_sync.overview()
            finished = (overview.get("last_success") or {}).get("finished_at")
            return JSONResponse(
                status_code=200,
                content={
                    "status": "up_to_date",
                    "last_successful_price_sync": finished.isoformat() if finished is not None else None,
                },
            )
        started = market_data_sync.start_in_background("external")
        if isinstance(started, AlreadyRunning):
            return JSONResponse(
                status_code=409,
                content={
                    "code": "already_running",
                    "run_id": started.run_id,
                    "error": {"code": "already_running", "message": "Sincronizzazione già in corso"},
                },
            )
        logger.info("market_data_sync external trigger accepted run_id=%s force=%s", started.run_id, force)
        return JSONResponse(status_code=202, content={"run_id": started.run_id, "status": "running"})

    @router.get(STATUS_PATH, include_in_schema=False)
    def market_data_sync_status(request: Request) -> JSONResponse:
        denied = guard.check(request, guard.status_limiter)
        if denied is not None:
            return denied
        from fastapi.encoders import jsonable_encoder

        return JSONResponse(status_code=200, content=jsonable_encoder(market_data_sync.status_payload()))

    return guard
