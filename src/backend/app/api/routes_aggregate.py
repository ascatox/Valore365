"""Vista aggregata: read-only endpoints over several portfolios read as one.

Every route is ``GET /portfolios/aggregate/<resource>?portfolio_ids=1&portfolio_ids=2``
and mirrors the query parameters and response model of the matching
``/portfolios/{portfolio_id}/<resource>`` route.

This module MUST be registered before any module that declares
``/portfolios/{portfolio_id}/...`` routes: Starlette matches routes in
registration order, and ``aggregate`` would otherwise hit the int path
parameter and fail with 422.

Response shape: models that carry ``portfolio_id`` report ``portfolio_id = 0``
and ``portfolio_ids`` = the normalized selected ids. Transactions keep their
own ``portfolio_id`` and add ``portfolio_name``.

Errors (shared with every aggregate read, see ``app.repository._scope``):
- empty selection, too many ids, mixed base currencies -> 400 ``invalid_request``
- a portfolio the user does not own -> 404 ``not_found``
"""

from collections.abc import Callable
from datetime import date
from typing import TypeVar

from fastapi import APIRouter, Depends, Query

from ..auth import AuthContext
from ..config import get_settings
from ..errors import AppError
from ..models import (
    AllocationItem,
    AssetCoverageItem,
    DataCoverageResponse,
    DrawdownResponse,
    ErrorResponse,
    GainTimeseriesPoint,
    HallOfFameResponse,
    IntradayTimeseriesPoint,
    MonthlyReturnsResponse,
    MWRResult,
    MWRTimeseriesPoint,
    PerformanceSummary,
    PeriodPerformer,
    PortfolioSummary,
    Position,
    RollingWindowsResponse,
    TimeSeriesPoint,
    TransactionListItem,
    TWRResult,
    TWRTimeseriesPoint,
    YearlyPerformanceResponse,
)
from ..rate_limit import require_auth_rate_limited
from ..repository import PortfolioRepository, aggregate_identity, normalize_portfolio_ids
from ..repository._scope import EMPTY_SCOPE_MESSAGE, MIXED_CURRENCY_MESSAGE, NOT_FOUND_MESSAGE
from ..schemas.portfolio_doctor import (
    AggregateDecumulationPlanResponse,
    MonteCarloProjectionResponse,
    PortfolioHealthResponse,
    StressTestResponse,
    XRayResponse,
)
from ..services.portfolio_doctor import (
    analyze_portfolio_health,
    compute_portfolio_xray,
    run_aggregate_decumulation_plan,
    run_monte_carlo_projection,
    run_stress_test,
)
from .portfolio_health import _parse_one_off_expenses, _validate_terminal_range

AGGREGATE_PREFIX = "/portfolios/aggregate"
MAX_AGGREGATE_PORTFOLIOS = 20
TOO_MANY_MESSAGE = f"Puoi aggregare al massimo {MAX_AGGREGATE_PORTFOLIOS} portafogli"

_ERRORS = {400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

T = TypeVar("T")


def aggregate_error(exc: ValueError, *, default_status: int = 404) -> AppError:
    """Map a ValueError raised by an aggregate read to the API error.

    Scope errors have fixed messages (app.repository._scope): an empty
    selection or mixed base currencies are 400 ``invalid_request``, a
    portfolio not owned by the user is 404 ``not_found``. Any other error
    keeps the status of the matching single-portfolio route:
    ``default_status`` 404 -> ``not_found``, 400 -> ``bad_request``.
    """
    message = str(exc)
    if message in (EMPTY_SCOPE_MESSAGE, MIXED_CURRENCY_MESSAGE, TOO_MANY_MESSAGE):
        return AppError(code="invalid_request", message=message, status_code=400)
    if message == NOT_FOUND_MESSAGE:
        return AppError(code="not_found", message=message, status_code=404)
    code = "not_found" if default_status == 404 else "bad_request"
    return AppError(code=code, message=message, status_code=default_status)


def _call(fn: Callable[[], T], *, default_status: int = 404) -> T:
    try:
        return fn()
    except ValueError as exc:
        raise aggregate_error(exc, default_status=default_status) from exc


def aggregate_portfolio_ids(
    portfolio_ids: list[int] = Query(
        default_factory=list,
        description="Portafogli da aggregare (parametro ripetuto), stessa valuta base.",
    ),
) -> list[int]:
    """Normalized ids of an aggregate request (duplicates and ids <= 0 dropped).

    An empty or too long selection is a 400, like every other scope error.
    Ownership and base currency are checked by the repository/services.
    """
    ids = normalize_portfolio_ids(portfolio_ids)
    if not ids:
        raise aggregate_error(ValueError(EMPTY_SCOPE_MESSAGE))
    if len(ids) > MAX_AGGREGATE_PORTFOLIOS:
        raise aggregate_error(ValueError(TOO_MANY_MESSAGE))
    return ids


def register_aggregate_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    performance_service: object,
    finance_client: object = None,
    justetf_client: object = None,
    ensure_target_allocation_enabled: Callable[[], None] = lambda: None,
) -> None:
    settings = get_settings()
    Ids = Depends(aggregate_portfolio_ids)
    Auth = Depends(require_auth_rate_limited)

    # --- Dashboard ---------------------------------------------------------

    @router.get(f"{AGGREGATE_PREFIX}/summary", response_model=PortfolioSummary, responses=_ERRORS)
    def get_aggregate_summary(ids: list[int] = Ids, _auth: AuthContext = Auth) -> PortfolioSummary:
        return _call(lambda: repo.get_summary_multi(ids, _auth.user_id))

    @router.get(f"{AGGREGATE_PREFIX}/positions", response_model=list[Position], responses=_ERRORS)
    def get_aggregate_positions(ids: list[int] = Ids, _auth: AuthContext = Auth) -> list[Position]:
        return _call(lambda: repo.get_positions_multi(ids, _auth.user_id))

    @router.get(f"{AGGREGATE_PREFIX}/allocation", response_model=list[AllocationItem], responses=_ERRORS)
    def get_aggregate_allocation(ids: list[int] = Ids, _auth: AuthContext = Auth) -> list[AllocationItem]:
        return _call(lambda: repo.get_allocation_multi(ids, _auth.user_id))

    @router.get(f"{AGGREGATE_PREFIX}/performers", response_model=list[PeriodPerformer], responses=_ERRORS)
    def get_aggregate_performers(
        ids: list[int] = Ids,
        days: int = Query(default=1, ge=1, le=3650),
        _auth: AuthContext = Auth,
    ) -> list[PeriodPerformer]:
        return _call(lambda: repo.get_period_performers_multi(ids, _auth.user_id, days))

    @router.get(f"{AGGREGATE_PREFIX}/timeseries", response_model=list[TimeSeriesPoint], responses=_ERRORS)
    def get_aggregate_timeseries(
        ids: list[int] = Ids,
        range: str = Query(default="1y", pattern="^1y$"),
        interval: str = Query(default="1d", pattern="^1d$"),
        _auth: AuthContext = Auth,
    ) -> list[TimeSeriesPoint]:
        return _call(
            lambda: repo.get_timeseries_multi(ids, range_value=range, interval=interval, user_id=_auth.user_id),
            default_status=400,
        )

    @router.get(
        f"{AGGREGATE_PREFIX}/intraday-timeseries", response_model=list[IntradayTimeseriesPoint], responses=_ERRORS,
    )
    def get_aggregate_intraday_timeseries(
        ids: list[int] = Ids, _auth: AuthContext = Auth,
    ) -> list[IntradayTimeseriesPoint]:
        return _call(
            lambda: repo.get_intraday_timeseries_multi(ids, _auth.user_id, finance_client),
            default_status=400,
        )

    @router.get(f"{AGGREGATE_PREFIX}/transactions", response_model=list[TransactionListItem], responses=_ERRORS)
    def list_aggregate_transactions(ids: list[int] = Ids, _auth: AuthContext = Auth) -> list[TransactionListItem]:
        return _call(lambda: repo.list_transactions_multi(ids, _auth.user_id))

    @router.get(f"{AGGREGATE_PREFIX}/data-coverage", response_model=DataCoverageResponse, responses=_ERRORS)
    def get_aggregate_data_coverage(
        ids: list[int] = Ids,
        days: int = Query(default=365, ge=1, le=2000),
        threshold_pct: float = Query(default=80, ge=0, le=100),
        _auth: AuthContext = Auth,
    ) -> DataCoverageResponse:
        ensure_target_allocation_enabled()
        rows = _call(lambda: repo.get_price_coverage_multi(ids, _auth.user_id, days=days))
        assets = [AssetCoverageItem(**r) for r in rows]
        sufficient = all(a.coverage_pct >= threshold_pct for a in assets) if assets else True
        return DataCoverageResponse(
            **aggregate_identity(ids),
            days=days,
            sufficient=sufficient,
            threshold_pct=threshold_pct,
            assets=assets,
        )

    # --- Performance -------------------------------------------------------
    # Same status mapping as the single routes: "not found" 404, else 400.

    def _perf(fn: Callable[[], T]) -> T:
        return _call(fn, default_status=400)

    @router.get(f"{AGGREGATE_PREFIX}/performance/summary", response_model=PerformanceSummary, responses=_ERRORS)
    def get_aggregate_performance_summary(
        ids: list[int] = Ids,
        period: str = Query(default="1y", pattern="^(1m|3m|6m|ytd|1y|3y|all)$"),
        _auth: AuthContext = Auth,
    ) -> PerformanceSummary:
        return _perf(lambda: performance_service.get_performance_summary(ids, _auth.user_id, period))

    @router.get(f"{AGGREGATE_PREFIX}/performance/twr", response_model=TWRResult, responses=_ERRORS)
    def get_aggregate_performance_twr(
        ids: list[int] = Ids,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> TWRResult:
        return _perf(lambda: performance_service.calculate_twr(ids, _auth.user_id, start_date=start_date, end_date=end_date))

    @router.get(
        f"{AGGREGATE_PREFIX}/performance/twr/timeseries", response_model=list[TWRTimeseriesPoint], responses=_ERRORS,
    )
    def get_aggregate_performance_twr_timeseries(
        ids: list[int] = Ids,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> list[TWRTimeseriesPoint]:
        return _perf(
            lambda: performance_service.get_twr_timeseries(ids, _auth.user_id, start_date=start_date, end_date=end_date)
        )

    @router.get(
        f"{AGGREGATE_PREFIX}/performance/gain/timeseries", response_model=list[GainTimeseriesPoint], responses=_ERRORS,
    )
    def get_aggregate_performance_gain_timeseries(
        ids: list[int] = Ids,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> list[GainTimeseriesPoint]:
        return _perf(
            lambda: performance_service.get_gain_timeseries(ids, _auth.user_id, start_date=start_date, end_date=end_date)
        )

    @router.get(
        f"{AGGREGATE_PREFIX}/performance/mwr/timeseries", response_model=list[MWRTimeseriesPoint], responses=_ERRORS,
    )
    def get_aggregate_performance_mwr_timeseries(
        ids: list[int] = Ids,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> list[MWRTimeseriesPoint]:
        return _perf(
            lambda: performance_service.get_mwr_timeseries(ids, _auth.user_id, start_date=start_date, end_date=end_date)
        )

    @router.get(f"{AGGREGATE_PREFIX}/performance/mwr", response_model=MWRResult, responses=_ERRORS)
    def get_aggregate_performance_mwr(
        ids: list[int] = Ids,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> MWRResult:
        return _perf(lambda: performance_service.calculate_mwr(ids, _auth.user_id, start_date=start_date, end_date=end_date))

    @router.get(
        f"{AGGREGATE_PREFIX}/performance/monthly-returns", response_model=MonthlyReturnsResponse, responses=_ERRORS,
    )
    def get_aggregate_monthly_returns(
        ids: list[int] = Ids,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> MonthlyReturnsResponse:
        return _perf(lambda: performance_service.get_monthly_returns(ids, _auth.user_id, start_date, end_date))

    @router.get(
        f"{AGGREGATE_PREFIX}/performance/yearly", response_model=YearlyPerformanceResponse, responses=_ERRORS,
    )
    def get_aggregate_performance_yearly(ids: list[int] = Ids, _auth: AuthContext = Auth) -> YearlyPerformanceResponse:
        return _perf(lambda: performance_service.get_yearly_returns(ids, _auth.user_id))

    @router.get(f"{AGGREGATE_PREFIX}/performance/drawdown", response_model=DrawdownResponse, responses=_ERRORS)
    def get_aggregate_drawdown(
        ids: list[int] = Ids,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> DrawdownResponse:
        return _perf(lambda: performance_service.get_drawdown(ids, _auth.user_id, start_date, end_date))

    @router.get(
        f"{AGGREGATE_PREFIX}/performance/rolling-windows", response_model=RollingWindowsResponse, responses=_ERRORS,
    )
    def get_aggregate_rolling_windows(
        ids: list[int] = Ids,
        window_months: int = Query(default=12, ge=6, le=60),
        risk_free_rate: float = Query(default=2.0, ge=0, le=20),
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> RollingWindowsResponse:
        return _perf(
            lambda: performance_service.get_rolling_windows(
                ids, _auth.user_id, window_months, risk_free_rate, start_date, end_date,
            )
        )

    @router.get(
        f"{AGGREGATE_PREFIX}/performance/hall-of-fame", response_model=HallOfFameResponse, responses=_ERRORS,
    )
    def get_aggregate_hall_of_fame(
        ids: list[int] = Ids,
        top_n: int = Query(default=5, ge=1, le=20),
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Auth,
    ) -> HallOfFameResponse:
        return _perf(lambda: performance_service.get_hall_of_fame(ids, _auth.user_id, top_n, start_date, end_date))

    # --- Portfolio Doctor --------------------------------------------------

    @router.get(f"{AGGREGATE_PREFIX}/health", response_model=PortfolioHealthResponse, responses=_ERRORS)
    def get_aggregate_health(ids: list[int] = Ids, _auth: AuthContext = Auth) -> PortfolioHealthResponse:
        return _call(lambda: analyze_portfolio_health(repo, ids, _auth.user_id))

    @router.get(f"{AGGREGATE_PREFIX}/monte-carlo", response_model=MonteCarloProjectionResponse, responses=_ERRORS)
    def get_aggregate_monte_carlo(ids: list[int] = Ids, _auth: AuthContext = Auth) -> MonteCarloProjectionResponse:
        return _call(lambda: run_monte_carlo_projection(repo, ids, _auth.user_id))

    @router.get(f"{AGGREGATE_PREFIX}/stress-test", response_model=StressTestResponse, responses=_ERRORS)
    def get_aggregate_stress_test(ids: list[int] = Ids, _auth: AuthContext = Auth) -> StressTestResponse:
        return _call(lambda: run_stress_test(repo, ids, _auth.user_id))

    @router.get(f"{AGGREGATE_PREFIX}/xray", response_model=XRayResponse, responses=_ERRORS)
    def get_aggregate_xray(ids: list[int] = Ids, _auth: AuthContext = Auth) -> XRayResponse:
        if not finance_client:
            raise AppError(code="not_configured", message="Finance client non disponibile", status_code=500)
        xray_justetf_client = justetf_client if settings.justetf_xray_auto_enrich_enabled_resolved else None
        return _call(
            lambda: compute_portfolio_xray(repo, ids, _auth.user_id, finance_client, justetf_client=xray_justetf_client)
        )

    @router.get(
        f"{AGGREGATE_PREFIX}/decumulation", response_model=AggregateDecumulationPlanResponse, responses=_ERRORS,
    )
    def get_aggregate_decumulation_plan(
        ids: list[int] = Ids,
        annual_withdrawal: float = Query(ge=0),
        years: int = Query(ge=1, le=80),
        inflation_rate_pct: float = Query(default=2.0, ge=0, le=20),
        other_income_annual: float = Query(default=0.0, ge=0),
        capital_gains_tax_rate_pct: float = Query(default=26.0, ge=0, le=100),
        current_age: int | None = Query(default=None, ge=18, le=100),
        capital_floor: float = Query(default=0.0, ge=0),
        pension_annual: float = Query(default=0.0, ge=0),
        pension_start_age: int | None = Query(default=None, ge=18, le=100),
        one_off_ages: list[int] = Query(default_factory=list, max_length=50),
        one_off_amounts: list[float] = Query(default_factory=list, max_length=50),
        terminal_target_min: float = Query(default=0.0, ge=0),
        terminal_target_max: float = Query(default=0.0, ge=0),
        _auth: AuthContext = Auth,
    ) -> AggregateDecumulationPlanResponse:
        one_off_expenses = _parse_one_off_expenses(one_off_ages, one_off_amounts)
        terminal_max = _validate_terminal_range(terminal_target_min, terminal_target_max)
        return _call(
            lambda: run_aggregate_decumulation_plan(
                repo,
                portfolio_ids=ids,
                annual_withdrawal=annual_withdrawal,
                years=years,
                inflation_rate_pct=inflation_rate_pct,
                other_income_annual=other_income_annual,
                capital_gains_tax_rate_pct=capital_gains_tax_rate_pct,
                current_age=current_age,
                user_id=_auth.user_id,
                capital_floor=capital_floor,
                pension_annual=pension_annual,
                pension_start_age=pension_start_age,
                one_off_expenses=one_off_expenses,
                terminal_target_min=terminal_target_min,
                terminal_target_max=terminal_max,
            )
        )
