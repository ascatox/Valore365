"""TASK-44 part 2: section C checks of the MCP audit, on synthetic data.

Every expected value is computed independently in the test (by hand or
with a small solver), never read back from the code under test. The
outcome of each check is recorded in docs/audit-mcp-2026-11/.

An ``xfail(strict=True)`` test documents an issue left open on purpose
(no fix in TASK-44): it starts failing the day the issue is fixed, so the
marker has to be removed together with the fix.
"""

from __future__ import annotations

from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.copilot_tools as copilot_tools
from app.models import CashFlowEntry
from app.repository._utilities import _cash_balance_detail
from app.services.performance_service import PerformanceService
from tests.unit.test_summary_day_change import TODAY, _bar, _Position, _Repo as _SummaryRepo
from tests.unit.test_transactions_repository import _scripted_repo, _tx

D0 = date(2026, 1, 5)


def _d(offset: int) -> date:
    return D0 + timedelta(days=offset)


# --- C1: TWR / MWR against cash flows ------------------------------------------


class _PerfRepo:
    """Real repository valuation (scripted SQL rows) + cash flows derived
    from the same transactions with the documented sign convention
    (portfolio perspective: deposit/buy positive, withdrawal/sell negative)."""

    def __init__(self, transactions, price_bars):
        self.transactions = transactions
        self._valuation = _scripted_repo(
            transactions=transactions,
            price_bars=price_bars,
            assets=[{"id": 1, "symbol": "AAA", "quote_currency": "EUR"}],
            fx_rates=[],
            cash_balance=0.0,
        )

    def get_portfolio_inception_date(self, portfolio_id, user_id):
        return min(t["trade_date"] for t in self.transactions)

    def get_portfolio_values_in_range(self, portfolio_id, user_id, target_dates):
        return self._valuation.get_portfolio_values_in_range(portfolio_id, user_id, target_dates)

    def get_external_cashflows(self, portfolio_id, user_id, start_date=None, end_date=None, include_trades=False):
        sides = {"deposit", "withdrawal", "dividend", "fee", "interest"}
        if include_trades:
            sides |= {"buy", "sell"}
        out = []
        for t in self.transactions:
            if t["side"] not in sides:
                continue
            if start_date and t["trade_date"] < start_date or end_date and t["trade_date"] > end_date:
                continue
            amount = t["quantity"] * t["price"]
            sign = 1.0 if t["side"] in {"deposit", "buy", "dividend", "interest"} else -1.0
            out.append(CashFlowEntry(date=t["trade_date"].isoformat(), side=t["side"], amount=sign * amount))
        return out


def _irr(flows: list[tuple[int, float]]) -> float:
    """Annual IRR by bisection (ACT/365), independent from the service solver."""
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


def test_twr_trade_only_portfolio_chains_subperiods():
    # Demo-like portfolio (no deposits): the initial purchase is the starting
    # value, not a return. 10 @ 100 -> 110 (+10%), buy 5 @ 110, -> 121 (+10%).
    txs = [_tx(_d(0), "buy", 1, qty=10, price=100), _tx(_d(10), "buy", 1, qty=5, price=110)]
    bars = [
        {"asset_id": 1, "price_date": _d(0), "close": 100.0},
        {"asset_id": 1, "price_date": _d(10), "close": 110.0},
        {"asset_id": 1, "price_date": _d(20), "close": 121.0},
    ]
    service = PerformanceService(_PerfRepo(txs, bars), cache_ttl_seconds=0)

    twr = service.calculate_twr(1, "u", None, _d(20))

    assert twr.start_date == _d(0).isoformat()
    assert twr.twr_pct == pytest.approx((1.10 * 1.10 - 1) * 100, abs=1e-3)


def test_deposits_and_withdrawals_are_not_counted_as_return():
    # Flat price: whatever enters or leaves as cash must give a 0% return.
    txs = [
        _tx(_d(0), "buy", 1, qty=10, price=100),
        _tx(_d(10), "deposit", None, qty=500, price=1),
        _tx(_d(15), "withdrawal", None, qty=200, price=1),
    ]
    bars = [{"asset_id": 1, "price_date": _d(0), "close": 100.0}]
    service = PerformanceService(_PerfRepo(txs, bars), cache_ttl_seconds=0)

    twr = service.calculate_twr(1, "u", None, _d(30))
    mwr = service.calculate_mwr(1, "u", None, _d(30))

    assert twr.twr_pct == pytest.approx(0.0, abs=1e-6)
    assert mwr.mwr_pct == pytest.approx(0.0, abs=1e-3)


