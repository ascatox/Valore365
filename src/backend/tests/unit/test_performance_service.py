from datetime import date, timedelta

from app.models import CashFlowEntry
from app.services.performance_service import PerformanceService


class _FakeRepo:
    def __init__(
        self,
        created: date,
        values: dict[date, float],
        cashflows: list[CashFlowEntry] | None = None,
        inception: date | None = None,
    ) -> None:
        self.created = created
        self.values = values
        self.cashflows = cashflows or []
        # First transaction date; falls back to the record creation date,
        # like the repository does for portfolios with no transactions.
        self.inception = inception
        self.batch_calls = 0

    def get_portfolio_created_date(self, portfolio_id: int, user_id: str) -> date:
        return self.created

    def get_portfolio_inception_date(self, portfolio_id: int, user_id: str) -> date:
        return self.inception or self.created

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

    def get_portfolio_values_in_range(self, portfolio_id: int, user_id: str, target_dates) -> dict[date, float]:
        self.batch_calls += 1
        return {d: float(self.values.get(d, 0.0)) for d in target_dates}


def test_performance_starts_at_first_transaction_not_record_creation():
    # Imported multi-year history: the portfolio record was created long
    # after the first trade. Windows must start at the first trade, or the
    # whole history before the import day would be silently dropped.
    inception = date(2023, 10, 25)
    created = date(2026, 1, 1)
    end = date(2026, 9, 2)
    repo = _FakeRepo(
        created=created,
        inception=inception,
        values={inception: 1000.0, created: 1900.0, end: 2000.0},
    )
    service = PerformanceService(repo)

    twr = service.calculate_twr(1, 'u', None, end)
    mwr = service.calculate_mwr(1, 'u', None, end)

    assert twr.start_date == inception.isoformat()
    assert mwr.start_date == inception.isoformat()
    # 1000 -> 2000 over the full history, not 1900 -> 2000 since creation
    assert abs(twr.twr_pct - 100.0) < 0.01
    assert abs(mwr.mwr_pct - 100.0) < 0.01


def test_explicit_start_date_is_clamped_to_inception_not_creation():
    inception = date(2023, 10, 25)
    created = date(2026, 1, 1)
    end = date(2026, 9, 2)
    repo = _FakeRepo(
        created=created,
        inception=inception,
        values={inception: 1000.0, created: 1900.0, end: 2000.0},
    )
    service = PerformanceService(repo)

    result = service.calculate_twr(1, 'u', date(2020, 1, 1), end)

    assert result.start_date == inception.isoformat()


def test_period_all_starts_at_inception():
    inception = date(2023, 10, 25)
    today = date.today()
    repo = _FakeRepo(
        created=date(2026, 1, 1),
        inception=inception,
        values={inception: 1000.0, today: 2000.0},
    )
    service = PerformanceService(repo)

    summary = service.get_performance_summary(1, 'u', 'all')

    assert summary.start_date == inception.isoformat()
    assert abs(summary.twr.twr_pct - 100.0) < 0.01


def test_inception_falls_back_to_creation_without_transactions():
    created = date(2026, 1, 1)
    end = date(2026, 9, 2)
    repo = _FakeRepo(created=created, values={created: 1000.0, end: 1100.0})
    service = PerformanceService(repo)

    result = service.calculate_twr(1, 'u', None, end)

    assert result.start_date == created.isoformat()
    assert abs(result.twr_pct - 10.0) < 0.01


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


def test_mwr_short_period_is_a_period_return():
    # 100 -> 105 in ~6 months: mwr_pct must be the 5% period return
    # (comparable with twr_pct), not the annualized IRR (~10.3%).
    start = date(2025, 1, 1)
    end = date(2025, 7, 2)
    service = PerformanceService(_FakeRepo(created=start, values={start: 100.0, end: 105.0}))

    result = service.calculate_mwr(1, 'u', start, end)

    assert result.converged is True
    assert abs(result.mwr_pct - 5.0) < 0.05
    assert result.mwr_annualized_pct is None


def test_mwr_one_year_period_exposes_annualized_rate():
    start = date(2025, 1, 1)
    end = date(2026, 1, 1)
    service = PerformanceService(_FakeRepo(created=start, values={start: 100.0, end: 110.0}))

    result = service.calculate_mwr(1, 'u', start, end)

    assert result.converged is True
    assert result.mwr_annualized_pct is not None
    assert abs(result.mwr_annualized_pct - result.mwr_pct) < 0.01


