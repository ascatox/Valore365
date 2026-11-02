"""Per-user rate limiting as a FastAPI dependency."""

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, Request
from starlette.requests import HTTPConnection

from .auth import AuthContext, require_auth
from .config import get_settings
from .errors import AppError


class SlidingWindowRateLimiter:
    """In-memory sliding-window counter per key (per process)."""

    # Keys whose newest hit left the window are dropped every this many
    # calls, so keys that are never seen again (e.g. client IPs) don't pile up.
    _PRUNE_EVERY = 1024

    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()
        self._calls = 0

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            self._calls += 1
            if self._calls % self._PRUNE_EVERY == 0:
                for stale in [k for k, b in self._entries.items() if not b or b[-1] <= cutoff]:
                    del self._entries[stale]
            bucket = self._entries[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True

    def is_limited(self, key: str) -> bool:
        """True if the next allow(key) would be refused. Records nothing."""
        cutoff = time.monotonic() - self.window_seconds
        with self._lock:
            bucket = self._entries.get(key)
            if not bucket:
                return False
            return sum(1 for t in bucket if t > cutoff) >= self.max_requests


def client_ip(conn: HTTPConnection, settings=None) -> str:
    """Client IP; X-Forwarded-For is trusted only from TRUSTED_PROXY_IPS."""
    settings = settings or get_settings()
    forwarded_for = conn.headers.get("x-forwarded-for", "").strip()
    remote_host = conn.client.host if conn.client and conn.client.host else None
    if forwarded_for and remote_host and remote_host in settings.trusted_proxy_ips_list:
        return forwarded_for.split(",")[0].strip()
    if remote_host:
        return remote_host
    return "unknown"


_settings = get_settings()

_user_limiter = SlidingWindowRateLimiter(
    max_requests=_settings.authenticated_rate_limit_requests,
    window_seconds=_settings.authenticated_rate_limit_window_seconds,
)


def require_auth_rate_limited(
    request: Request,
    auth: AuthContext = Depends(require_auth),
) -> AuthContext:
    """Authenticate and enforce per-user rate limit.

    Also sets request.state.user_id for the logging middleware.
    """
    request.state.user_id = auth.user_id

    if not _user_limiter.allow(auth.user_id):
        raise AppError(
            code="rate_limited",
            message="Too many requests. Please slow down.",
            status_code=429,
        )
    return auth
