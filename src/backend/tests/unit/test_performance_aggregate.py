"""Vista aggregata: PerformanceService over several portfolios read as one."""

from datetime import date

import pytest

from app.models import CashFlowEntry
from app.repository import PortfolioScope
from app.services.performance_service import PerformanceService

START = date(2026, 1, 1)
MID = date(2026, 4, 1)
END = date(2026, 7, 1)


def _cf(day: date, side: str, amount: float) -> CashFlowEntry:
    return CashFlowEntry(date=day.isoformat(), side=side, amount=amount)


class _FakeRepo:
    """Per-portfolio value series and cashflows; multi reads combine them."""

    def __init__(self, values: dict[int, dict[date, float]], cashflows: dict[int, list[CashFlowEntry]],
                 currencies: dict[int, str] | None = None) -> None:
        self.values = values
        self.cashflows = cashflows
        self.currencies = currencies or {pid: "EUR" for pid in values}
        self.calls: list[str] = []

    # -- scope
    def resolve_portfolio_scope(self, portfolio_ids, user_id):
        self.calls.append("scope")
        ids = list(dict.fromkeys(i for i in portfolio_ids if i > 0))
        if any(i not in self.values for i in ids):
            raise ValueError("Portfolio non trovato")
        if len({self.currencies[i] for i in ids}) != 1:
            raise ValueError("I portafogli aggregati devono avere la stessa valuta base")
        return PortfolioScope(portfolio_ids=tuple(ids), base_currency=self.currencies[ids[0]])

    # -- single
    def get_portfolio_inception_date(self, portfolio_id, user_id):
        self.calls.append("inception")
        return START

    def get_external_cashflows(self, portfolio_id, user_id, start_date=None, end_date=None, include_trades=False):
        self.calls.append("cashflows")
        return self._window(self.cashflows.get(portfolio_id, []), start_date, end_date, include_trades)

    def get_portfolio_values_in_range(self, portfolio_id, user_id, target_dates):
        self.calls.append("values")
        return {d: self._value(portfolio_id, d) for d in target_dates}

    # -- multi
    def get_portfolio_inception_date_multi(self, portfolio_ids, user_id):
        self.calls.append("inception_multi")
        return START

    def get_external_cashflows_by_portfolio(self, portfolio_ids, user_id, start_date=None, end_date=None,
                                            include_trades=False):
        self.calls.append("cashflows_multi")
        return {
            pid: self._window(self.cashflows.get(pid, []), start_date, end_date, include_trades)
            for pid in portfolio_ids
        }

    def get_portfolio_values_in_range_multi(self, portfolio_ids, user_id, target_dates):
        self.calls.append("values_multi")
        return {d: round(sum(self._value(pid, d) for pid in portfolio_ids), 2) for d in target_dates}

    # -- helpers
    def _value(self, pid: int, day: date) -> float:
        # Step series: the last known value on or before `day`.
        series = self.values[pid]
        known = [d for d in series if d <= day]
        return float(series[max(known)]) if known else 0.0

    @staticmethod
    def _window(flows, start, end, include_trades):
        sides = {"deposit", "withdrawal", "dividend", "fee", "interest"}
        if include_trades:
            sides |= {"buy", "sell"}
        return [
            cf for cf in flows
            if cf.side in sides
            and (start is None or date.fromisoformat(cf.date) >= start)
            and (end is None or date.fromisoformat(cf.date) <= end)
        ]


def test_aggregate_twr_uses_combined_values_and_flows():
    # Each portfolio grows 10% with no flows: the aggregate grows 10% too.
    repo = _FakeRepo(
        values={1: {START: 1000.0, END: 1100.0}, 2: {START: 3000.0, END: 3300.0}},
        cashflows={},
    )
    twr = PerformanceService(repo).calculate_twr([1, 2], "u", START, END)

    assert twr.twr_pct == pytest.approx(10.0, abs=1e-6)


def test_a_transfer_between_selected_portfolios_nets_out():
    # 500 moves from portfolio 1 to portfolio 2 on MID. Combined values are
    # 2000 -> 2100 -> 2200 with no money entering or leaving the aggregate,
    # so the combined TWR is 1.05 x (2200 / 2100) - 1 = 10%.
    repo = _FakeRepo(
        values={
            1: {START: 1000.0, MID: 550.0, END: 600.0},
            2: {START: 1000.0, MID: 1550.0, END: 1600.0},
        },
        cashflows={
            1: [_cf(MID, "withdrawal", -500.0)],
            2: [_cf(MID, "deposit", 500.0)],
        },
    )
    service = PerformanceService(repo)

    twr = service.calculate_twr([1, 2], "u", START, END)
    assert twr.twr_pct == pytest.approx(10.0, abs=1e-6)

    # The same aggregate with no transfer recorded at all gives the same TWR.
    no_transfer = _FakeRepo(
        values={1: {START: 2000.0, MID: 2100.0, END: 2200.0}, 2: {START: 0.0}},
        cashflows={},
    )
    assert PerformanceService(no_transfer).calculate_twr([1, 2], "u", START, END).twr_pct == pytest.approx(
        twr.twr_pct, abs=1e-6
    )

    mwr = service.calculate_mwr([1, 2], "u", START, END)
    assert mwr.converged
    assert mwr.mwr_pct == pytest.approx(10.0, abs=0.01)

    drawdown = service.get_drawdown([1, 2], "u", START, END)
    assert drawdown.portfolio_id == 1
    assert drawdown.max_drawdown_pct == pytest.approx(0.0, abs=1e-6)


def test_aggregate_fallback_to_trades_is_decided_per_portfolio():
    # Portfolio 1 is funded by a deposit; portfolio 2 has only trades. Its
    # purchase must still count as an external flow, not as performance.
    repo = _FakeRepo(
        values={
            1: {START: 1000.0, END: 1000.0},
            2: {START: 0.0, MID: 500.0, END: 500.0},
        },
        cashflows={
            1: [_cf(START, "deposit", 1000.0)],
            2: [_cf(MID, "buy", 500.0)],
        },
    )
    service = PerformanceService(repo)

    flows, used_fallback = service._get_cashflows_with_fallback([1, 2], "u", START, END)
    assert [(f.side, f.amount) for f in flows] == [("deposit", 1000.0), ("buy", 500.0)]
    assert used_fallback

    twr = service.calculate_twr([1, 2], "u", START, END)
    assert twr.twr_pct == pytest.approx(0.0, abs=1e-6)


def test_aggregate_cache_is_keyed_by_the_sorted_ids():
    repo = _FakeRepo(
        values={1: {START: 1000.0, END: 1100.0}, 2: {START: 1000.0, END: 1100.0}},
        cashflows={},
    )
    service = PerformanceService(repo, cache_ttl_seconds=300.0)

    service.calculate_twr([1, 2], "u", START, END)
    service.calculate_twr([2, 1, 2], "u", START, END)

    assert repo.calls.count("values_multi") == 1
    assert set(service._cache_store._entries) == {("u", (1, 2))}


def test_a_one_id_list_runs_the_single_portfolio_path():
    repo = _FakeRepo(values={1: {START: 1000.0, END: 1200.0}}, cashflows={})
    service = PerformanceService(repo, cache_ttl_seconds=300.0)

    single = service.calculate_twr(1, "u", START, END)
    as_list = service.calculate_twr([1], "u", START, END)

    assert as_list == single
    assert not any(call.endswith("_multi") or call == "scope" for call in repo.calls)
    assert set(service._cache_store._entries) == {("u", (1,))}


def test_aggregate_rejects_mixed_currencies_and_empty_selection():
    repo = _FakeRepo(
        values={1: {START: 1.0}, 2: {START: 1.0}},
        cashflows={},
        currencies={1: "EUR", 2: "USD"},
    )
    service = PerformanceService(repo)

    with pytest.raises(ValueError, match="valuta base"):
        service.get_performance_summary([1, 2], "u", "1y")
    with pytest.raises(ValueError, match="Seleziona almeno"):
        service.calculate_twr([0], "u", START, END)
    with pytest.raises(ValueError, match="Portfolio non trovato"):
        service.calculate_twr([1, 9], "u", START, END)


def test_aggregate_summary_and_series_endpoints_run():
    repo = _FakeRepo(
        values={1: {START: 1000.0, END: 1100.0}, 2: {START: 1000.0, END: 1100.0}},
        cashflows={1: [_cf(START, "deposit", 1000.0)], 2: [_cf(START, "deposit", 1000.0)]},
    )
    service = PerformanceService(repo)

    summary = service.get_performance_summary([1, 2], "u", "1y")
    assert summary.twr is not None
    monthly = service.get_monthly_returns([2, 1], "u", START, END)
    assert monthly.portfolio_id == 2
    assert service.get_twr_timeseries([1, 2], "u", START, END)
    assert service.get_yearly_returns([1, 2], "u").portfolio_id == 1