def test_mwr_deposit_on_start_day_not_double_counted():
    # The deposit dated 'start' is already inside start_value: it must not
    # be added again as a t=0 flow.
    start = date(2025, 1, 1)
    end = date(2026, 1, 1)
    repo = _FakeRepo(
        created=start,
        values={start: 1000.0, end: 1100.0},
        cashflows=[CashFlowEntry(date=start.isoformat(), side='deposit', amount=1000.0)],
    )
    service = PerformanceService(repo)

    result = service.calculate_mwr(1, 'u', start, end)

    assert result.converged is True
    assert abs(result.mwr_pct - 10.0) < 0.05


def test_mwr_trade_fallback_buy_on_start_day():
    # Single buy of 1000 on the start day, worth 1200 one year later.
    # Portfolio value already reflects the bought assets, no cash adjustment.
    start = date(2025, 1, 1)
    end = date(2026, 1, 1)
    repo = _FakeRepo(
        created=start,
        values={start: 1000.0, end: 1200.0},
        cashflows=[CashFlowEntry(date=start.isoformat(), side='buy', amount=1000.0)],
    )
    service = PerformanceService(repo)

    result = service.calculate_mwr(1, 'u', start, end)

    assert result.converged is True
    assert abs(result.mwr_pct - 20.0) < 0.05


def test_mwr_trade_fallback_mid_period_buy():
    # Buy 1000 after 182 days, worth 1200 at the end of the year:
    # 1200/1000 = (1+r)^(183/365) -> r = 1.2^(365/183) - 1 ~ 43.86%
    start = date(2025, 1, 1)
    buy_day = date(2025, 7, 2)
    end = date(2026, 1, 1)
    repo = _FakeRepo(
        created=start,
        values={start: 0.0, end: 1200.0},
        cashflows=[CashFlowEntry(date=buy_day.isoformat(), side='buy', amount=1000.0)],
    )
    service = PerformanceService(repo)

    result = service.calculate_mwr(1, 'u', start, end)

    assert result.converged is True
    assert abs(result.mwr_pct - 43.86) < 0.1


def test_mwr_dividend_stays_internal():
    # A dividend kept inside the portfolio is income, not an investor
    # contribution: MWR must equal the plain growth of the value.
    start = date(2025, 1, 1)
    mid = date(2025, 7, 2)
    end = date(2026, 1, 1)
    repo = _FakeRepo(
        created=start,
        values={start: 1000.0, end: 1100.0},
        cashflows=[CashFlowEntry(date=mid.isoformat(), side='dividend', amount=50.0)],
    )
    service = PerformanceService(repo)

    result = service.calculate_mwr(1, 'u', start, end)

    assert result.converged is True
    assert abs(result.mwr_pct - 10.0) < 0.05


def test_mwr_timeseries_last_point_matches_calculate_mwr():
    start = date(2026, 1, 1)
    end = date(2026, 1, 11)
    values: dict[date, float] = {}
    for offset in range(11):
        day = date(2026, 1, 1 + offset)
        values[day] = 1000.0 + 2.0 * offset + (500.0 if offset >= 5 else 0.0)
    repo = _FakeRepo(
        created=start,
        values=values,
        cashflows=[
            CashFlowEntry(date=start.isoformat(), side='deposit', amount=1000.0),
            CashFlowEntry(date=date(2026, 1, 6).isoformat(), side='deposit', amount=500.0),
        ],
    )
    service = PerformanceService(repo)

    result = service.calculate_mwr(1, 'u', start, end)
    points = service.get_mwr_timeseries(1, 'u', start, end)

    assert result.converged is True
    assert points[-1].date == end.isoformat()
    assert points[-1].cumulative_mwr_pct is not None
    assert abs(points[-1].cumulative_mwr_pct - result.mwr_pct) < 1e-6


def test_twr_trade_fallback_counts_buys_as_external_flows():
    # Portfolio value includes bought assets without deducting cash, so in
    # the buy/sell fallback the buy cost must be treated as a deposit.
    start = date(2026, 1, 1)
    mid = date(2026, 1, 2)
    end = date(2026, 1, 3)
    repo = _FakeRepo(
        created=start,
        values={start: 1000.0, mid: 2010.0, end: 2010.0},
        cashflows=[CashFlowEntry(date=mid.isoformat(), side='buy', amount=1000.0)],
    )
    service = PerformanceService(repo)

    result = service.calculate_twr(1, 'u', start, end)

    # Day 2 return = (2010 - 1000 - 1000) / 1000 = 1%
    assert abs(result.twr_pct - 1.0) < 0.01


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


class _CountingRepo(_FakeRepo):
    """Fails loudly if anything falls back to one valuation query per day."""

    def get_portfolio_value_at_date(self, portfolio_id: int, user_id: str, target_date: date) -> float:
        raise AssertionError(
            "per-date valuation is an N+1: one connection checkout per day drained "
            "the pool in production. Use get_portfolio_values_in_range instead."
        )


