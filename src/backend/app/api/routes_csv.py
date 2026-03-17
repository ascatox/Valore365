from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import StreamingResponse

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..models import (
    CsvImportCommitResponse,
    CsvImportPreviewResponse,
    ErrorResponse,
)
from ..repository import PortfolioRepository


CSV_IMPORT_ALLOWED_EXTENSIONS = (".csv", ".xlsx", ".xls")
CSV_IMPORT_ALLOWED_CONTENT_TYPES = {
    "text/csv",
    "application/csv",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/octet-stream",
}


def _format_file_size_limit(byte_count: int) -> str:
    if byte_count >= 1024 * 1024:
        return f"{byte_count // (1024 * 1024)} MB"
    if byte_count >= 1024:
        return f"{byte_count // 1024} KB"
    return f"{byte_count} bytes"


def register_csv_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    settings: object,
    csv_import_service: object,
) -> None:

    @router.post(
        "/portfolios/{portfolio_id}/csv-import/preview",
        response_model=CsvImportPreviewResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    async def csv_import_preview(
        portfolio_id: int,
        file: UploadFile = File(...),
        broker: str = Form("generic"),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> CsvImportPreviewResponse:
        try:
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
            if len(content) > settings.csv_import_max_upload_bytes:
                raise AppError(
                    code="bad_request",
                    message=f"File troppo grande. Limite massimo {_format_file_size_limit(settings.csv_import_max_upload_bytes)}",
                    status_code=400,
                )
            is_xlsx = filename.lower().endswith((".xlsx", ".xls"))
            if is_xlsx:
                return csv_import_service.parse_and_validate(
                    portfolio_id=portfolio_id,
                    user_id=_auth.user_id,
                    file_bytes=content,
                    filename=filename,
                    broker=broker,
                )
            file_content = content.decode("utf-8-sig")
            return csv_import_service.parse_and_validate(
                portfolio_id=portfolio_id,
                user_id=_auth.user_id,
                file_content=file_content,
                filename=filename,
                broker=broker,
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/csv-import/template",
        responses={400: {"model": ErrorResponse}},
    )
    def csv_import_template(
        broker: str = Query("generic"),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> StreamingResponse:
        try:
            content, filename = csv_import_service.build_template_xlsx(broker)
            return StreamingResponse(
                iter([content]),
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                headers={"Content-Disposition": f'attachment; filename="{filename}"'},
            )
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.post(
        "/csv-import/{batch_id}/commit",
        response_model=CsvImportCommitResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def csv_import_commit(batch_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> CsvImportCommitResponse:
        try:
            return csv_import_service.commit_batch(batch_id, _auth.user_id)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.delete("/csv-import/{batch_id}", responses={404: {"model": ErrorResponse}})
    def csv_import_cancel(batch_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> dict[str, str]:
        try:
            repo.cancel_csv_import_batch(batch_id, _auth.user_id)
            return {"status": "ok"}
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
