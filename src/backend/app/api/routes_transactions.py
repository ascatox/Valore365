import threading

from fastapi import APIRouter, Depends

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..models import (
    ErrorResponse,
    TransactionCreate,
    TransactionListItem,
    TransactionRead,
    TransactionUpdate,
)
from ..repository import PortfolioRepository


def register_transactions_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    historical_service: object,
) -> None:

    @router.get(
        "/portfolios/{portfolio_id}/transactions",
        response_model=list[TransactionListItem],
        responses={404: {"model": ErrorResponse}},
    )
    def list_transactions(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> list[TransactionListItem]:
        try:
            return repo.list_transactions(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.post("/transactions", response_model=TransactionRead, responses={400: {"model": ErrorResponse}})
    def create_transaction(payload: TransactionCreate, _auth: AuthContext = Depends(require_auth_rate_limited)) -> TransactionRead:
        try:
            result = repo.create_transaction(payload, _auth.user_id)
            threading.Thread(
                target=historical_service.backfill_single_asset,
                kwargs={"asset_id": payload.asset_id, "portfolio_id": payload.portfolio_id},
                daemon=True,
            ).start()
            return result
        except ValueError as exc:
            raise AppError(code="bad_request", message=str(exc), status_code=400) from exc

    @router.patch(
        "/transactions/{transaction_id}",
        response_model=TransactionRead,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def update_transaction(
        transaction_id: int,
        payload: TransactionUpdate,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> TransactionRead:
        try:
            return repo.update_transaction(transaction_id, payload, _auth.user_id)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovata" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.delete(
        "/transactions/{transaction_id}",
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def delete_transaction(transaction_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> dict[str, str]:
        try:
            repo.delete_transaction(transaction_id, _auth.user_id)
            return {"status": "ok"}
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovata" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc
