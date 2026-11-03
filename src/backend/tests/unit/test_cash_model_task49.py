"""TASK-49: the summary cash follows the performance cash model (one truth).

- ``summary.cash_balance``, ``GET /cash-balance`` (``total_cash``), the MCP /
  copilot tools and the aggregates fold every transaction with the rules of
  ``repository/_cash_model.py``: buys debit cash (fees/taxes included), sells
  credit the net proceeds, deposits / net dividends / interest credit,
  withdrawals / fees debit; an end-of-day shortfall is an implicit
  contribution and cash never goes below 0.
- The undated opening ``portfolios.cash_balance`` is cash available before
  the first transaction, in the current cash and in the performance history
  (valuation fold + an external deposit on the first transaction day).
- Invariant: summary ``market_value + cash_balance`` == the last value of the
  performance series (``current_value``).

Expected values are computed by hand in each test.
"""

from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.copilot_tools as copilot_tools
from app.mcp_server import aggregate_tools
from app.repository import PortfolioRepository
from app.repository._utilities import CASH_COMPONENT_SIGNS, CASH_MODEL_NOTE
from app.services.performance_service import PerformanceService
from tests.unit.test_aggregate_repository import D0, D1, D2, D3, TODAY, USER
from tests.unit.test_cash_fx_task47 import _FxDb

ASSET = {"id": 10, "symbol": "AAA", "name": "Asset A", "asset_type": "etf", "quote_currency": "EUR"}


def _bars(db: _FxDb, closes: list[tuple]) -> None:
    for day, close in closes:
        db.bars.append({"asset_id": 10, "price_date": day, "close": close})


def _synthetic_db(*, pid: int = 1, opening: float = 0.0) -> _FxDb:
    """methodology.md section 9.1: deposit 1000, buy 8 x 100, sell 3 x 110,
    dividend 20 with 5.20 withholding tax, final price 110."""
    db = _FxDb()
    db.portfolio(pid, cash=opening)
    db.assets = [ASSET]
    _bars(db, [(D1, 100.0), (D2, 110.0), (TODAY, 110.0)])
    db.add_tx(pid, D0, "deposit", None, 1000.0)
    db.add_tx(pid, D1, "buy", 10, 8.0, 100.0)
    db.add_tx(pid, D2, "sell", 10, 3.0, 110.0)
    db.add_tx(pid, D3, "dividend", None, 1.0, 20.0, taxes=5.20)
    return db


def _components_total(components: dict[str, float]) -> float:
    return sum(CASH_COMPONENT_SIGNS[key] * value for key, value in components.items())


# --- 1. the synthetic example ------------------------------------------------------


def test_synthetic_example_summary_total_equals_performance_value():
    repo = PortfolioRepository(_synthetic_db())

    summary = repo.get_summary(1, USER)
    perf = PerformanceService(repo, cache_ttl_seconds=0).get_performance_summary(1, USER, "1y")
    value_today = repo.get_portfolio_values_in_range(1, USER, [TODAY])[TODAY]

    # Before TASK-49: cash 1014.80 (trades ignored), total 1564.80.
    assert summary.market_value == pytest.approx(550.0)  # 5 x 110
    assert summary.cash_balance == pytest.approx(544.80)  # 1000 - 800 + 330 + 14.80
    assert summary.implicit_contributions_total == 0.0
    total = summary.market_value + summary.cash_balance
    assert total == pytest.approx(1094.80)
    assert value_today == pytest.approx(1094.80)
    assert perf.current_value == pytest.approx(total)


def test_synthetic_example_cash_endpoints_agree_and_breakdown_adds_up():
    repo = PortfolioRepository(_synthetic_db())

    computed = repo.get_computed_cash_balance(1, USER)
    detail = repo.get_current_cash_balance_detail(1, USER)

    assert computed.total_cash == pytest.approx(544.80)
    assert detail.balance == computed.total_cash
    assert computed.implicit_contributions_total == 0.0
    assert computed.cash_model_note == CASH_MODEL_NOTE
    b = computed.cash_breakdown
    assert (b.deposits, b.buys, b.sells, b.dividends) == pytest.approx((1000.0, 800.0, 330.0, 14.80))
    assert _components_total(b.model_dump()) == pytest.approx(computed.total_cash)
    # Nominal per currency (all EUR): the same total.
    assert [(c.currency, c.balance) for c in computed.currency_breakdown] == [("EUR", 544.80)]


# --- 2. trade-only portfolio (no deposits) ----------------------------------------


def test_trade_only_portfolio_cash_is_the_sell_proceeds_and_matches_performance():
    db = _FxDb()
    db.portfolio(1)
    db.assets = [ASSET]
    _bars(db, [(D1, 100.0), (D2, 110.0), (TODAY, 110.0)])
    db.add_tx(1, D1, "buy", 10, 10.0, 100.0)
    db.add_tx(1, D2, "sell", 10, 4.0, 110.0)
    db.add_tx(1, D3, "buy", 10, 1.0, 110.0)
    repo = PortfolioRepository(db)

    summary = repo.get_summary(1, USER)
    perf = PerformanceService(repo, cache_ttl_seconds=0).get_performance_summary(1, USER, "1y")

    # D1 buy 1000 with no cash: implicit contribution 1000, cash 0.
    # D2 sell 4 x 110 = 440 in cash; D3 buy 110 paid from it -> 330.
    # Before TASK-49 the summary cash was 0 (total 770).
    assert summary.cash_balance == pytest.approx(330.0)
    assert summary.implicit_contributions_total == pytest.approx(1000.0)
    assert summary.market_value == pytest.approx(7 * 110.0)
    assert summary.market_value + summary.cash_balance == pytest.approx(1100.0)
    assert perf.current_value == pytest.approx(1100.0)
    assert perf.implicit_contributions == pytest.approx(1000.0)


def test_withdrawal_beyond_cash_floors_at_zero():
    db = _FxDb()
    db.portfolio(1)
    db.add_tx(1, D0, "deposit", None, 100.0)
    db.add_tx(1, D1, "withdrawal", None, 150.0)
    db.add_tx(1, D2, "deposit", None, 20.0)
    repo = PortfolioRepository(db)

    detail = repo.get_current_cash_balance_detail(1, USER)

    # Was -30 before TASK-49 (cash could go negative).
    assert detail.balance == 20.0
    assert detail.implicit_contributions == 50.0
    assert _components_total(detail.components) == pytest.approx(detail.balance)


def test_same_day_deposit_covers_an_earlier_buy():
    # End-of-day settlement, like the performance fold: intraday order does not matter.
    db = _FxDb()
    db.portfolio(1)
    db.assets = [ASSET]
    _bars(db, [(D1, 100.0), (TODAY, 100.0)])
    db.add_tx(1, D1, "buy", 10, 5.0, 100.0)
    db.add_tx(1, D1, "deposit", None, 600.0)
    repo = PortfolioRepository(db)

    detail = repo.get_current_cash_balance_detail(1, USER)

    assert detail.balance == 100.0
    assert detail.implicit_contributions == 0.0


# --- 3. opening balance ------------------------------------------------------------


def test_opening_balance_is_cash_before_the_first_transaction_everywhere():
    repo = PortfolioRepository(_synthetic_db(opening=200.0))

    summary = repo.get_summary(1, USER)
    values = repo.get_portfolio_values_in_range(1, USER, [D0 - timedelta(days=1), D0, TODAY])
    flows = repo.get_external_cashflows(1, USER, include_trades=True)
    perf = PerformanceService(repo, cache_ttl_seconds=0).get_performance_summary(1, USER, "1y")

    assert summary.cash_balance == pytest.approx(744.80)
    assert summary.market_value + summary.cash_balance == pytest.approx(1294.80)
    # History: nothing before the first transaction, opening + deposit from D0 on.
    assert values[D0 - timedelta(days=1)] == 0.0
    assert values[D0] == pytest.approx(1200.0)
    assert values[TODAY] == pytest.approx(1294.80)
    assert perf.current_value == pytest.approx(1294.80)
    # The opening balance is an external deposit of the first transaction day,
    # so it is invested capital, not return.
    assert (flows[0].date, flows[0].side, flows[0].amount) == (D0.isoformat(), "deposit", 200.0)
    assert perf.total_deposits == pytest.approx(1200.0)
    assert perf.absolute_gain == pytest.approx(94.80)


