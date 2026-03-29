import hashlib
import threading
import time
from collections import defaultdict, deque

from fastapi import APIRouter, Request
from fastapi import File, Form, UploadFile

from ..config import get_settings
from ..errors import AppError
from ..models import ErrorResponse
from ..repository import PortfolioRepository
from .routes_csv import (
    CSV_IMPORT_ALLOWED_CONTENT_TYPES,
    CSV_IMPORT_ALLOWED_EXTENSIONS,
    _format_file_size_limit,
)
from ..schemas.instant_portfolio_analyzer import (
    InstantAnalyzeRequest,
    InstantAnalyzeResponse,
    InstantInsightExplainRequest,
    InstantInsightExplainResponse,
    InstantPortfolioImportResponse,
)
from ..services.instant_portfolio_analyzer import (
    InstantPortfolioAnalysisError,
    analyze_public_portfolio,
    explain_public_insight,
)


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


def _positions_count(payload: InstantAnalyzeRequest) -> int:
    if payload.input_mode == "raw_text":
        raw_text = payload.raw_text or ""
        return len([line for line in raw_text.splitlines() if line.strip()])
    return len(payload.positions)


def _hash_client_ip(client_ip: str) -> str | None:
    if not client_ip or client_ip == "unknown":
        return None
    return hashlib.sha256(client_ip.encode("utf-8")).hexdigest()


_settings = get_settings()
_public_instant_rate_limiter = SlidingWindowRateLimiter(
    max_requests=_settings.public_instant_analyzer_rate_limit_requests,
    window_seconds=_settings.public_instant_analyzer_rate_limit_window_seconds,
)


def reset_public_instant_analyzer_rate_limiter() -> None:
    _public_instant_rate_limiter.reset()


def register_instant_portfolio_analyzer_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    csv_import_service: object | None = None,
) -> None:
    @router.post(
        "/public/portfolio/analyze",
        response_model=InstantAnalyzeResponse,
        responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    def analyze_portfolio(payload: InstantAnalyzeRequest, request: Request) -> InstantAnalyzeResponse:
        client_ip = _client_ip(request)
        if not _public_instant_rate_limiter.allow(client_ip):
            raise AppError(
                code="rate_limited",
                message="Too many analysis requests. Please try again later.",
                status_code=429,
            )
        positions_count = _positions_count(payload)

        try:
            _validate_public_payload(payload)
            response = analyze_public_portfolio(repo, payload)
            try:
                repo.record_public_instant_analyzer_event(
                    client_ip_hash=_hash_client_ip(client_ip),
                    input_mode=payload.input_mode,
                    positions_count=positions_count,
                    success=True,
                )
            except Exception:
                pass
            return response
        except InstantPortfolioAnalysisError as exc:
            try:
                repo.record_public_instant_analyzer_event(
                    client_ip_hash=_hash_client_ip(client_ip),
                    input_mode=payload.input_mode,
                    positions_count=positions_count,
                    success=False,
                )
            except Exception:
                pass
            raise AppError(code="bad_request", message=str(exc), status_code=400, details=exc.details) from exc
        except ValueError as exc:
            try:
                repo.record_public_instant_analyzer_event(
                    client_ip_hash=_hash_client_ip(client_ip),
                    input_mode=payload.input_mode,
                    positions_count=positions_count,
                    success=False,
                )
            except Exception:
                pass
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc
        except AppError:
            try:
                repo.record_public_instant_analyzer_event(
                    client_ip_hash=_hash_client_ip(client_ip),
                    input_mode=payload.input_mode,
                    positions_count=positions_count,
                    success=False,
                )
            except Exception:
                pass
            raise

    @router.post(
        "/public/portfolio/explain-insight",
        response_model=InstantInsightExplainResponse,
        responses={400: {"model": ErrorResponse}},
    )
    def explain_insight(payload: InstantInsightExplainRequest) -> InstantInsightExplainResponse:
        try:
            return explain_public_insight(payload.insight)
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.post(
        "/public/portfolio/import-csv",
        response_model=InstantPortfolioImportResponse,
        responses={400: {"model": ErrorResponse}, 429: {"model": ErrorResponse}},
    )
    async def import_csv_for_analyzer(
        request: Request,
        file: UploadFile = File(...),
        broker: str = Form("fineco"),
    ) -> InstantPortfolioImportResponse:
        if csv_import_service is None:
            raise AppError(code="bad_request", message="CSV import service not configured", status_code=400)

        client_ip = _client_ip(request)
        if not _public_instant_rate_limiter.allow(client_ip):
            raise AppError(
                code="rate_limited",
                message="Too many analysis requests. Please try again later.",
                status_code=429,
            )

        filename = file.filename or ""
        if not filename.lower().endswith(CSV_IMPORT_ALLOWED_EXTENSIONS):
            raise AppError(
                code="bad_request",
                message="Formato file non supportato. Usa CSV o Excel (XLSX).",
                status_code=400,
            )
        if file.content_type and file.content_type not in CSV_IMPORT_ALLOWED_CONTENT_TYPES:
            raise AppError(
                code="bad_request",
                message="Content-Type file non supportato.",
                status_code=400,
            )

        content = await file.read()
        max_upload = get_settings().csv_import_max_upload_bytes
        if len(content) > max_upload:
            raise AppError(
                code="bad_request",
                message=f"File troppo grande. Limite massimo {_format_file_size_limit(max_upload)}",
                status_code=400,
            )

        try:
            is_xlsx = filename.lower().endswith((".xlsx", ".xls"))
            if is_xlsx:
                return csv_import_service.parse_public_portfolio_file(
                    file_bytes=content,
                    filename=filename,
                    broker=broker,
                )
            return csv_import_service.parse_public_portfolio_file(
                file_content=content.decode("utf-8-sig"),
                filename=filename,
                broker=broker,
            )
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc
