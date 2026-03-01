from datetime import date

from app.models import CashFlowEntry
from app.performance_service import PerformanceService


class _FakeRepo:
    def __init__(self, created: date, values: dict[date, float], cashflows: list[CashFlowEntry] | None = None) -> None:
        self.created = created
        self.values = values
        self.cashflows = cashflows or []

    def get_portfolio_created_date(self, portfolio_id: int, user_id: str) -> date:
        return self.created

    def get_external_cashflows(self, portfolio_id: int, user_id: str, start_date: date | None = None, end_date: date | None = None):
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