def test_opening_balance_only_portfolio_keeps_its_cash():
    db = _FxDb()
    db.portfolio(1, cash=300.0)
    repo = PortfolioRepository(db)

    assert repo.get_summary(1, USER).cash_balance == 300.0
    assert repo.get_computed_cash_balance(1, USER).cash_breakdown.opening_balance == 300.0
    # A windowed list (start_date set) does not invent the opening deposit.
    assert repo.get_external_cashflows(1, USER, start_date=D0) == []


def test_opening_balance_covers_the_first_buy():
    db = _FxDb()
    db.portfolio(1, cash=500.0)
    db.assets = [ASSET]
    _bars(db, [(D1, 100.0), (TODAY, 100.0)])
    db.add_tx(1, D1, "buy", 10, 6.0, 100.0)
    repo = PortfolioRepository(db)

    detail = repo.get_current_cash_balance_detail(1, USER)
    perf = PerformanceService(repo, cache_ttl_seconds=0).get_performance_summary(1, USER, "1y")

    # 500 opening - 600 buy: 100 implicit, cash 0; value 600 = performance value.
    assert detail.balance == 0.0
    assert detail.implicit_contributions == 100.0
    assert perf.current_value == pytest.approx(600.0)
    assert perf.implicit_contributions == pytest.approx(100.0)
    assert perf.total_deposits == pytest.approx(600.0)
    assert perf.twr.twr_pct == pytest.approx(0.0, abs=1e-6)


# --- 4. aggregate ------------------------------------------------------------------


def test_aggregate_summary_total_equals_aggregate_performance_value():
    db = _synthetic_db()
    db.portfolio(2)
    db.add_tx(2, D1, "buy", 10, 2.0, 100.0)
    repo = PortfolioRepository(db)

    agg = repo.get_summary_multi([1, 2], USER)
    perf = PerformanceService(repo, cache_ttl_seconds=0).get_performance_summary([1, 2], USER, "1y")

    # P2: buy 200 with no cash -> implicit 200, cash 0, 2 x 110 = 220.
    assert agg.cash_balance == pytest.approx(544.80)
    assert agg.implicit_contributions_total == pytest.approx(200.0)
    assert agg.market_value + agg.cash_balance == pytest.approx(1094.80 + 220.0)
    assert perf.current_value == pytest.approx(agg.market_value + agg.cash_balance)


# --- 5. tools ----------------------------------------------------------------------


def test_copilot_and_mcp_tools_expose_the_cash_model():
    repo = PortfolioRepository(_synthetic_db())

    summary = copilot_tools._get_portfolio_summary({}, repo, MagicMock(), 1, USER)
    cash = copilot_tools._get_cash_balance({}, repo, MagicMock(), 1, USER)

    assert summary["cash_balance"] == pytest.approx(544.80)
    assert summary["implicit_contributions_total"] == 0.0
    assert summary["cash_model_note"] == CASH_MODEL_NOTE
    assert cash["total_cash"] == summary["cash_balance"]
    assert cash["base_currency"] == "EUR"
    assert cash["cash_model_note"] == CASH_MODEL_NOTE
    assert _components_total(cash["cash_breakdown"]) == pytest.approx(cash["total_cash"])

    agg = aggregate_tools._summary(SimpleNamespace(repo=repo), [1], USER)
    assert agg["cash_model_note"] == CASH_MODEL_NOTE
    assert "implicit_contributions_total" in agg


def test_rebalance_available_cash_is_the_model_cash():
    repo = PortfolioRepository(_synthetic_db())
    target = SimpleNamespace(asset_id=10, symbol="AAA", name="Asset A", weight_pct=100.0)
    repo.list_portfolio_target_allocations = lambda *_a, **_k: [target]

    out = copilot_tools._calculate_rebalance_orders({}, repo, MagicMock(), 1, USER)

    # Before TASK-49 the plan started from 1014.80 of cash (buys ignored),
    # i.e. it could spend the 800 already invested a second time.
    assert out["totals"]["cash_before"] == pytest.approx(544.80)
    assert out["total_value"] == pytest.approx(1094.80)
    assert out["totals"]["invariant_ok"] is True