def test_mwr_with_mid_period_deposit_matches_independent_irr():
    # 10 @ 100 on day 0, +500 cash on day 100, price 120 on day 365.
    txs = [_tx(_d(0), "buy", 1, qty=10, price=100), _tx(_d(100), "deposit", None, qty=500, price=1)]
    bars = [
        {"asset_id": 1, "price_date": _d(0), "close": 100.0},
        {"asset_id": 1, "price_date": _d(365), "close": 120.0},
    ]
    service = PerformanceService(_PerfRepo(txs, bars), cache_ttl_seconds=0)

    mwr = service.calculate_mwr(1, "u", None, _d(365))
    twr = service.calculate_twr(1, "u", None, _d(365))

    rate = _irr([(0, -1000.0), (100, -500.0), (365, 1700.0)])
    assert mwr.mwr_annualized_pct == pytest.approx(rate * 100, abs=1e-3)
    # TWR: 0% until the deposit (price still 100), then 1500 -> 1700 with the
    # deposited cash earning nothing: (1 + 0) * 1700 / 1500 - 1 = +13.33%.
    assert twr.twr_pct == pytest.approx((1700 / 1500 - 1) * 100, abs=1e-3)


def test_twr_deposit_then_buy_at_flat_price_is_zero():
    txs = [_tx(_d(0), "deposit", None, qty=500, price=1), _tx(_d(5), "buy", 1, qty=10, price=100)]
    bars = [{"asset_id": 1, "price_date": _d(5), "close": 100.0}]
    service = PerformanceService(_PerfRepo(txs, bars), cache_ttl_seconds=0)

    twr = service.calculate_twr(1, "u", None, _d(10))

    assert twr.twr_pct == pytest.approx(0.0, abs=1e-6)


# --- C2: cash movements: sign, date, currency ------------------------------------


def test_cash_balance_signs_and_trade_date_fx():
    rows = [
        {"side": "deposit", "trade_date": _d(0), "trade_currency": "EUR", "quantity": 1000, "price": 1},
        {"side": "withdrawal", "trade_date": _d(1), "trade_currency": "EUR", "quantity": 1, "price": 300},
        {"side": "interest", "trade_date": _d(2), "trade_currency": "EUR", "quantity": 1, "price": 5},
        {"side": "fee", "trade_date": _d(3), "trade_currency": "EUR", "quantity": 1, "price": 2},
        # USD dividend: converted at the rate of its trade date (0.90), not the latest (0.95).
        {"side": "dividend", "trade_date": _d(4), "trade_currency": "USD", "quantity": 1, "price": 100},
        # TASK-49: trades move cash (performance cash model); this buy exceeds
        # the cash available, so the shortfall is an implicit contribution.
        {"side": "buy", "trade_date": _d(5), "trade_currency": "EUR", "quantity": 1, "price": 999},
    ]
    fx = [
        {"from_ccy": "USD", "price_date": _d(3), "rate": 0.90},
        {"from_ccy": "USD", "price_date": _d(9), "rate": 0.95},
    ]

    detail = _cash_balance_detail(base_currency="EUR", opening_cash_balance=0.0, rows=rows, fx_rows=fx)

    # Before TASK-49 the buy was ignored: cash = 793. Now the buy takes the 793
    # and the remaining 206 came from outside: cash floors at 0.
    before_buy = 1000 - 300 + 5 - 2 + 90.0
    assert detail.balance == 0.0
    assert detail.implicit_contributions == pytest.approx(999 - before_buy)


# --- C3: day change summary vs positions -----------------------------------------


def test_summary_day_change_uses_unrounded_prices_not_rounded_position_pcts():
    # A: 1000 x 4.8462 -> 4.8461 (-0.0021%, rounds to 0.00 on the position)
    # B: 3 x 100 -> 101.5 (+1.50%)
    daily = [
        _bar(1, TODAY, 4.8461, 1), _bar(1, TODAY - timedelta(days=1), 4.8462, 2),
        _bar(2, TODAY, 101.5, 1), _bar(2, TODAY - timedelta(days=1), 100.0, 2),
    ]
    positions = [_Position(1, 1000.0, 4846.1), _Position(2, 3.0, 304.5)]
    summary = _SummaryRepo(positions, daily, []).get_summary(1, "u")

    exact = 1000 * (4.8461 - 4.8462) + 3 * (101.5 - 100.0)
    prev_value = 1000 * 4.8462 + 3 * 100.0
    assert summary.day_change == round(exact, 2)
    assert summary.day_change_pct == round(exact / prev_value * 100, 2)
    # Rebuilding the summary from the rounded position percentages is off:
    rebuilt = 1000 * 4.8462 * round(-0.0021, 2) / 100 + 300.0 * 1.50 / 100
    assert round(rebuilt, 2) != summary.day_change


