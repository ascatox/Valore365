"""Middleware: structured request logging."""

import logging
import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("valore365.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status and duration for every request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.monotonic()
        response: Response | None = None
        try:
            response = await call_next(request)
            return response
        finally:
            elapsed_ms = (time.monotonic() - start) * 1000
            status = response.status_code if response else 500
            user_id = getattr(request.state, "user_id", "-")
            logger.info(
                "%s %s %s %.0fms user=%s",
                request.method,
                request.url.path,
                status,
                elapsed_ms,
                user_id,
            )
