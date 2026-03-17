from fastapi import APIRouter, Depends
from sqlalchemy import text

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..models import (
    ErrorResponse,
    PacExecutionConfirm,
    PacExecutionRead,
    PacRuleCreate,
    PacRuleRead,
    PacRuleUpdate,
    TransactionCreate,
)
from ..repository import PortfolioRepository


def register_pac_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    engine: object,
) -> None:

    @router.post(
        "/portfolios/{portfolio_id}/pac-rules",
        response_model=PacRuleRead,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def create_pac_rule(
        portfolio_id: int,
        payload: PacRuleCreate,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PacRuleRead:
        if payload.portfolio_id != portfolio_id:
            raise AppError(code="bad_request", message="portfolio_id nel path e nel body non corrispondono", status_code=400)
        try:
            rule = repo.create_pac_rule(payload, _auth.user_id)
            repo.generate_pending_executions(rule.id)
            return rule
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/pac-rules",
        response_model=list[PacRuleRead],
        responses={404: {"model": ErrorResponse}},
    )
    def list_pac_rules(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> list[PacRuleRead]:
        try:
            return repo.list_pac_rules(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/pac-rules/{rule_id}",
        response_model=PacRuleRead,
        responses={404: {"model": ErrorResponse}},
    )
    def get_pac_rule(rule_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> PacRuleRead:
        try:
            return repo.get_pac_rule(rule_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.patch(
        "/pac-rules/{rule_id}",
        response_model=PacRuleRead,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def update_pac_rule(
        rule_id: int,
        payload: PacRuleUpdate,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PacRuleRead:
        try:
            rule = repo.update_pac_rule(rule_id, payload, _auth.user_id)
            repo.generate_pending_executions(rule.id)
            return rule
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovata" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.delete("/pac-rules/{rule_id}", responses={404: {"model": ErrorResponse}})
    def delete_pac_rule(rule_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> dict[str, str]:
        try:
            repo.delete_pac_rule(rule_id, _auth.user_id)
            return {"status": "ok"}
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/pac-rules/{rule_id}/executions",
        response_model=list[PacExecutionRead],
        responses={404: {"model": ErrorResponse}},
    )
    def list_pac_executions(rule_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> list[PacExecutionRead]:
        try:
            return repo.list_pac_executions(rule_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/pac-executions/pending",
        response_model=list[PacExecutionRead],
        responses={404: {"model": ErrorResponse}},
    )
    def list_pending_pac_executions(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> list[PacExecutionRead]:
        try:
            return repo.list_pending_pac_executions(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.post(
        "/pac-executions/{execution_id}/confirm",
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def confirm_pac_execution(
        execution_id: int,
        payload: PacExecutionConfirm,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> dict[str, str]:
        try:
            # Get execution details
            with engine.begin() as conn:
                exec_row = conn.execute(
                    text(
                        """
                        select e.id, e.pac_rule_id, e.scheduled_date,
                               r.portfolio_id, r.asset_id, r.mode, r.amount::float8, r.quantity::float8
                        from pac_executions e
                        join pac_rules r on r.id = e.pac_rule_id
                        where e.id = :execution_id and e.status = 'pending' and r.owner_user_id = :user_id
                        """
                    ),
                    {"execution_id": execution_id, "user_id": _auth.user_id},
                ).mappings().fetchone()

            if exec_row is None:
                raise ValueError("Esecuzione PAC non trovata o gia processata")

            # Determine quantity based on mode
            if str(exec_row["mode"]) == "amount":
                quantity = float(exec_row["amount"]) / payload.price if payload.price > 0 else 0.0
            else:
                quantity = float(exec_row["quantity"]) if exec_row["quantity"] else 0.0

            if quantity <= 0:
                raise ValueError("Quantita calcolata non valida")

            from datetime import datetime as dt
            tx = repo.create_transaction(
                TransactionCreate(
                    portfolio_id=int(exec_row["portfolio_id"]),
                    asset_id=int(exec_row["asset_id"]),
                    side="buy",
                    trade_at=dt.combine(exec_row["scheduled_date"], dt.min.time()),
                    quantity=round(quantity, 8),
                    price=payload.price,
                    fees=payload.fees,
                    taxes=payload.taxes,
                    trade_currency=payload.trade_currency,
                    notes=payload.notes or f"PAC esecuzione #{execution_id}",
                ),
                _auth.user_id,
            )

            repo.confirm_pac_execution(execution_id, tx.id, payload.price, round(quantity, 8), _auth.user_id)
            return {"status": "ok", "transaction_id": str(tx.id)}

        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovata" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.post(
        "/pac-executions/{execution_id}/skip",
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def skip_pac_execution(
        execution_id: int,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> dict[str, str]:
        try:
            repo.skip_pac_execution(execution_id, _auth.user_id)
            return {"status": "ok"}
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovata" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc
