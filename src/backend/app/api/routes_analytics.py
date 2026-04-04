from datetime import date

from fastapi import APIRouter, Depends, Query

from ..auth import AuthContext
from ..rate_limit import require_auth_rate_limited
from ..errors import AppError
from ..models import (
    AllocationItem,
    DrawdownResponse,
    ErrorResponse,
    GainTimeseriesPoint,
    HallOfFameResponse,
    IntradayTimeseriesPoint,
    MonthlyReturnsResponse,
    MWRResult,
    MWRTimeseriesPoint,
    PerformanceSummary,
    PortfolioSummary,
    Position,
    RollingWindowsResponse,
    TimeSeriesPoint,
    TWRResult,
    TWRTimeseriesPoint,
)
from ..repository import PortfolioRepository


def register_analytics_routes(
    router: APIRouter,
    repo: PortfolioRepository,
    performance_service: object,
    finance_client: object,
) -> None:

    @router.get(
        "/portfolios/{portfolio_id}/positions", response_model=list[Position], responses={404: {"model": ErrorResponse}}
    )
    def get_positions(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> list[Position]:
        try:
            return repo.get_positions(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get("/portfolios/{portfolio_id}/summary", response_model=PortfolioSummary, responses={404: {"model": ErrorResponse}})
    def get_summary(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> PortfolioSummary:
        try:
            return repo.get_summary(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/summary",
        response_model=PerformanceSummary,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_performance_summary(
        portfolio_id: int,
        period: str = Query(default="1y", pattern="^(1m|3m|6m|ytd|1y|3y|all)$"),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> PerformanceSummary:
        try:
            return performance_service.get_performance_summary(portfolio_id, _auth.user_id, period)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/twr",
        response_model=TWRResult,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_performance_twr(
        portfolio_id: int,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> TWRResult:
        try:
            return performance_service.calculate_twr(portfolio_id, _auth.user_id, start_date=start_date, end_date=end_date)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/twr/timeseries",
        response_model=list[TWRTimeseriesPoint],
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_performance_twr_timeseries(
        portfolio_id: int,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> list[TWRTimeseriesPoint]:
        try:
            return performance_service.get_twr_timeseries(portfolio_id, _auth.user_id, start_date=start_date, end_date=end_date)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/gain/timeseries",
        response_model=list[GainTimeseriesPoint],
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_performance_gain_timeseries(
        portfolio_id: int,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> list[GainTimeseriesPoint]:
        try:
            return performance_service.get_gain_timeseries(portfolio_id, _auth.user_id, start_date=start_date, end_date=end_date)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/mwr/timeseries",
        response_model=list[MWRTimeseriesPoint],
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_performance_mwr_timeseries(
        portfolio_id: int,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> list[MWRTimeseriesPoint]:
        try:
            return performance_service.get_mwr_timeseries(portfolio_id, _auth.user_id, start_date=start_date, end_date=end_date)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/mwr",
        response_model=MWRResult,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_performance_mwr(
        portfolio_id: int,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> MWRResult:
        try:
            return performance_service.calculate_mwr(portfolio_id, _auth.user_id, start_date=start_date, end_date=end_date)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/timeseries",
        response_model=list[TimeSeriesPoint],
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_timeseries(
        portfolio_id: int,
        range: str = Query(default="1y", pattern="^1y$"),
        interval: str = Query(default="1d", pattern="^1d$"),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> list[TimeSeriesPoint]:
        try:
            return repo.get_timeseries(portfolio_id, range_value=range, interval=interval, user_id=_auth.user_id)
        except ValueError as exc:
            message = str(exc)
            status = 404 if "portfolio non trovato" in message.lower() else 400
            code = "not_found" if status == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status) from exc

    @router.get(
        "/portfolios/{portfolio_id}/intraday-timeseries",
        response_model=list[IntradayTimeseriesPoint],
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_intraday_timeseries(
        portfolio_id: int,
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> list[IntradayTimeseriesPoint]:
        try:
            return repo.get_intraday_timeseries(portfolio_id, _auth.user_id, finance_client)
        except ValueError as exc:
            message = str(exc)
            status = 404 if "portfolio non trovato" in message.lower() else 400
            code = "not_found" if status == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status) from exc

    @router.get(
        "/portfolios/{portfolio_id}/allocation",
        response_model=list[AllocationItem],
        responses={404: {"model": ErrorResponse}},
    )
    def get_allocation(portfolio_id: int, _auth: AuthContext = Depends(require_auth_rate_limited)) -> list[AllocationItem]:
        try:
            return repo.get_allocation(portfolio_id, _auth.user_id)
        except ValueError as exc:
            raise AppError(code="not_found", message=str(exc), status_code=404) from exc

    # --- Advanced Performance Analytics ---

    @router.get(
        "/portfolios/{portfolio_id}/performance/monthly-returns",
        response_model=MonthlyReturnsResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_monthly_returns(
        portfolio_id: int,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> MonthlyReturnsResponse:
        try:
            return performance_service.get_monthly_returns(portfolio_id, _auth.user_id, start_date, end_date)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/drawdown",
        response_model=DrawdownResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_drawdown(
        portfolio_id: int,
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> DrawdownResponse:
        try:
            return performance_service.get_drawdown(portfolio_id, _auth.user_id, start_date, end_date)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/rolling-windows",
        response_model=RollingWindowsResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_rolling_windows(
        portfolio_id: int,
        window_months: int = Query(default=12, ge=6, le=60),
        risk_free_rate: float = Query(default=2.0, ge=0, le=20),
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> RollingWindowsResponse:
        try:
            return performance_service.get_rolling_windows(
                portfolio_id, _auth.user_id, window_months, risk_free_rate, start_date, end_date,
            )
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc

    @router.get(
        "/portfolios/{portfolio_id}/performance/hall-of-fame",
        response_model=HallOfFameResponse,
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
    )
    def get_hall_of_fame(
        portfolio_id: int,
        top_n: int = Query(default=5, ge=1, le=20),
        start_date: date | None = Query(default=None),
        end_date: date | None = Query(default=None),
        _auth: AuthContext = Depends(require_auth_rate_limited),
    ) -> HallOfFameResponse:
        try:
            return performance_service.get_hall_of_fame(portfolio_id, _auth.user_id, top_n, start_date, end_date)
        except ValueError as exc:
            message = str(exc)
            status_code = 404 if "non trovato" in message.lower() else 400
            code = "not_found" if status_code == 404 else "bad_request"
            raise AppError(code=code, message=message, status_code=status_code) from exc