def _counting_repo(start: date, end: date) -> _CountingRepo:
    values = {}
    cursor = start
    day = 0
    while cursor <= end:
        values[cursor] = 1000.0 + day
        cursor += timedelta(days=1)
        day += 1
    return _CountingRepo(created=start, values=values)


def test_twr_timeseries_makes_one_batch_call_for_a_long_range():
    start, end = date(2025, 1, 1), date(2026, 2, 4)
    repo = _counting_repo(start, end)
    service = PerformanceService(repo)

    points = service.get_twr_timeseries(1, 'u', start_date=start, end_date=end)

    assert len(points) == 400
    assert repo.batch_calls == 1


def test_gain_timeseries_makes_one_batch_call_for_a_long_range():
    start, end = date(2025, 1, 1), date(2026, 2, 4)
    repo = _counting_repo(start, end)
    service = PerformanceService(repo)

    points = service.get_gain_timeseries(1, 'u', start_date=start, end_date=end)

    assert len(points) == 400
    assert repo.batch_calls == 1


def test_drawdown_makes_one_batch_call_for_a_long_range():
    # get_drawdown, get_monthly_returns, get_rolling_windows and get_hall_of_fame
    # all run through _build_monthly_returns, so this covers the daily loop for all four.
    start, end = date(2025, 1, 1), date(2026, 2, 4)
    repo = _counting_repo(start, end)
    service = PerformanceService(repo)

    drawdown = service.get_drawdown(1, 'u', start_date=start, end_date=end)

    assert len(drawdown.points) == 400
    assert repo.batch_calls == 1


def test_mwr_timeseries_makes_one_batch_call_for_a_long_range():
    start, end = date(2025, 1, 1), date(2026, 2, 4)
    repo = _counting_repo(start, end)
    service = PerformanceService(repo)

    points = service.get_mwr_timeseries(1, 'u', start_date=start, end_date=end)

    assert len(points) > 1
    assert repo.batch_calls == 1


def test_twr_calculation_batches_its_cashflow_day_valuations():
    start, end = date(2025, 1, 1), date(2026, 2, 4)
    repo = _counting_repo(start, end)
    repo.cashflows = [
        CashFlowEntry(date=date(2025, 3, 1).isoformat(), side='deposit', amount=500.0),
        CashFlowEntry(date=date(2025, 7, 1).isoformat(), side='deposit', amount=250.0),
        CashFlowEntry(date=date(2025, 11, 1).isoformat(), side='withdrawal', amount=-100.0),
    ]
    service = PerformanceService(repo)

    twr = service.calculate_twr(1, 'u', start, end)

    assert twr.start_date == start.isoformat()
    assert repo.batch_calls == 1


class _CallCountingRepo(_FakeRepo):
    """Counts the repository reads a single request makes."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.inception_calls = 0
        self.cashflow_calls = 0

    def get_portfolio_inception_date(self, portfolio_id: int, user_id: str) -> date:
        self.inception_calls += 1
        return super().get_portfolio_inception_date(portfolio_id, user_id)

    def get_external_cashflows(self, portfolio_id: int, user_id: str, start_date=None, end_date=None, include_trades=False):
        self.cashflow_calls += 1
        return super().get_external_cashflows(portfolio_id, user_id, start_date, end_date, include_trades)


def test_summary_resolves_inception_and_cashflows_once():
    # get_performance_summary used to resolve inception three times and fetch
    # the same cashflows three times, each one its own connection.
    start = date(2025, 1, 1)
    today = date.today()
    repo = _CallCountingRepo(
        created=start,
        values={start: 1000.0, today: 1200.0},
        cashflows=[CashFlowEntry(date=start.isoformat(), side='deposit', amount=1000.0)],
    )
    service = PerformanceService(repo)

    summary = service.get_performance_summary(1, 'u', 'all')

    assert summary.current_value == 1200.0
    assert repo.inception_calls == 1
    # One fetch; the deposit is found straight away, so no trade fallback.
    assert repo.cashflow_calls == 1
    assert repo.batch_calls == 1


def test_drawdown_resolves_inception_once_despite_nested_range_resolution():
    # get_drawdown resolves the range and _build_monthly_returns resolves it
    # again; both must share the one lookup.
    start, end = date(2025, 1, 1), date(2025, 3, 1)
    repo = _CallCountingRepo(created=start, values={d: 100.0 for d in _date_range(start, end)})
    service = PerformanceService(repo)

    service.get_drawdown(1, 'u', start_date=start, end_date=end)

    assert repo.inception_calls == 1
    assert repo.cashflow_calls <= 2
    assert repo.batch_calls == 1


def _date_range(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days