# --- C5: income yield vs total return --------------------------------------------


def test_income_projection_counts_only_distributions_and_lists_accumulating_funds():
    pos = [
        SimpleNamespace(asset_id=1, symbol="DIST", name="Distributing Equity ETF", asset_type="etf",
                        investment_focus="Equity, World", market_value=1000.0, weight=50.0),
        SimpleNamespace(asset_id=2, symbol="ACC", name="Accumulating Equity ETF", asset_type="etf",
                        investment_focus="Equity, World", market_value=1000.0, weight=50.0),
    ]
    repo = MagicMock()
    repo.get_positions.return_value = pos
    repo.get_summary.return_value = SimpleNamespace(market_value=2000.0, cost_basis=2000.0)
    repo.get_user_settings.side_effect = RuntimeError("no settings")
    repo.get_asset_metadata_bulk.return_value = {
        1: SimpleNamespace(dividend_yield=2.0, category=None),
        2: SimpleNamespace(dividend_yield=None, category=None),
    }

    out = copilot_tools._get_income_projection({}, repo, MagicMock(), 1, "u")

    # Income only: 2% of the distributing fund; the accumulating fund's total
    # return is not income and is listed, not estimated.
    assert out["current_annual_dividends_gross_eur"] == 20.0
    assert out["missing_yield_symbols"] == ["ACC"]


# --- C6: X-Ray coverage -----------------------------------------------------------


def test_xray_coverage_is_weight_with_any_top_holdings_and_exposures_are_on_total(monkeypatch):
    from app.services.portfolio_doctor import _xray
    from app.services.portfolio_doctor._holdings import AnalyzedHolding

    def _h(aid, symbol, weight):
        return AnalyzedHolding(asset_id=aid, symbol=symbol, name=f"{symbol} Equity ETF", asset_type="etf",
                               quote_currency="EUR", market_value=weight * 10, weight_pct=weight)

    monkeypatch.setattr(_xray, "_load_holdings", lambda repo, scope, user_id: [_h(1, "AAA", 50.0), _h(2, "BBB", 50.0)])
    _xray._top_holdings_cache.clear()

    class _Repo:
        def get_etf_enrichment_bulk(self, ids):
            # Only the top 2 holdings (20% of the fund) are known, 100% USA.
            return {1: {
                "top_holdings": [{"name": "X", "isin": "US1", "percentage": 12.0},
                                 {"name": "Y", "isin": "US2", "percentage": 8.0}],
                "country_weights": [{"name": "USA", "percentage": 100.0}],
            }}

        def get_asset_pricing_symbols(self, ids, provider):
            return {}

    finance = SimpleNamespace(get_etf_top_holdings=lambda symbol: [])
    out = copilot_tools._get_xray_summary({}, _Repo(), MagicMock(), 1, "u", finance_client=finance)
    _xray._top_holdings_cache.clear()

    # Fund AAA counts as fully covered although only 20% of its basket is known.
    assert out["coverage_pct"] == 50.0
    # Exposures are shares of the whole (invested) portfolio, not of the covered part.
    assert out["geographic_exposure"] == {"USA": 50.0}
    assert out["top_underlying_holdings"][0]["aggregated_weight_pct"] == 6.0
    # No reference date of the provider data in the output.
    assert "as_of" not in out and "data_date" not in out


# --- C8: fractional quantities ----------------------------------------------------


def test_valuation_keeps_original_fractional_quantity():
    txs = [_tx(_d(0), "buy", 1, qty=744.00010311, price=100.0)]
    bars = [{"asset_id": 1, "price_date": _d(0), "close": 100.0}]
    repo = _scripted_repo(transactions=txs, price_bars=bars,
                          assets=[{"id": 1, "symbol": "AAA", "quote_currency": "EUR"}],
                          fx_rates=[], cash_balance=0.0)

    values = repo.get_portfolio_values_in_range(1, "u", [_d(0)])

    assert values[_d(0)] == round(744.00010311 * 100.0, 2)
