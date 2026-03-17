from fastapi import APIRouter, Depends

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..models import (
    ErrorResponse,
    PortfolioCreate,
    PortfolioCloneRequest,
    PortfolioCloneResponse,
    PortfolioRead,
    PortfolioUpdate,
    UserSettingsRead,
    UserSettingsUpdate,
)
from ..repository import PortfolioRepository


def register_portfolio_routes(router: APIRouter, repo: PortfolioRepository, settings: object = None) -> None:
    from ..copilot_service import encrypt_api_key

    @router.get("/settings/user", response_model=UserSettingsRead)
    def get_user_settings(_auth: AuthContext = Depends(require_auth_rate_limited)) -> UserSettingsRead:
        try:
            return repo.get_user_settings(_auth.user_id)
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.put("/settings/user", response_model=UserSettingsRead, responses={400: {"model": ErrorResponse}})
    def update_user_settings(payload: UserSettingsUpdate, _auth: AuthContext = Depends(require_auth_rate_limited)) -> UserSettingsRead:
        try:
            api_key_enc: str | None = None
            if payload.copilot_api_key is not None:
                if payload.copilot_api_key == "":
                    api_key_enc = ""  # clear key
                else:
                    api_key_enc = encrypt_api_key(payload.copilot_api_key, settings)
                    if not api_key_enc:
                        raise ValueError("Impossibile cifrare la chiave API: COPILOT_ENCRYPTION_KEY non configurata")
            return repo.upsert_user_settings(_auth.user_id, payload, api_key_enc=api_key_enc)
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.post("/portfolios", response_model=PortfolioRead, responses={400: {"model": ErrorResponse}})
    def create_portfolio(payload: PortfolioCreate, _auth: AuthContext = Depends(require_auth_rate_limited)) -> PortfolioRead:
        try:
            return repo.create_portfolio(payload, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.get("/portfolios", response_model=list[PortfolioRead], responses={400: {"model": ErrorResponse}})
    def list_portfolios(_auth: AuthContext = Depends(require_auth_rate_limited)) -> list[PortfolioRead]:
        return repo.list_portfolios(_auth.user_id)

    @router.patch(
        "/portfolios/{portfolio_id}",
        response_model=PortfolioRead,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def update_portfolio(
        portfolio_id: int,
        payload: PortfolioUpdate,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PortfolioRead:
        try:
            return repo.update_portfolio(portfolio_id, payload, _auth.user_id)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.post(
        "/portfolios/{portfolio_id}/clone",
        response_model=PortfolioCloneResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def clone_portfolio(
        portfolio_id: int,
        payload: PortfolioCloneRequest,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PortfolioCloneResponse:
        try:
            return repo.clone_portfolio(portfolio_id, payload, _auth.user_id)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.delete(
        "/portfolios/{portfolio_id}",
        responses={404: {"model": ErrorResponse}},
    )
    def delete_portfolio(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> dict[str, str]:
        try:
            repo.delete_portfolio(portfolio_id, _auth.user_id)
            return {"status": "ok"}
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
