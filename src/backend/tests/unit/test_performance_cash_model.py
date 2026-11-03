"""TASK-46: one cash model for the valuation and the external flows of TWR/MWR.

Buys are paid from cash, sell proceeds stay in cash, fees/taxes reduce it,
dividends/interest add to it. A day that would leave cash negative is funded
by an implicit external contribution (cash floors at 0).

Valuation is the real repository fold (scripted SQL rows). Cash flows are
derived here from the same transactions with the documented sign convention
(portfolio perspective, fees/taxes on trades), independently of the code under
test. Every expected number is computed by hand in the test.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.models import CashFlowEntry
from app.repository import PortfolioScope
from app.services.performance_service import PerformanceService
from tests.unit.test_transactions_repository import _scripted_repo

D0 = date(2026, 1, 5)


def _d(offset: int) -> date:
    return D0 + timedelta(days=offset)


def _tx(day, side, asset_id=None, *, qty, price, fees=0.0, taxes=0.0):
    return {
        "asset_id": asset_id,
        "side": side,
        "trade_date": day,
        "quantity": qty,
        "price": price,
        "fees": fees,
        "taxes": taxes,
        "trade_currency": "EUR",
    }


def _signed(t) -> float:
    gross = t["quantity"] * t["price"]
    costs = t["fees"] + t["taxes"]
    if t["side"] == "buy":
        return gross + costs
    if t["side"] == "sell":
        return -(gross - costs)
    if t["side"] in {"deposit", "dividend", "interest"}:
        return gross
    return -gross  # withdrawal, fee


def _flows(transactions, start, end, include_trades):
    sides = {"deposit", "withdrawal", "dividend", "fee", "interest"}
    if include_trades:
        sides |= {"buy", "sell"}
    return [
        CashFlowEntry(date=t["trade_date"].isoformat(), side=t["side"], amount=_signed(t))
        for t in transactions
        if t["side"] in sides
        and (start is None or t["trade_date"] >= start)
        and (end is None or t["trade_date"] <= end)
    ]


def _valuation(transactions, bars):
    return _scripted_repo(
        transactions=transactions,
        price_bars=bars,
        assets=[{"id": 1, "symbol": "AAA", "quote_currency": "EUR"}],
        fx_rates=[],
        cash_balance=0.0,
    )


class _Repo:
    """One or more portfolios: real valuation fold + independently derived flows."""

    def __init__(self, portfolios: dict[int, tuple[list, list]]):
        self.txs = {pid: txs for pid, (txs, _) in portfolios.items()}
        self.val = {pid: _valuation(txs, bars) for pid, (txs, bars) in portfolios.items()}

    def resolve_portfolio_scope(self, portfolio_ids, user_id):
        return PortfolioScope(portfolio_ids=tuple(portfolio_ids), base_currency="EUR")

    def get_portfolio_inception_date(self, portfolio_id, user_id):
        return min(t["trade_date"] for t in self.txs[portfolio_id])

    def get_portfolio_inception_date_multi(self, portfolio_ids, user_id):
        return min(self.get_portfolio_inception_date(pid, user_id) for pid in portfolio_ids)

    def get_external_cashflows(self, portfolio_id, user_id, start_date=None, end_date=None, include_trades=False):
        return _flows(self.txs[portfolio_id], start_date, end_date, include_trades)

    def get_external_cashflows_by_portfolio(self, portfolio_ids, user_id, start_date=None, end_date=None,
                                            include_trades=False):
        return {pid: _flows(self.txs[pid], start_date, end_date, include_trades) for pid in portfolio_ids}

    def get_portfolio_values_in_range(self, portfolio_id, user_id, target_dates):
        return self.val[portfolio_id].get_portfolio_values_in_range(portfolio_id, user_id, target_dates)

    def get_portfolio_values_in_range_multi(self, portfolio_ids, user_id, target_dates):
        dates = list(target_dates)
        series = [self.val[pid].get_portfolio_values_in_range(pid, user_id, dates) for pid in portfolio_ids]
        return {d: round(sum(s[d] for s in series), 2) for d in dates}


def _service(txs, bars):
    return PerformanceService(_Repo({1: (txs, bars)}), cache_ttl_seconds=0)


FLAT = [{"asset_id": 1, "price_date": _d(0), "close": 100.0}]


def _irr(flows: list[tuple[int, float]]) -> float:
    def npv(r: float) -> float:
        return sum(cf / (1 + r) ** (days / 365.0) for days, cf in flows)

    lo, hi = -0.99, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if npv(lo) * npv(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def test_deposit_then_buy_at_flat_price_is_zero_and_has_no_implicit_flow():
    # Before TASK-46: TWR +100% (the 1000 bought entered value from nowhere).
    txs = [_tx(_d(0), "deposit", qty=1000, price=1), _tx(_d(5), "buy", 1, qty=10, price=100)]
    service = _service(txs, FLAT)

    flows, implicit_only = service._get_cashflows_with_fallback(1, "u", _d(0), _d(10))
    assert [(f.side, f.amount) for f in flows] == [("deposit", 1000.0)]
    assert not implicit_only
    assert service.calculate_twr(1, "u", None, _d(10)).twr_pct == pytest.approx(0.0, abs=1e-6)
    assert service.calculate_mwr(1, "u", None, _d(10)).mwr_pct == pytest.approx(0.0, abs=1e-3)


def test_buy_beyond_cash_is_an_implicit_contribution():
    # 500 on record, a 1000 buy: 500 paid from cash, 500 contributed implicitly.
    # Before TASK-46 the same data gave TWR +200%.
    txs = [_tx(_d(0), "deposit", qty=500, price=1), _tx(_d(5), "buy", 1, qty=10, price=100)]
    service = _service(txs, FLAT)

    flows, _ = service._get_cashflows_with_fallback(1, "u", _d(0), _d(10))
    assert [(f.date, f.side, f.amount) for f in flows] == [
        (_d(0).isoformat(), "deposit", 500.0),
        (_d(5).isoformat(), "implicit_contribution", 500.0),
    ]
    # Cash floors at 0: the value is the 10 units only.
    assert service.repo.get_portfolio_values_in_range(1, "u", [_d(5)])[_d(5)] == 1000.0
    assert service.calculate_twr(1, "u", None, _d(10)).twr_pct == pytest.approx(0.0, abs=1e-6)
    assert service.calculate_mwr(1, "u", None, _d(10)).mwr_pct == pytest.approx(0.0, abs=1e-3)


def test_sell_then_withdrawal_at_flat_price_is_zero():
    # Sell proceeds stay in cash (no flow); only the withdrawal leaves.
    txs = [
        _tx(_d(0), "deposit", qty=1000, price=1),
        _tx(_d(1), "buy", 1, qty=10, price=100),
        _tx(_d(5), "sell", 1, qty=5, price=100),
        _tx(_d(8), "withdrawal", qty=500, price=1),
    ]
    service = _service(txs, FLAT)

    flows, _ = service._get_cashflows_with_fallback(1, "u", _d(0), _d(10))
    assert [(f.side, f.amount) for f in flows] == [("deposit", 1000.0), ("withdrawal", -500.0)]
    values = service.repo.get_portfolio_values_in_range(1, "u", [_d(5), _d(10)])
    assert values == {_d(5): 1000.0, _d(10): 500.0}
    assert service.calculate_twr(1, "u", None, _d(10)).twr_pct == pytest.approx(0.0, abs=1e-6)
    assert service.calculate_mwr(1, "u", None, _d(10)).mwr_pct == pytest.approx(0.0, abs=1e-3)


def test_withdrawal_beyond_cash_nets_to_the_cash_available():
    # 100 deposited and fully invested, then a 50 withdrawal with no cash: the
    # uncovered 50 is an implicit contribution, the day's net flow is 0 and the
    # value (the 1 unit) does not move, so no return is created.
    txs = [
        _tx(_d(0), "deposit", qty=100, price=1),
        _tx(_d(0), "buy", 1, qty=1, price=100),
        _tx(_d(5), "withdrawal", qty=50, price=1),
    ]
    service = _service(txs, FLAT)

    flows, _ = service._get_cashflows_with_fallback(1, "u", _d(0), _d(10))
    assert sum(f.amount for f in flows if f.date == _d(5).isoformat()) == pytest.approx(0.0)
    assert service.repo.get_portfolio_values_in_range(1, "u", [_d(5)])[_d(5)] == 100.0
    assert service.calculate_twr(1, "u", None, _d(10)).twr_pct == pytest.approx(0.0, abs=1e-6)


def test_price_move_with_mid_period_deposit_matches_chain_linked_twr():
    # d0: deposit 1000, buy 10 @ 100 (cash 0). d100: price 110, deposit 600,
    # buy 5 @ 110 (cash 50). d200: price 121.
    txs = [
        _tx(_d(0), "deposit", qty=1000, price=1),
        _tx(_d(0), "buy", 1, qty=10, price=100),
        _tx(_d(100), "deposit", qty=600, price=1),
        _tx(_d(100), "buy", 1, qty=5, price=110),
    ]
    bars = [
        {"asset_id": 1, "price_date": _d(0), "close": 100.0},
        {"asset_id": 1, "price_date": _d(100), "close": 110.0},
        {"asset_id": 1, "price_date": _d(200), "close": 121.0},
    ]
    service = _service(txs, bars)

    v0, v100, v200 = 1000.0, 15 * 110 + 50, 15 * 121 + 50
    r1 = (v100 - v0 - 600) / v0
    r2 = v200 / v100 - 1
    expected = ((1 + r1) * (1 + r2) - 1) * 100
    assert expected == pytest.approx(20.67647, abs=1e-4)
    assert service.calculate_twr(1, "u", None, _d(200)).twr_pct == pytest.approx(expected, abs=1e-3)

    mwr = service.calculate_mwr(1, "u", None, _d(200))
    rate = _irr([(0, -v0), (100, -600.0), (200, v200)])
    assert mwr.mwr_pct == pytest.approx(((1 + rate) ** (200 / 365) - 1) * 100, abs=1e-3)


def test_dividend_increases_return():
    txs = [
        _tx(_d(0), "deposit", qty=1000, price=1),
        _tx(_d(0), "buy", 1, qty=10, price=100),
        _tx(_d(10), "dividend", qty=1, price=20),
    ]
    service = _service(txs, FLAT)

    assert service.calculate_twr(1, "u", None, _d(20)).twr_pct == pytest.approx(2.0, abs=1e-6)


def test_fees_and_taxes_reduce_return():
    # 2000 cash; buy 10 @ 100 + 10 fees (d5); sell 5 @ 100 - 3 fees - 2 taxes
    # (d8); a 15 fee movement (d9). Flat price: the return is the costs only.
    txs = [
        _tx(_d(0), "deposit", qty=2000, price=1),
        _tx(_d(5), "buy", 1, qty=10, price=100, fees=10),
        _tx(_d(8), "sell", 1, qty=5, price=100, fees=3, taxes=2),
        _tx(_d(9), "fee", qty=1, price=15),
    ]
    service = _service(txs, FLAT)

    values = service.repo.get_portfolio_values_in_range(1, "u", [_d(5), _d(8), _d(10)])
    assert values == {_d(5): 1990.0, _d(8): 1985.0, _d(10): 1970.0}
    assert service.calculate_twr(1, "u", None, _d(10)).twr_pct == pytest.approx((1970 / 2000 - 1) * 100, abs=1e-6)


def test_aggregate_scope_uses_the_same_model_per_portfolio():
    # P1: 500 deposited, 1000 bought (500 implicit), flat. P2: 1000 deposited,
    # 5 @ 100 bought on d1, price 110 from d10. Cash is kept per portfolio:
    # P2's spare 500 does not pay for P1's buy.
    p1 = ([_tx(_d(0), "deposit", qty=500, price=1), _tx(_d(5), "buy", 1, qty=10, price=100)], FLAT)
    p2 = (
        [_tx(_d(0), "deposit", qty=1000, price=1), _tx(_d(1), "buy", 1, qty=5, price=100)],
        [{"asset_id": 1, "price_date": _d(0), "close": 100.0}, {"asset_id": 1, "price_date": _d(10), "close": 110.0}],
    )
    service = PerformanceService(_Repo({1: p1, 2: p2}), cache_ttl_seconds=0)

    flows, _ = service._get_cashflows_with_fallback([1, 2], "u", _d(0), _d(20))
    assert sorted((f.side, f.amount) for f in flows) == [
        ("deposit", 500.0), ("deposit", 1000.0), ("implicit_contribution", 500.0),
    ]
    # Start 1500; d5: 2000 with a 500 flow (0%); d20: 1000 + 500 + 550 = 2050.
    twr = service.calculate_twr([1, 2], "u", None, _d(20))
    assert twr.twr_pct == pytest.approx((2050 / 2000 - 1) * 100, abs=1e-6)


def test_portfolio_without_deposits_matches_the_old_trade_fallback_for_buys():
    # No deposit: every buy is fully an implicit contribution of its cost
    # (exactly the old buy flows), so buy-only portfolios are unchanged.
    txs = [_tx(_d(0), "buy", 1, qty=10, price=100, fees=1), _tx(_d(10), "buy", 1, qty=5, price=110)]
    bars = [
        {"asset_id": 1, "price_date": _d(0), "close": 100.0},
        {"asset_id": 1, "price_date": _d(10), "close": 110.0},
        {"asset_id": 1, "price_date": _d(20), "close": 121.0},
    ]
    service = _service(txs, bars)

    flows, implicit_only = service._get_cashflows_with_fallback(1, "u", _d(0), _d(20))
    assert [(f.side, f.amount) for f in flows] == [("implicit_contribution", 1001.0), ("implicit_contribution", 550.0)]
    assert implicit_only
    # Moving prices: the chain-linked 1.10 x 1.10 of the old fallback.
    assert service.calculate_twr(1, "u", None, _d(20)).twr_pct == pytest.approx(21.0, abs=1e-3)
    # Flat prices (trades at the close): 0%.
    flat_txs = [_tx(_d(0), "buy", 1, qty=10, price=100), _tx(_d(10), "buy", 1, qty=5, price=100)]
    flat = _service(flat_txs, FLAT)
    assert flat.calculate_twr(1, "u", None, _d(20)).twr_pct == pytest.approx(0.0, abs=1e-6)


def test_portfolio_without_deposits_keeps_sell_proceeds_in_cash():
    # Changed on purpose by TASK-46: the old fallback booked a sell as a
    # withdrawal of its proceeds (TWR 1.10 x 1.10 - 1 = 21%); now the proceeds
    # stay in cash earning 0 until a withdrawal is recorded:
    # 10 @ 100 -> 1100 (+10%), sell 5 @ 110 (550 cash), -> 605 + 550 = 1155 (+5%).
    txs = [_tx(_d(0), "buy", 1, qty=10, price=100), _tx(_d(10), "sell", 1, qty=5, price=110)]
    bars = [
        {"asset_id": 1, "price_date": _d(0), "close": 100.0},
        {"asset_id": 1, "price_date": _d(10), "close": 110.0},
        {"asset_id": 1, "price_date": _d(20), "close": 121.0},
    ]
    service = _service(txs, bars)

    assert service.calculate_twr(1, "u", None, _d(20)).twr_pct == pytest.approx((1.10 * 1.05 - 1) * 100, abs=1e-3)
    # At flat prices (sell at the close) it stays 0%, as before.
    flat_txs = [_tx(_d(0), "buy", 1, qty=10, price=100), _tx(_d(10), "sell", 1, qty=5, price=100)]
    assert _service(flat_txs, FLAT).calculate_twr(1, "u", None, _d(20)).twr_pct == pytest.approx(0.0, abs=1e-6)


def test_summary_counts_implicit_contributions_as_invested():
    txs = [_tx(_d(0), "deposit", qty=500, price=1), _tx(_d(5), "buy", 1, qty=10, price=100)]
    service = _service(txs, FLAT)

    summary = service.get_performance_summary(1, "u", "all")

    assert summary.implicit_contributions == 500.0
    assert summary.total_deposits == 1000.0
    assert summary.net_invested == 1000.0
    assert summary.current_value == 1000.0
    assert summary.absolute_gain == 0.0
    assert summary.twr.twr_pct == pytest.approx(0.0, abs=1e-6)


def test_mcp_get_performance_exposes_implicit_contributions():
    import app.copilot_tools as copilot_tools

    txs = [_tx(_d(0), "deposit", qty=500, price=1), _tx(_d(5), "buy", 1, qty=10, price=100)]
    service = _service(txs, FLAT)
    out = copilot_tools._get_performance({}, None, service, 1, "u")

    assert set(out["implicit_contributions_eur"]) == {"1m", "3m", "ytd", "1y"}
    # The 500 implicit contribution is on D0 + 5 (January 2026): inside YTD and 1y.
    assert out["implicit_contributions_eur"]["1y"] == 500.0
    assert out["implicit_contributions_eur"]["ytd"] == 500.0
    assert "implicit_contributions_note" in out
