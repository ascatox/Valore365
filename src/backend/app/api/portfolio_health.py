from fastapi import APIRouter, Depends, Query

from ..auth import AuthContext, require_auth
from ..errors import AppError
from ..models import ErrorResponse
from ..repository import PortfolioRepository
from ..schemas.portfolio_doctor import DecumulationPlanResponse, MonteCarloProjectionResponse, PortfolioHealthResponse
from ..services.portfolio_doctor import analyze_portfolio_health, run_decumulation_plan, run_monte_carlo_projection


def register_portfolio_health_routes(router: APIRouter, repo: PortfolioRepository) -> None:
    @router.get(
        "/portfolios/{portfolio_id}/health",
        response_model=PortfolioHealthResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_portfolio_health(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth),
    ) -> PortfolioHealthResponse:
        try:
            return analyze_portfolio_health(repo, portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/monte-carlo",
        response_model=MonteCarloProjectionResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_monte_carlo_projection(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth),
    ) -> MonteCarloProjectionResponse:
        try:
            return run_monte_carlo_projection(repo, portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/decumulation",
        response_model=DecumulationPlanResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_decumulation_plan(
        portfolio_id: int,
        annual_withdrawal: float = Query(ge=0),
        years: int = Query(ge=1, le=80),
        inflation_rate_pct: float = Query(default=2.0, ge=0, le=20),
        other_income_annual: float = Query(default=0.0, ge=0),
        current_age: int | None = Query(default=None, ge=18, le=100),
        _auth: AuthContext = Depends(require_auth),
    ) -> DecumulationPlanResponse:
        try:
            return run_decumulation_plan(
                repo,
                portfolio_id,
                annual_withdrawal=annual_withdrawal,
                years=years,
                inflation_rate_pct=inflation_rate_pct,
                other_income_annual=other_income_annual,
                current_age=current_age,
                user_id=_auth.user_id,
            )
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
