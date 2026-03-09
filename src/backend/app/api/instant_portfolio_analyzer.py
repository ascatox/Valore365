import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Request

from ..config import get_settings
from ..errors import AppError
from ..models import ErrorResponse
from ..repository import PortfolioRepository
from ..schemas.instant_portfolio_analyzer import InstantAnalyzeRequest, InstantAnalyzeResponse
from ..services.instant_portfolio_analyzer import InstantPortfolioAnalysisError, analyze_public_portfolio


class SlidingWindowRateLimiter:
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

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").strip()
    settings = get_settings()
    remote_host = request.client.host if request.client and request.client.host else None
    if forwarded_for and remote_host and remote_host in settings.trusted_proxy_ips_list:
        return forwarded_for.split(",")[0].strip()
    if remote_host:
        return remote_host
    return "unknown"


def _validate_public_payload(payload: InstantAnalyzeRequest) -> None:
    settings = get_settings()
    max_positions = settings.public_instant_analyzer_max_positions
    max_raw_text_chars = settings.public_instant_analyzer_max_raw_text_chars

    if payload.input_mode == "raw_text":
        raw_text = payload.raw_text or ""
        if len(raw_text) > max_raw_text_chars:
            raise AppError(
                code="bad_request",
                message=f"Raw text input exceeds the {max_raw_text_chars} character limit",
                status_code=400,
            )
        non_empty_lines = [line for line in raw_text.splitlines() if line.strip()]
        if len(non_empty_lines) > max_positions:
            raise AppError(
                code="bad_request",
                message=f"Too many positions submitted (max {max_positions})",
                status_code=400,
            )
        return

    if len(payload.positions) > max_positions:
        raise AppError(
            code="bad_request",
            message=f"Too many positions submitted (max {max_positions})",
            status_code=400,
        )


_settings = get_settings()
_public_instant_rate_limiter = SlidingWindowRateLimiter(
    max_requests=_settings.public_instant_analyzer_rate_limit_requests,
    window_seconds=_settings.public_instant_analyzer_rate_limit_window_seconds,
)


def reset_public_instant_analyzer_rate_limiter() -> None:
    _public_instant_rate_limiter.reset()


def register_instant_portfolio_analyzer_routes(router: APIRouter, repo: PortfolioRepository) -> None:
    @router.post(
        "/public/portfolio/analyze",
        response_model=InstantAnalyzeResponse,
        responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    def analyze_portfolio(payload: InstantAnalyzeRequest, request: Request) -> InstantAnalyzeResponse:
        if not _public_instant_rate_limiter.allow(_client_ip(request)):
            raise AppError(
                code="rate_limited",
                message="Too many analysis requests. Please try again later.",
                status_code=429,
            )
        _validate_public_payload(payload)
        try:
            return analyze_public_portfolio(repo, payload)
        except InstantPortfolioAnalysisError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400, details=exc.details) from exc
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc
