"""Golden audit of TWR / MWR (XIRR) in PerformanceService on synthetic fixtures.

Every expected number is produced by the small reference implementation in
this module (``_ref_twr``: plain product of subperiod returns; ``_ref_xirr`` /
``_ref_xirr_roots``: pure bisection on an ACT/365 NPV), never by
PerformanceService or its ``_solve_irr``. The service MWR rate is also checked
by plugging it back into the independent ``_ref_npv`` (residual ~ 0).

Conventions (same as the service): values are end of day; a flow dated on the
window ``start`` is already inside values[start]; deposit = +, withdrawal = -
(portfolio perspective); with include_trades a buy is +cost, a sell -proceeds;
an implicit_contribution is generated when end-of-day cash is < 0.

Tolerances:
- returns (twr_pct, mwr_pct, mwr_annualized_pct): 0.01 percentage points
  (the service rounds to 4 decimals);
- money (flows, NPV residual): 0.01 EUR.

Known defects are documented as ``xfail(strict=True)`` with a reason starting
with an AUDIT-* id; a fix must remove the marker (strict makes an unexpected
pass fail the suite).
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models import CashFlowEntry
from app.repository import PortfolioScope
from app.repository._cash_model import fold_cash
from app.services.performance_service import IMPLICIT_CONTRIBUTION, PerformanceService

PCT_TOL = 0.01  # percentage points
EUR_TOL = 0.01  # EUR
UID = "u"


# --------------------------------------------------------------------------
# Independent reference implementation (no service code involved)
# --------------------------------------------------------------------------

def _ref_twr(start_value: float, events: list[tuple[date, float, float]], end_value: float) -> float:
    """TWR in % as the product of subperiod returns.

    ``events`` = [(date, external_flow, end_of_day_value_after_flow)], strictly
    after the window start and on/before its end, in date order. Each subperiod
    return is (V_after_flow - flow) / V_prev - 1, the last one end_value / V_prev - 1.
    """
    growth = 1.0
    prev = start_value
    for _day, flow, value_after in events:
        growth *= (value_after - flow) / prev
        prev = value_after
    growth *= end_value / prev
    return (growth - 1.0) * 100.0


def _ref_npv(rate: float, dated_flows: list[tuple[date, float]]) -> float:
    t0 = min(d for d, _ in dated_flows)
    return sum(cf / (1.0 + rate) ** ((d - t0).days / 365.0) for d, cf in dated_flows)


def _ref_bisect(dated_flows, lo: float, hi: float) -> float:
    f_lo = _ref_npv(lo, dated_flows)
    for _ in range(300):
        mid = (lo + hi) / 2.0
        f_mid = _ref_npv(mid, dated_flows)
        if f_mid == 0.0:
            return mid
        if (f_lo < 0) == (f_mid < 0):
            lo, f_lo = mid, f_mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _ref_xirr_roots(dated_flows, lo: float = -0.99, hi: float = 10.0, steps: int = 20000) -> list[float]:
    """Every annual rate in [lo, hi] where the NPV changes sign (investor perspective)."""
    roots: list[float] = []
    grid = [lo + (hi - lo) * i / steps for i in range(steps + 1)]
    prev_x, prev_f = grid[0], _ref_npv(grid[0], dated_flows)
    for x in grid[1:]:
        f = _ref_npv(x, dated_flows)
        if prev_f == 0.0:
            roots.append(prev_x)
        elif (prev_f < 0) != (f < 0) and f != 0.0:
            roots.append(_ref_bisect(dated_flows, prev_x, x))
        prev_x, prev_f = x, f
    if prev_f == 0.0:
        roots.append(prev_x)
    return roots


def _ref_xirr(dated_flows) -> float:
    roots = _ref_xirr_roots(dated_flows)
    assert len(roots) == 1, f"fixture must have a unique IRR, got {roots}"
    return roots[0]


def _cum_pct(rate: float, days: int) -> float:
    return ((1.0 + rate) ** (days / 365.0) - 1.0) * 100.0


def _service_rate(mwr) -> float:
    """Annual rate implied by the service result (annualized if present, else from mwr_pct)."""
    if mwr.mwr_annualized_pct is not None:
        return mwr.mwr_annualized_pct / 100.0
    return (1.0 + mwr.mwr_pct / 100.0) ** (365.0 / mwr.period_days) - 1.0


# --------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------

def _cf(day: date, side: str, amount: float) -> CashFlowEntry:
    return CashFlowEntry(date=day.isoformat(), side=side, amount=amount)


_EXTERNAL = {"deposit", "withdrawal", "dividend", "fee", "interest"}


def _window(flows, start, end, include_trades):
    sides = _EXTERNAL | ({"buy", "sell"} if include_trades else set())
    return [
        cf for cf in flows
        if cf.side in sides
        and (start is None or date.fromisoformat(cf.date) >= start)
        and (end is None or date.fromisoformat(cf.date) <= end)
    ]


def _step(series: dict[date, float], day: date) -> float:
    known = [d for d in series if d <= day]
    return float(series[max(known)]) if known else 0.0


class _FakeRepo:
    """One portfolio: step value series (EOD) and a transaction cashflow history."""

    def __init__(self, inception: date, values: dict[date, float], history: list[CashFlowEntry]):
        self.inception = inception
        self.values = values
        self.history = history

    def get_portfolio_inception_date(self, portfolio_id, user_id):
        return self.inception

    def get_external_cashflows(self, portfolio_id, user_id, start_date=None, end_date=None, include_trades=False):
        return _window(self.history, start_date, end_date, include_trades)

    def get_portfolio_values_in_range(self, portfolio_id, user_id, target_dates):
        return {d: _step(self.values, d) for d in target_dates}


class _FakeMultiRepo:
    """Several portfolios; multi reads combine them (sum of values, flows per portfolio)."""

    def __init__(self, inception: date, values: dict[int, dict[date, float]], history: dict[int, list]):
        self.inception = inception
        self.values = values
        self.history = history

    def resolve_portfolio_scope(self, portfolio_ids, user_id):
        return PortfolioScope(portfolio_ids=tuple(portfolio_ids), base_currency="EUR")

    def get_portfolio_inception_date(self, portfolio_id, user_id):
        return self.inception

    def get_portfolio_inception_date_multi(self, portfolio_ids, user_id):
        return self.inception

    def get_external_cashflows(self, portfolio_id, user_id, start_date=None, end_date=None, include_trades=False):
        return _window(self.history.get(portfolio_id, []), start_date, end_date, include_trades)

    def get_external_cashflows_by_portfolio(self, portfolio_ids, user_id, start_date=None, end_date=None,
                                            include_trades=False):
        return {pid: _window(self.history.get(pid, []), start_date, end_date, include_trades)
                for pid in portfolio_ids}

    def get_portfolio_values_in_range(self, portfolio_id, user_id, target_dates):
        return {d: _step(self.values[portfolio_id], d) for d in target_dates}

    def get_portfolio_values_in_range_multi(self, portfolio_ids, user_id, target_dates):
        return {d: round(sum(_step(self.values[p], d) for p in portfolio_ids), 2) for d in target_dates}


def _svc(repo) -> PerformanceService:
    return PerformanceService(repo, cache_ttl_seconds=0)


def _assert_npv_residual(mwr, dated_flows):
    assert abs(_ref_npv(_service_rate(mwr), dated_flows)) < EUR_TOL


# --------------------------------------------------------------------------
# A: no flows
# --------------------------------------------------------------------------

A_START, A_END = date(2025, 1, 1), date(2026, 1, 1)


def _fixture_a():
    return _FakeRepo(A_START, {A_START: 1000.0, A_END: 1100.0}, [_cf(A_START, "deposit", 1000.0)])


def test_a_no_flows_twr_and_mwr_equal_simple_return():
    svc = _svc(_fixture_a())
    twr = svc.calculate_twr(1, UID, A_START, A_END)
    mwr = svc.calculate_mwr(1, UID, A_START, A_END)

    exp_twr = _ref_twr(1000.0, [], 1100.0)
    flows = [(A_START, -1000.0), (A_END, 1100.0)]
    r = _ref_xirr(flows)

    assert (A_END - A_START).days == 365
    assert exp_twr == pytest.approx(10.0, abs=1e-9)
    assert twr.twr_pct == pytest.approx(exp_twr, abs=PCT_TOL)
    assert mwr.converged
    assert mwr.mwr_pct == pytest.approx(_cum_pct(r, 365), abs=PCT_TOL)
    assert mwr.mwr_annualized_pct == pytest.approx(r * 100.0, abs=PCT_TOL)
    assert mwr.mwr_annualized_pct == pytest.approx(10.0, abs=PCT_TOL)
    _assert_npv_residual(mwr, flows)


# --------------------------------------------------------------------------
# B: one mid-period deposit, TWR != MWR
# --------------------------------------------------------------------------

B_START, B_DEP, B_END = date(2025, 1, 1), date(2025, 7, 2), date(2026, 1, 1)


def _fixture_b():
    return _FakeRepo(
        B_START,
        {B_START: 1000.0, B_DEP: 1100.0, B_END: 1210.0},
        [_cf(B_START, "deposit", 1000.0), _cf(B_DEP, "deposit", 100.0)],
    )


def test_b_mid_period_deposit():
    svc = _svc(_fixture_b())
    twr = svc.calculate_twr(1, UID, B_START, B_END)
    mwr = svc.calculate_mwr(1, UID, B_START, B_END)

    exp_twr = _ref_twr(1000.0, [(B_DEP, 100.0, 1100.0)], 1210.0)
    flows = [(B_START, -1000.0), (B_DEP, -100.0), (B_END, 1210.0)]
    r = _ref_xirr(flows)

    assert (B_DEP - B_START).days == 182
    assert exp_twr == pytest.approx(10.0, abs=1e-9)
    assert twr.twr_pct == pytest.approx(exp_twr, abs=PCT_TOL)
    assert mwr.converged
    assert mwr.mwr_annualized_pct == pytest.approx(r * 100.0, abs=PCT_TOL)
    assert mwr.mwr_pct == pytest.approx(_cum_pct(r, 365), abs=PCT_TOL)
    _assert_npv_residual(mwr, flows)
    # Money in for the cheaper second half (flat then +10%): MWR differs from TWR.
    assert abs(mwr.mwr_pct - twr.twr_pct) > 10 * PCT_TOL


# --------------------------------------------------------------------------
# C: internal sell, no withdrawal
# --------------------------------------------------------------------------

C_START, C_SELL, C_END = date(2025, 1, 1), date(2025, 6, 1), date(2025, 12, 31)


def _fixture_c():
    return _FakeRepo(
        C_START,
        {C_START: 1000.0},  # flat: 1000 securities -> 700 securities + 300 cash
        [_cf(C_START, "deposit", 1000.0), _cf(C_START, "buy", 1000.0), _cf(C_SELL, "sell", -300.0)],
    )


def test_c_internal_sell_is_not_an_external_flow():
    svc = _svc(_fixture_c())
    flows, implicit_only = svc._get_cashflows_with_fallback(1, UID, C_START, C_END)
    in_window = [f for f in flows if C_START < date.fromisoformat(f.date) <= C_END]
    assert in_window == []
    assert all(f.side != "sell" for f in flows)
    assert not any(f.date == C_SELL.isoformat() for f in flows)
    assert implicit_only is False

    twr = svc.calculate_twr(1, UID, C_START, C_END)
    mwr = svc.calculate_mwr(1, UID, C_START, C_END)
    exp_twr = _ref_twr(1000.0, [], 1000.0)
    ref_flows = [(C_START, -1000.0), (C_END, 1000.0)]
    assert twr.twr_pct == pytest.approx(exp_twr, abs=PCT_TOL)
    assert twr.twr_pct == pytest.approx(0.0, abs=PCT_TOL)
    assert mwr.converged
    assert mwr.mwr_pct == pytest.approx(_cum_pct(_ref_xirr(ref_flows), 364), abs=PCT_TOL)
    assert mwr.mwr_pct == pytest.approx(0.0, abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)


# --------------------------------------------------------------------------
# D: buy with no deposit -> implicit contribution
# --------------------------------------------------------------------------

D_BEFORE, D_BUY, D_END = date(2025, 3, 1), date(2025, 3, 11), date(2025, 6, 30)


def test_d_buy_without_deposit_is_one_implicit_contribution():
    history = [_cf(D_BUY, "buy", 1000.0)]
    flows = PerformanceService._external_flows_from_history(history, D_BEFORE, D_END)
    assert len(flows) == 1
    assert flows[0].side == IMPLICIT_CONTRIBUTION
    assert flows[0].date == D_BUY.isoformat()
    assert flows[0].amount == pytest.approx(1000.0, abs=EUR_TOL)

    svc = _svc(_FakeRepo(D_BEFORE, {D_BUY: 1000.0}, history))
    via_service, implicit_only = svc._get_cashflows_with_fallback(1, UID, D_BEFORE, D_END)
    assert [(f.date, f.side, round(f.amount, 2)) for f in via_service] == [
        (D_BUY.isoformat(), IMPLICIT_CONTRIBUTION, 1000.0)
    ]
    assert implicit_only is True

    cash, implicit = fold_cash([(D_BUY, -1000.0)])
    assert cash == pytest.approx(0.0, abs=EUR_TOL)
    assert implicit == pytest.approx(1000.0, abs=EUR_TOL)


def test_d_flat_price_gives_no_fictitious_gain():
    # A prior position (also implicit) so the window really starts before D.
    history = [_cf(D_BEFORE, "buy", 500.0), _cf(D_BUY, "buy", 1000.0)]
    svc = _svc(_FakeRepo(D_BEFORE, {D_BEFORE: 500.0, D_BUY: 1500.0}, history))
    twr = svc.calculate_twr(1, UID, D_BEFORE, D_END)
    mwr = svc.calculate_mwr(1, UID, D_BEFORE, D_END)

    exp_twr = _ref_twr(500.0, [(D_BUY, 1000.0, 1500.0)], 1500.0)
    ref_flows = [(D_BEFORE, -500.0), (D_BUY, -1000.0), (D_END, 1500.0)]
    assert twr.start_date == D_BEFORE.isoformat()
    assert twr.twr_pct == pytest.approx(exp_twr, abs=PCT_TOL)
    assert twr.twr_pct == pytest.approx(0.0, abs=PCT_TOL)
    assert mwr.mwr_pct == pytest.approx(0.0, abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)

    # Window with zero start value: TWR moves to D and still reports 0.
    svc0 = _svc(_FakeRepo(D_BEFORE - timedelta(days=30), {D_BUY: 1000.0}, [_cf(D_BUY, "buy", 1000.0)]))
    twr0 = svc0.calculate_twr(1, UID, D_BEFORE, D_END)
    assert twr0.twr_pct == pytest.approx(0.0, abs=PCT_TOL)


# --------------------------------------------------------------------------
# E: aggregate of two portfolios
# --------------------------------------------------------------------------

E_START, E_D, E_END = date(2025, 1, 1), date(2025, 6, 1), date(2025, 12, 31)


def _net_by_day(flows) -> dict[str, float]:
    out: dict[str, float] = {}
    for f in flows:
        out[f.date] = out.get(f.date, 0.0) + float(f.amount)
    return out


def test_e_transfer_between_aggregated_portfolios_nets_to_zero():
    repo = _FakeMultiRepo(
        E_START,
        values={1: {E_START: 1000.0, E_D: 500.0}, 2: {E_D: 500.0}},
        history={
            1: [_cf(E_START, "deposit", 1000.0), _cf(E_D, "withdrawal", -500.0)],
            2: [_cf(E_D, "deposit", 500.0)],
        },
    )
    svc = _svc(repo)
    flows, _ = svc._get_cashflows_with_fallback([1, 2], UID, E_START, E_END)
    assert _net_by_day(flows)[E_D.isoformat()] == pytest.approx(0.0, abs=EUR_TOL)
    assert all(f.side != IMPLICIT_CONTRIBUTION for f in flows)

    twr = svc.calculate_twr([1, 2], UID, E_START, E_END)
    mwr = svc.calculate_mwr([1, 2], UID, E_START, E_END)
    exp_twr = _ref_twr(1000.0, [(E_D, 0.0, 1000.0)], 1000.0)
    ref_flows = [(E_START, -1000.0), (E_D, 0.0), (E_END, 1000.0)]
    assert twr.twr_pct == pytest.approx(exp_twr, abs=PCT_TOL)
    assert twr.twr_pct == pytest.approx(0.0, abs=PCT_TOL)
    assert mwr.converged
    assert mwr.mwr_pct == pytest.approx(_cum_pct(_ref_xirr(ref_flows), 364), abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)


def test_e_transfer_from_portfolio_without_cash_reads_as_net_inflow():
    # AUDIT-FINDING (E2): Parent has no recorded cash (only a buy, so its
    # securities were implicitly funded). Its -500 withdrawal leaves cash at
    # -500, which the cash model covers with an implicit +500 on the same day
    # (_external_flows_from_history -> settle_day). The withdrawal is thus
    # cancelled inside Parent, and the aggregate sees the Wealth deposit as a
    # net external inflow of +500 instead of an internal transfer (net 0).
    # The value fold applies the same rule (Parent stays at 1000, Wealth gets
    # 500, aggregate 1000 -> 1500), so TWR/MWR stay at 0 and are consistent;
    # only the "net invested" reading of the aggregate grows by 500.
    repo = _FakeMultiRepo(
        E_START,
        values={1: {E_START: 1000.0}, 2: {E_D: 500.0}},
        history={
            1: [_cf(E_START, "buy", 1000.0), _cf(E_D, "withdrawal", -500.0)],
            2: [_cf(E_D, "deposit", 500.0)],
        },
    )
    svc = _svc(repo)
    flows, _ = svc._get_cashflows_with_fallback([1, 2], UID, E_START, E_END)
    on_d = [(f.side, round(f.amount, 2)) for f in flows if f.date == E_D.isoformat()]
    assert sorted(on_d) == sorted([("withdrawal", -500.0), (IMPLICIT_CONTRIBUTION, 500.0), ("deposit", 500.0)])
    assert _net_by_day(flows)[E_D.isoformat()] == pytest.approx(500.0, abs=EUR_TOL)

    twr = svc.calculate_twr([1, 2], UID, E_START, E_END)
    mwr = svc.calculate_mwr([1, 2], UID, E_START, E_END)
    exp_twr = _ref_twr(1000.0, [(E_D, 500.0, 1500.0)], 1500.0)
    ref_flows = [(E_START, -1000.0), (E_D, -500.0), (E_END, 1500.0)]
    assert twr.twr_pct == pytest.approx(exp_twr, abs=PCT_TOL)
    assert mwr.mwr_pct == pytest.approx(_cum_pct(_ref_xirr(ref_flows), 364), abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)


def test_e_aggregate_twr_is_not_the_average_of_single_twrs():
    mid = date(2025, 6, 1)
    repo = _FakeMultiRepo(
        E_START,
        values={
            1: {E_START: 1000.0, mid: 1050.0, E_END: 1100.0},  # +10% no flows
            2: {mid: 1000.0, E_END: 900.0},  # funded on mid, -10%
        },
        history={1: [_cf(E_START, "deposit", 1000.0)], 2: [_cf(mid, "deposit", 1000.0)]},
    )
    svc = _svc(repo)
    t1 = svc.calculate_twr(1, UID, E_START, E_END).twr_pct
    t2 = svc.calculate_twr(2, UID, E_START, E_END).twr_pct
    agg = svc.calculate_twr([1, 2], UID, E_START, E_END).twr_pct

    assert t1 == pytest.approx(_ref_twr(1000.0, [], 1100.0), abs=PCT_TOL)
    assert t2 == pytest.approx(_ref_twr(1000.0, [], 900.0), abs=PCT_TOL)  # TWR starts on mid
    exp_agg = _ref_twr(1000.0, [(mid, 1000.0, 2050.0)], 2000.0)
    assert agg == pytest.approx(exp_agg, abs=PCT_TOL)
    assert abs(agg - (t1 + t2) / 2.0) > 1.0


# --------------------------------------------------------------------------
# F: window boundaries
# --------------------------------------------------------------------------

F_START, F_END = date(2025, 1, 1), date(2025, 12, 31)
F_AFTER = F_END + timedelta(days=1)


def _fixture_f():
    # 1000 deposited on start (inside values[start]); +10% on securities;
    # +100 deposited on end (inside values[end] = 1100 + 100); +50 on end+1.
    return _FakeRepo(
        F_START,
        {F_START: 1000.0, F_END: 1200.0, F_AFTER: 1250.0},
        [_cf(F_START, "deposit", 1000.0), _cf(F_END, "deposit", 100.0), _cf(F_AFTER, "deposit", 50.0)],
    )


def test_f_window_flows_start_inside_value_end_once_after_ignored():
    svc = _svc(_fixture_f())
    flows, _ = svc._get_cashflows_with_fallback(1, UID, F_START, F_END)
    dates = [f.date for f in flows]
    assert F_AFTER.isoformat() not in dates
    assert dates.count(F_END.isoformat()) == 1

    mwr = svc.calculate_mwr(1, UID, F_START, F_END)
    ref_flows = [(F_START, -1000.0), (F_END, -100.0), (F_END, 1200.0)]
    r = _ref_xirr(ref_flows)
    assert mwr.converged
    assert mwr.mwr_pct == pytest.approx(_cum_pct(r, 364), abs=PCT_TOL)
    assert mwr.mwr_pct == pytest.approx(10.0, abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)

    twr = svc.calculate_twr(1, UID, F_START, F_END)
    assert twr.start_date == mwr.start_date == F_START.isoformat()
    assert twr.end_date == mwr.end_date == F_END.isoformat()


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-F1: calculate_twr loops over event_days + [end]; with a flow on `end` the end day "
           "is processed twice and the second pass subtracts the flow again (r = -cf / V_end)",
)
def test_f_twr_counts_end_day_flow_exactly_once():
    svc = _svc(_fixture_f())
    twr = svc.calculate_twr(1, UID, F_START, F_END)
    exp = _ref_twr(1000.0, [(F_END, 100.0, 1200.0)], 1200.0)
    assert exp == pytest.approx(10.0, abs=1e-9)
    assert twr.twr_pct == pytest.approx(exp, abs=PCT_TOL)


F2_START, F2_DEP, F2_END = date(2025, 1, 1), date(2025, 3, 1), date(2025, 12, 31)


def _fixture_f2():
    # Inception on start with value 0 (e.g. an empty account opened), first
    # money deposited later.
    return _FakeRepo(F2_START, {F2_DEP: 1000.0, F2_END: 1100.0}, [_cf(F2_DEP, "deposit", 1000.0)])


def test_f_zero_start_value_actual_behavior():
    svc = _svc(_fixture_f2())
    twr = svc.calculate_twr(1, UID, F2_START, F2_END)
    mwr = svc.calculate_mwr(1, UID, F2_START, F2_END)

    # TWR moves its start to the first positive flow; MWR keeps the window start.
    assert twr.start_date == F2_DEP.isoformat()
    assert twr.period_days == (F2_END - F2_DEP).days
    assert mwr.start_date == F2_START.isoformat()
    assert mwr.period_days == (F2_END - F2_START).days

    assert twr.twr_pct == pytest.approx(_ref_twr(1000.0, [], 1100.0), abs=PCT_TOL)
    ref_flows = [(F2_DEP, -1000.0), (F2_END, 1100.0)]
    r = _ref_xirr(ref_flows)
    # mwr_pct compounds the rate over the full window (incl. the 59 idle days).
    assert mwr.mwr_pct == pytest.approx(_cum_pct(r, (F2_END - F2_START).days), abs=PCT_TOL)
    assert abs(_ref_npv(_service_rate(mwr), ref_flows)) < EUR_TOL


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-F2: with start value 0 calculate_twr shifts start to the first positive flow "
           "while calculate_mwr keeps the requested start, so start_date/period_days differ",
)
def test_f_twr_and_mwr_windows_are_aligned_when_start_value_is_zero():
    svc = _svc(_fixture_f2())
    twr = svc.calculate_twr(1, UID, F2_START, F2_END)
    mwr = svc.calculate_mwr(1, UID, F2_START, F2_END)
    assert twr.start_date == mwr.start_date
    assert twr.period_days == mwr.period_days


# --------------------------------------------------------------------------
# G: degenerate / ambiguous MWR
# --------------------------------------------------------------------------

G_START = date(2025, 1, 1)


def test_g_all_flows_same_sign_is_not_converged():
    end = date(2025, 12, 31)
    svc = _svc(_FakeRepo(G_START, {G_START: 1000.0, date(2025, 6, 1): 0.0}, [_cf(G_START, "deposit", 1000.0)]))
    mwr = svc.calculate_mwr(1, UID, G_START, end)
    assert mwr.mwr_pct is None
    assert mwr.converged is False


G_Y1 = G_START + timedelta(days=365)
G_Y2 = G_START + timedelta(days=730)


def _fixture_g_multi():
    # Investor flows -100 (t0), +230 (1y), -132 (2y): NPV roots at 10% and 20%.
    # Cash stays >= 0 so no implicit contribution: interest pays the extra 130,
    # and a fee empties the account after the final deposit (end value 0).
    return _FakeRepo(
        G_START,
        {G_START: 100.0, G_Y1: 0.0, G_Y2: 0.0},
        [
            _cf(G_START, "deposit", 100.0),
            _cf(G_Y1, "interest", 130.0),
            _cf(G_Y1, "withdrawal", -230.0),
            _cf(G_Y2, "deposit", 132.0),
            _cf(G_Y2, "fee", -132.0),
        ],
    )


G_FLOWS = [(G_START, -100.0), (G_Y1, 230.0), (G_Y2, -132.0)]


def test_g_multiple_roots_returns_one_of_the_independent_roots():
    roots = _ref_xirr_roots(G_FLOWS)
    assert len(roots) == 2
    assert roots[0] == pytest.approx(0.10, abs=1e-6)
    assert roots[1] == pytest.approx(0.20, abs=1e-6)

    mwr = _svc(_fixture_g_multi()).calculate_mwr(1, UID, G_START, G_Y2)
    assert mwr.mwr_annualized_pct is not None
    assert any(mwr.mwr_annualized_pct == pytest.approx(r * 100.0, abs=PCT_TOL) for r in roots)
    _assert_npv_residual(mwr, G_FLOWS)


@pytest.mark.xfail(
    strict=True,
    reason="AUDIT-G1: _solve_irr only logs a warning on multiple NPV sign changes; calculate_mwr "
           "returns one root with converged=True and no ambiguity flag",
)
def test_g_multiple_roots_is_flagged_ambiguous():
    mwr = _svc(_fixture_g_multi()).calculate_mwr(1, UID, G_START, G_Y2)
    assert getattr(mwr, "multiple_roots", False) is True or mwr.converged is False


# --------------------------------------------------------------------------
# Extra solver checks
# --------------------------------------------------------------------------

X_START = date(2025, 1, 1)


def test_x_partial_withdrawal():
    w, end = date(2025, 4, 11), date(2026, 1, 1)
    svc = _svc(_FakeRepo(
        X_START,
        {X_START: 1000.0, w: 700.0, end: 770.0},
        [_cf(X_START, "deposit", 1000.0), _cf(w, "withdrawal", -400.0)],
    ))
    flows, _ = svc._get_cashflows_with_fallback(1, UID, X_START, end)
    assert all(f.side != IMPLICIT_CONTRIBUTION for f in flows)
    mwr = svc.calculate_mwr(1, UID, X_START, end)
    twr = svc.calculate_twr(1, UID, X_START, end)
    ref_flows = [(X_START, -1000.0), (w, 400.0), (end, 770.0)]
    r = _ref_xirr(ref_flows)
    assert mwr.mwr_annualized_pct == pytest.approx(r * 100.0, abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)
    assert twr.twr_pct == pytest.approx(_ref_twr(1000.0, [(w, -400.0, 700.0)], 770.0), abs=PCT_TOL)


def test_x_total_withdrawal():
    mid, end = date(2025, 6, 1), date(2026, 1, 1)
    svc = _svc(_FakeRepo(
        X_START,
        {X_START: 1000.0, mid: 1100.0, end: 0.0},
        [_cf(X_START, "deposit", 1000.0), _cf(mid, "interest", 100.0), _cf(end, "withdrawal", -1100.0)],
    ))
    flows, _ = svc._get_cashflows_with_fallback(1, UID, X_START, end)
    assert all(f.side != IMPLICIT_CONTRIBUTION for f in flows)
    mwr = svc.calculate_mwr(1, UID, X_START, end)
    ref_flows = [(X_START, -1000.0), (end, 1100.0), (end, 0.0)]
    r = _ref_xirr(ref_flows)
    assert mwr.converged
    assert mwr.mwr_pct == pytest.approx(_cum_pct(r, 365), abs=PCT_TOL)
    assert mwr.mwr_pct == pytest.approx(10.0, abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)


def test_x_first_investment_from_zero_funded_by_deposit():
    dep, end = date(2025, 1, 11), date(2026, 1, 11)
    svc = _svc(_FakeRepo(X_START, {dep: 1000.0, end: 1100.0}, [_cf(dep, "deposit", 1000.0)]))
    mwr = svc.calculate_mwr(1, UID, X_START, end)
    ref_flows = [(dep, -1000.0), (end, 1100.0)]
    r = _ref_xirr(ref_flows)
    assert r == pytest.approx(0.10, abs=1e-9)
    assert mwr.period_days == (end - X_START).days == 375
    assert mwr.mwr_annualized_pct == pytest.approx(r * 100.0, abs=PCT_TOL)
    assert mwr.mwr_pct == pytest.approx(_cum_pct(r, 375), abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)


def test_x_mwr_pct_matches_annualized_rate_over_long_window():
    dep, end = date(2025, 5, 1), date(2026, 5, 16)  # 500 days
    svc = _svc(_FakeRepo(
        X_START,
        {X_START: 1000.0, dep: 1300.0, end: 1450.0},
        [_cf(X_START, "deposit", 1000.0), _cf(dep, "deposit", 200.0)],
    ))
    mwr = svc.calculate_mwr(1, UID, X_START, end)
    days = (end - X_START).days
    assert days == 500
    r_ann = mwr.mwr_annualized_pct / 100.0
    assert mwr.mwr_pct == pytest.approx(100.0 * ((1.0 + r_ann) ** (days / 365.0) - 1.0), abs=PCT_TOL)
    ref_flows = [(X_START, -1000.0), (dep, -200.0), (end, 1450.0)]
    assert mwr.mwr_annualized_pct == pytest.approx(_ref_xirr(ref_flows) * 100.0, abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)


def test_x_short_window_has_no_annualized_mwr():
    end = X_START + timedelta(days=30)
    svc = _svc(_FakeRepo(X_START, {X_START: 1000.0, end: 1020.0}, [_cf(X_START, "deposit", 1000.0)]))
    mwr = svc.calculate_mwr(1, UID, X_START, end)
    ref_flows = [(X_START, -1000.0), (end, 1020.0)]
    assert mwr.period_days == 30
    assert mwr.mwr_annualized_pct is None
    assert mwr.mwr_pct == pytest.approx(_cum_pct(_ref_xirr(ref_flows), 30), abs=PCT_TOL)
    assert mwr.mwr_pct == pytest.approx(2.0, abs=PCT_TOL)
    _assert_npv_residual(mwr, ref_flows)
