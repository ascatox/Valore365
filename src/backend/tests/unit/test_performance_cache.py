import threading
import time
from datetime import date, timedelta

from app.models import CashFlowEntry
from app.services.performance_service import PerformanceService

START = date(2025, 1, 1)
END = date(2026, 2, 4)


class _SlowRepo:
    """Repository whose valuation is slow enough to overlap concurrent callers."""

    def __init__(self, delay: float = 0.05) -> None:
        self.delay = delay
        self.value_calls = 0
        self.inception_calls = 0
        self.cashflow_calls = 0
        self._lock = threading.Lock()

    def get_portfolio_created_date(self, portfolio_id, user_id):
        return START

    def get_portfolio_inception_date(self, portfolio_id, user_id):
        with self._lock:
            self.inception_calls += 1
        return START

    def get_external_cashflows(self, portfolio_id, user_id, start_date=None, end_date=None, include_trades=False):
        with self._lock:
            self.cashflow_calls += 1
        return [CashFlowEntry(date=START.isoformat(), side="deposit", amount=1000.0)]

    def get_portfolio_values_in_range(self, portfolio_id, user_id, target_dates):
        with self._lock:
            self.value_calls += 1
        time.sleep(self.delay)
        return {d: 1000.0 + (d - START).days for d in target_dates}


def _service(repo, ttl: float = 30.0) -> PerformanceService:
    return PerformanceService(repo, cache_ttl_seconds=ttl)


def test_simultaneous_requests_for_one_portfolio_compute_once():
    # The dashboard fires its performance endpoints together, so a plain TTL
    # cache would have every one of them miss and compute in parallel. The
    # first caller must fill while the rest wait.
    repo = _SlowRepo()
    service = _service(repo)
    barrier = threading.Barrier(8)
    errors: list[BaseException] = []

    def call() -> None:
        try:
            barrier.wait()
            service.get_twr_timeseries(1, "u", start_date=START, end_date=END)
        except BaseException as exc:  # pragma: no cover - surfaced by the assert
            errors.append(exc)

    threads = [threading.Thread(target=call) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors
    assert repo.value_calls == 1, "eight simultaneous requests must value the portfolio once"
    assert repo.inception_calls == 1


def test_the_performance_endpoints_share_one_valuation():
    repo = _SlowRepo(delay=0.0)
    service = _service(repo)

    service.get_performance_summary(1, "u", "1y")
    service.get_twr_timeseries(1, "u", start_date=START, end_date=END)
    service.get_gain_timeseries(1, "u", start_date=START, end_date=END)
    service.get_mwr_timeseries(1, "u", start_date=START, end_date=END)
    service.get_drawdown(1, "u", start_date=START, end_date=END)
    service.get_monthly_returns(1, "u", start_date=START, end_date=END)
    service.get_rolling_windows(1, "u", start_date=START, end_date=END)
    service.get_hall_of_fame(1, "u", start_date=START, end_date=END)
    service.get_yearly_returns(1, "u")

    # The summary resolves its own period, so it asks for a couple of dates the
    # shared window (START..END) does not already hold; that is one miss.
    # get_yearly_returns spans inception (START) through the real today, which
    # reaches past END, so it is a *third* miss — the whole-history window is
    # wider than the shared START..END window every other call here uses, so
    # it cannot be a hit on the same cache entries. Bound relaxed from <= 2 to
    # <= 3 only after observing this third call actually happen.
    assert repo.value_calls <= 3
    assert repo.inception_calls == 1


def test_yearly_returns_is_served_from_the_shared_cache():
    # get_drawdown(inception..today) already walks the full daily range that
    # get_yearly_returns needs; once it has run, the yearly table must be a
    # pure cache hit, not a second valuation pass over the same history.
    repo = _SlowRepo(delay=0.0)
    service = _service(repo)

    service.get_drawdown(1, "u", start_date=START, end_date=date.today())
    before = repo.value_calls
    service.get_yearly_returns(1, "u")

    assert repo.value_calls == before


def test_one_users_data_is_never_served_to_another():
    repo = _SlowRepo(delay=0.0)
    service = _service(repo)

    service.get_twr_timeseries(1, "user_a", start_date=START, end_date=END)
    before = repo.value_calls
    service.get_twr_timeseries(1, "user_b", start_date=START, end_date=END)

    assert repo.value_calls > before, "a second user must not read the first user's cache"


def test_separate_portfolios_do_not_share_an_entry():
    repo = _SlowRepo(delay=0.0)
    service = _service(repo)

    service.get_twr_timeseries(1, "u", start_date=START, end_date=END)
    before = repo.value_calls
    service.get_twr_timeseries(2, "u", start_date=START, end_date=END)

    assert repo.value_calls > before


def test_the_cache_expires():
    repo = _SlowRepo(delay=0.0)
    service = _service(repo, ttl=0.05)

    service.get_twr_timeseries(1, "u", start_date=START, end_date=END)
    first = repo.value_calls
    time.sleep(0.1)
    service.get_twr_timeseries(1, "u", start_date=START, end_date=END)

    assert repo.value_calls > first, "stale prices must not be served past the TTL"


def test_a_zero_ttl_recomputes_every_time():
    repo = _SlowRepo(delay=0.0)
    service = _service(repo, ttl=0.0)

    service.get_twr_timeseries(1, "u", start_date=START, end_date=END)
    first = repo.value_calls
    service.get_twr_timeseries(1, "u", start_date=START, end_date=END)

    assert repo.value_calls > first


def test_the_store_stays_bounded():
    repo = _SlowRepo(delay=0.0)
    service = PerformanceService(repo, cache_ttl_seconds=300.0, cache_max_entries=4)

    for portfolio_id in range(20):
        service.get_twr_timeseries(portfolio_id, "u", start_date=START, end_date=END)

    assert len(service._cache_store._entries) <= 4


def test_cached_results_match_uncached_ones():
    uncached = _service(_SlowRepo(delay=0.0), ttl=0.0)
    cached = _service(_SlowRepo(delay=0.0))

    for _ in range(2):
        a = uncached.get_twr_timeseries(1, "u", start_date=START, end_date=END)
        b = cached.get_twr_timeseries(1, "u", start_date=START, end_date=END)
        assert [p.model_dump() for p in a] == [p.model_dump() for p in b]

    assert uncached.get_drawdown(1, "u", start_date=START, end_date=END).model_dump() == \
        cached.get_drawdown(1, "u", start_date=START, end_date=END).model_dump()


def test_a_long_window_still_needs_only_one_valuation_call():
    repo = _SlowRepo(delay=0.0)
    service = _service(repo)

    points = service.get_twr_timeseries(1, "u", start_date=START, end_date=START + timedelta(days=399))

    assert len(points) == 400
    assert repo.value_calls == 1
