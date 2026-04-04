from datetime import date

from app.models import CashFlowEntry
from app.services.performance_service import PerformanceService


class _FakeRepo:
    def __init__(self, created: date, values: dict[date, float], cashflows: list[CashFlowEntry] | None = None) -> None:
        self.created = created
        self.values = values
        self.cashflows = cashflows or []

    def get_portfolio_created_date(self, portfolio_id: int, user_id: str) -> date:
        return self.created

    def get_external_cashflows(self, portfolio_id: int, user_id: str, start_date: date | None = None, end_date: date | None = None, include_trades: bool = False):
        out: list[CashFlowEntry] = []
        for cf in self.cashflows:
            d = date.fromisoformat(cf.date)
            if start_date and d < start_date:
                continue
            if end_date and d > end_date:
                continue
            out.append(cf)
        return out

    def get_portfolio_value_at_date(self, portfolio_id: int, user_id: str, target_date: date) -> float:
        return float(self.values.get(target_date, 0.0))


def test_twr_and_mwr_zero_on_empty_portfolio():
    day = date(2026, 1, 1)
    service = PerformanceService(_FakeRepo(created=day, values={day: 0.0}))

    twr = service.calculate_twr(1, 'u', day, day)
    mwr = service.calculate_mwr(1, 'u', day, day)

    assert twr.twr_pct == 0.0
    assert mwr.mwr_pct == 0.0
    assert mwr.converged is True


def test_mwr_simple_one_year_growth():
    start = date(2025, 1, 1)
    end = date(2026, 1, 1)
    service = PerformanceService(_FakeRepo(created=start, values={start: 100.0, end: 110.0}))

    result = service.calculate_mwr(1, 'u', start, end)

    assert result.converged is True
    assert result.mwr_pct is not None
    assert abs(result.mwr_pct - 10.0) < 0.05


def test_twr_timeseries_accounts_for_external_cashflow():
    start = date(2026, 1, 1)
    mid = date(2026, 1, 2)
    end = date(2026, 1, 3)
    repo = _FakeRepo(
        created=start,
        values={
            start: 100.0,
            mid: 170.0,
            end: 180.0,
        },
        cashflows=[
            CashFlowEntry(date=mid.isoformat(), side='deposit', amount=50.0),
        ],
    )
    service = PerformanceService(repo)

    points = service.get_twr_timeseries(1, 'u', start, end)

    assert len(points) == 3
    assert points[0].cumulative_twr_pct == 0.0
    # Day 2 return = (170 - 100 - 50) / 100 = 20%
    assert abs(points[1].cumulative_twr_pct - 20.0) < 0.01


def test_monthly_returns_and_hall_of_fame_rank_periods_correctly():
    start = date(2026, 1, 30)
    end = date(2026, 2, 2)
    repo = _FakeRepo(
        created=start,
        values={
            start: 100.0,
            date(2026, 1, 31): 110.0,
            date(2026, 2, 1): 121.0,
            end: 133.1,
        },
    )
    service = PerformanceService(repo)

    monthly = service.get_monthly_returns(1, 'u', start, end)
    hall = service.get_hall_of_fame(1, 'u', top_n=1, start_date=start, end_date=end)

    assert [(cell.year, cell.month, round(cell.return_pct, 2)) for cell in monthly.cells] == [
        (2026, 1, 10.0),
        (2026, 2, 21.0),
    ]
    assert len(monthly.yearly_returns) == 1
    assert round(monthly.yearly_returns[0].return_pct, 2) == 33.1

    assert hall.best_months[0].label == 'Feb 2026'
    assert round(hall.best_months[0].return_pct, 2) == 21.0
    assert hall.worst_months[0].label == 'Gen 2026'
    assert round(hall.worst_months[0].return_pct, 2) == 10.0


def test_drawdown_tracks_peak_trough_and_current_drawdown():
    start = date(2026, 1, 1)
    end = date(2026, 1, 4)
    repo = _FakeRepo(
        created=start,
        values={
            start: 100.0,
            date(2026, 1, 2): 120.0,
            date(2026, 1, 3): 90.0,
            end: 95.0,
        },
    )
    service = PerformanceService(repo)

    drawdown = service.get_drawdown(1, 'u', start, end)

    assert round(drawdown.max_drawdown_pct, 2) == -25.0
    assert drawdown.max_drawdown_start == '2026-01-02'
    assert drawdown.max_drawdown_end == '2026-01-03'
    assert drawdown.peak_date == '2026-01-02'
    assert drawdown.peak_value == 120.0
    assert round(drawdown.current_drawdown_pct, 2) == -20.83


def test_rolling_windows_exposes_cagr_volatility_and_sharpe():
    start = date(2026, 1, 30)
    end = date(2026, 2, 2)
    repo = _FakeRepo(
        created=start,
        values={
            start: 100.0,
            date(2026, 1, 31): 110.0,
            date(2026, 2, 1): 121.0,
            end: 133.1,
        },
    )
    service = PerformanceService(repo)

    rolling = service.get_rolling_windows(1, 'u', window_months=2, risk_free_rate=2.0, start_date=start, end_date=end)

    assert rolling.window_months == 2
    assert len(rolling.points) == 1
    point = rolling.points[0]
    assert point.date == '2026-02'
    assert point.cagr_pct is not None and point.cagr_pct > 0
    assert point.volatility_pct is not None and point.volatility_pct > 0
    assert point.sharpe_ratio is not None and point.sharpe_ratio > 0
