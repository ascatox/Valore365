"""Per-user rate limiting as a FastAPI dependency."""

import threading
import time
from collections import defaultdict, deque

from fastapi import Depends, Request

from .auth import AuthContext, require_auth
from .config import get_settings
from .errors import AppError


class SlidingWindowRateLimiter:
    """In-memory sliding-window counter per key."""

    def __init__(self, *, max_requests: int, window_seconds: int) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self.window_seconds
        with self._lock:
            bucket = self._entries[key]
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= self.max_requests:
                return False
            bucket.append(now)
            return True


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
