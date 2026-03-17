from fastapi import APIRouter, Depends, Query

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..config import get_settings
from ..errors import AppError
from ..models import ErrorResponse
from ..repository import PortfolioRepository
from ..schemas.portfolio_doctor import (
    AggregateDecumulationPlanResponse,
    DecumulationPlanResponse,
    MonteCarloProjectionResponse,
    PortfolioHealthResponse,
    StressTestResponse,
    XRayResponse,
)
from ..services.portfolio_doctor import (
    analyze_portfolio_health,
    compute_portfolio_xray,
    run_aggregate_decumulation_plan,
    run_decumulation_plan,
    run_monte_carlo_projection,
    run_stress_test,
)


def register_portfolio_health_routes(router: APIRouter, repo: PortfolioRepository, finance_client: object = None, justetf_client: object = None) -> None:
    settings = get_settings()

    @router.get(
        "/portfolios/{portfolio_id}/health",
        response_model=PortfolioHealthResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_portfolio_health(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth_rate_limited),
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
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> MonteCarloProjectionResponse:
        try:
            return run_monte_carlo_projection(repo, portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/stress-test",
        response_model=StressTestResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_stress_test(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> StressTestResponse:
        try:
            return run_stress_test(repo, portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    # NOTE: aggregate route MUST be registered before the {portfolio_id} route
    # to prevent FastAPI from matching "aggregate" as a portfolio_id integer.
    @router.get(
        "/portfolios/aggregate/decumulation",
        response_model=AggregateDecumulationPlanResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_aggregate_decumulation_plan(
        portfolio_ids: list[int] = Query(min_length=1),
        annual_withdrawal: float = Query(ge=0),
        years: int = Query(ge=1, le=80),
        inflation_rate_pct: float = Query(default=2.0, ge=0, le=20),
        other_income_annual: float = Query(default=0.0, ge=0),
        current_age: int | None = Query(default=None, ge=18, le=100),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> AggregateDecumulationPlanResponse:
        try:
            return run_aggregate_decumulation_plan(
                repo,
                portfolio_ids=portfolio_ids,
                annual_withdrawal=annual_withdrawal,
                years=years,
                inflation_rate_pct=inflation_rate_pct,
                other_income_annual=other_income_annual,
                current_age=current_age,
                user_id=_auth.user_id,
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 400 if "valuta base" in message or "Seleziona almeno" in message else 404
            raise AppError(code="invalid_request" if status_code == 400 else "not_found", message=message, status_code=status_code) from exc

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
        _auth: AuthContext = Depends(require_auth_rate_limited),
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

    @router.get(
        "/portfolios/{portfolio_id}/xray",
        response_model=XRayResponse,
        responses={404: {"model": ErrorResponse}},
    )
    def get_portfolio_xray(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> XRayResponse:
        if not finance_client:
            raise AppError(code="not_configured", message="Finance client non disponibile", status_code=500)
        try:
            xray_justetf_client = justetf_client if settings.justetf_xray_auto_enrich_enabled_resolved else None
            return compute_portfolio_xray(
                repo,
                portfolio_id,
                _auth.user_id,
                finance_client,
                justetf_client=xray_justetf_client,
            )
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc
