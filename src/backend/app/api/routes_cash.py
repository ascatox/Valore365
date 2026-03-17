from fastapi import APIRouter, Depends

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..models import (
    CashBalanceResponse,
    CashFlowTimelineResponse,
    CashMovementCreate,
    ErrorResponse,
    TransactionRead,
)
from ..repository import PortfolioRepository


def register_cash_routes(router: APIRouter, repo: PortfolioRepository) -> None:

    @router.post("/cash-movements", response_model=TransactionRead, responses={400: {"model": ErrorResponse}})
    def create_cash_movement(payload: CashMovementCreate, _auth: AuthContext = Depends(require_auth_rate_limited)) -> TransactionRead:
        try:
            return repo.create_cash_movement(payload, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.get(
        "/portfolios/{portfolio_id}/cash-balance",
        response_model=CashBalanceResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_cash_balance(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> CashBalanceResponse:
        try:
            return repo.get_computed_cash_balance(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/cash-flow-timeline",
        response_model=CashFlowTimelineResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_cash_flow_timeline(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> CashFlowTimelineResponse:
        try:
            return repo.get_cash_flow_timeline(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
