"""TASK-47: one FX rule for cash, no silent fallbacks, net dividends.

- get_cash_balance (REST ``get_computed_cash_balance``) and
  ``summary.cash_balance`` share one helper: every cash movement in a
  non-base currency is converted at the FX rate of its trade date.
- A missing FX rate keeps the computation going (rate 1.0, price = avg cost)
  but is reported: ``fx_missing_currencies`` on cash and summary,
  ``price_fallback`` / ``fx_missing`` on positions.
- Dividends move cash net of withholding taxes (amount - taxes), in the
  summary/cash balance and in the TASK-46 cash model.

Expected values are computed by hand in each test.
"""

from __future__ import annotations

from datetime import datetime, time, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.copilot_tools as copilot_tools
from app.mcp_server import aggregate_tools
from app.repository import PortfolioRepository
from app.repository._cash_model import cash_delta
from app.repository._utilities import _compute_cash_balance_base
from tests.unit.test_aggregate_repository import D0, D1, D2, D3, TODAY, USER, _Begin, _Conn, _Db, _Result
from tests.unit.test_transactions_repository import _scripted_repo, _tx


class _FxConn(_Conn):
    """The aggregate-test connection, plus FX rows and the asset columns of
    the recent cash movements."""

    def execute(self, statement, params=None):
        params = params or {}
        sql = " ".join(str(statement).split())
        if "from fx_rates_1d" in sql:
            from_ccy = set(params.get("from_ccy") or [])
            to_ccy = params.get("to_ccy")
            to_set = set(to_ccy) if isinstance(to_ccy, (list, tuple, set)) else {to_ccy}
            cutoff = params.get("max_trade_day") or params.get("max_day") or params.get("target_date")
            rows = [
                {**r} for r in self.db.fx
                if r["from_ccy"] in from_ccy and r["to_ccy"] in to_set
                and (cutoff is None or r["price_date"] <= cutoff)
            ]
            rows.sort(key=lambda r: (r["from_ccy"], r["price_date"]))
            if "distinct on (from_ccy)" in sql:
                latest: dict[str, dict] = {}
                for r in rows:
                    latest[r["from_ccy"]] = r
                rows = list(latest.values())
            return _Result(rows)
        result = super().execute(statement, params)
        if "from transactions" in sql and "a.symbol" in sql:
            return _Result([{**r, "symbol": None, "asset_name": None} for r in result.all()])
        return result


class _FxDb(_Db):
    def __init__(self) -> None:
        super().__init__()
        self.fx: list[dict] = []

    def begin(self):
        return _Begin(_FxConn(self))

    def add_tx(self, pid, day, side, asset_id, qty, price=1.0, *, ccy="EUR", taxes=0.0):
        self.transactions.append({
            "id": len(self.transactions) + 1,
            "portfolio_id": pid,
            "asset_id": asset_id,
            "side": side,
            "trade_at": datetime.combine(day, time(12), tzinfo=timezone.utc),
            "trade_date": day,
            "quantity": qty,
            "price": price,
            "fees": 0.0,
            "taxes": taxes,
            "trade_currency": ccy,
            "notes": None,
        })


def _cash_repo(*, fx: bool = True) -> tuple[PortfolioRepository, _FxDb]:
    db = _FxDb()
    db.portfolio(1, cash=200.0)
    db.add_tx(1, D0, "deposit", None, 1000.0)
    # USD dividend on D1: 100 USD at the D0 rate 0.90 = 90 EUR (latest is 0.95).
    db.add_tx(1, D1, "dividend", None, 1.0, 100.0, ccy="USD")
    if fx:
        db.fx = [
            {"from_ccy": "USD", "to_ccy": "EUR", "price_date": D0, "rate": 0.90},
            {"from_ccy": "USD", "to_ccy": "EUR", "price_date": D3, "rate": 0.95},
        ]
    return PortfolioRepository(db), db


# --- 1. one FX rule ---------------------------------------------------------------


def test_get_cash_balance_and_summary_use_the_trade_date_fx():
    repo, _ = _cash_repo()

    computed = repo.get_computed_cash_balance(1, USER)
    summary = repo.get_summary(1, USER)

    expected = 200.0 + 1000.0 + 100.0 * 0.90
    assert summary.cash_balance == pytest.approx(expected)
    assert computed.total_cash == pytest.approx(expected)
    # Per-currency nominal balances, opening cash in the base currency.
    assert {(b.currency, b.balance) for b in computed.currency_breakdown} == {("EUR", 1200.0), ("USD", 100.0)}
    assert computed.fx_missing_currencies == []
    assert summary.fx_missing_currencies == []


def test_missing_fx_rate_is_flagged_not_hidden():
    repo, _ = _cash_repo(fx=False)

    computed = repo.get_computed_cash_balance(1, USER)
    summary = repo.get_summary(1, USER)

    # Still computed (rate 1.0), but reported.
    assert computed.total_cash == pytest.approx(1300.0)
    assert summary.cash_balance == pytest.approx(1300.0)
    assert computed.fx_missing_currencies == ["USD"]
    assert summary.fx_missing_currencies == ["USD"]


def test_aggregate_summary_unions_the_missing_currencies():
    repo, db = _cash_repo(fx=False)
    db.portfolio(2)
    db.add_tx(2, D0, "deposit", None, 50.0, ccy="GBP")

    summary = repo.get_summary_multi([1, 2], USER)

    assert summary.cash_balance == pytest.approx(1300.0 + 50.0)
    assert summary.fx_missing_currencies == ["GBP", "USD"]


def test_fx_dated_after_the_movement_counts_as_missing():
    rows = [{"side": "dividend", "trade_date": D0, "trade_currency": "USD", "quantity": 1, "price": 10, "taxes": 0}]
    fx = [{"from_ccy": "USD", "price_date": D1, "rate": 0.9}]
    from app.repository._utilities import _cash_balance_detail

    detail = _cash_balance_detail(base_currency="EUR", opening_cash_balance=0.0, rows=rows, fx_rows=fx)

    assert detail.balance == 10.0
    assert detail.fx_missing_currencies == ["USD"]


# --- 2. positions: price fallback and missing FX -------------------------------------


def _positions_repo() -> PortfolioRepository:
    db = _FxDb()
    db.portfolio(1)
    db.assets = [
        {"id": 10, "symbol": "EURX", "name": "Euro", "asset_type": "etf", "quote_currency": "EUR"},
        {"id": 20, "symbol": "USDX", "name": "Usd", "asset_type": "stock", "quote_currency": "USD"},
        {"id": 30, "symbol": "NOPX", "name": "No price", "asset_type": "stock", "quote_currency": "EUR"},
    ]
    db.bars = [
        {"asset_id": 10, "price_date": TODAY, "close": 12.0},
        {"asset_id": 20, "price_date": TODAY, "close": 50.0},
    ]
    db.add_tx(1, D1, "buy", 10, 10.0, 10.0)
    db.add_tx(1, D1, "buy", 20, 2.0, 40.0)  # bought in EUR, quoted in USD, no USD rate
    db.add_tx(1, D2, "buy", 30, 1.0, 7.0)
    return PortfolioRepository(db)


def test_positions_flag_price_fallback_and_missing_fx():
    by_symbol = {p.symbol: p for p in _positions_repo().get_positions(1, USER)}

    assert by_symbol["EURX"].price_fallback is None
    assert by_symbol["EURX"].fx_missing is False
    assert by_symbol["EURX"].market_price == 12.0

    usd = by_symbol["USDX"]
    assert usd.market_price == 40.0  # avg cost, as before
    assert usd.price_fallback == "avg_cost"
    assert usd.fx_missing is True
    assert usd.fx_missing_currencies == ["USD"]

    nop = by_symbol["NOPX"]
    assert nop.price_fallback == "avg_cost"
    assert nop.fx_missing is False


def test_summary_lists_price_fallbacks_and_position_fx_gaps():
    summary = _positions_repo().get_summary(1, USER)

    assert summary.price_fallback_symbols == ["NOPX", "USDX"]
    assert summary.fx_missing_currencies == ["USD"]
    # Values unchanged: 10 x 12 + 2 x 40 + 1 x 7.
    assert summary.market_value == pytest.approx(207.0)


# --- 3. dividend withholding taxes ------------------------------------------------


def test_dividend_cash_is_net_of_withholding_taxes():
    rows = [
        {"side": "deposit", "trade_date": D0, "trade_currency": "EUR", "quantity": 100, "price": 1, "taxes": 0},
        {"side": "dividend", "trade_date": D1, "trade_currency": "EUR", "quantity": 1, "price": 20, "taxes": 5.2},
        {"side": "dividend", "trade_date": D1, "trade_currency": "USD", "quantity": 1, "price": 10, "taxes": 1.5},
    ]
    fx = [{"from_ccy": "USD", "price_date": D0, "rate": 0.9}]

    cash = _compute_cash_balance_base(base_currency="EUR", opening_cash_balance=0.0, rows=rows, fx_rows=fx)

    assert cash == pytest.approx(100 + (20 - 5.2) + (10 - 1.5) * 0.9)


def test_get_cash_balance_and_summary_apply_net_dividends():
    db = _FxDb()
    db.portfolio(1)
    db.add_tx(1, D0, "deposit", None, 1000.0)
    db.add_tx(1, D1, "dividend", None, 1.0, 100.0, taxes=26.0)
    repo = PortfolioRepository(db)

    computed = repo.get_computed_cash_balance(1, USER)

    assert computed.total_cash == pytest.approx(1074.0)
    assert repo.get_summary(1, USER).cash_balance == pytest.approx(1074.0)
    assert [(b.currency, b.balance) for b in computed.currency_breakdown] == [("EUR", 1074.0)]


def test_cash_model_dividend_is_net_of_taxes():
    assert cash_delta("dividend", 100.0, 0.0, taxes_base=26.0) == pytest.approx(74.0)
    # Taxes stay out of the other cash-in sides' rule (they are always 0 there).
    assert cash_delta("deposit", 100.0, 0.0) == pytest.approx(100.0)
    assert cash_delta("buy", 100.0, 3.0) == pytest.approx(-103.0)


def test_valuation_fold_applies_net_dividends():
    div = _tx(D1, "dividend", None, qty=1.0, price=100.0)
    div["taxes"] = 26.0
    repo = _scripted_repo(
        transactions=[_tx(D0, "deposit", None, qty=1000.0, price=1.0), div],
        price_bars=[], fx_rates=[], cash_balance=0.0,
    )

    values = repo.get_portfolio_values_in_range(1, "u", [D2])

    assert values[D2] == pytest.approx(1074.0)


def test_external_cashflow_dividend_entry_is_net():
    db = _FxDb()
    db.portfolio(1)
    db.add_tx(1, D1, "dividend", None, 1.0, 100.0, taxes=26.0)

    flows = PortfolioRepository(db).get_external_cashflows(1, USER)

    assert [(f.side, f.amount) for f in flows] == [("dividend", 74.0)]


# --- copilot / MCP tools ------------------------------------------------------------


def _summary(**kw):
    base = dict(market_value=100.0, cost_basis=90.0, unrealized_pl=10.0, unrealized_pl_pct=11.11,
                day_change=0.0, day_change_pct=0.0, cash_balance=50.0, base_currency="EUR",
                fx_missing_currencies=[], price_fallback_symbols=[])
    base.update(kw)
    return SimpleNamespace(**base)


def _position(symbol, *, price_fallback=None, fx_missing=False):
    return SimpleNamespace(symbol=symbol, name=symbol, weight=50.0, market_value=10.0, avg_cost=1.0,
                           quantity=10.0, unrealized_pl_pct=0.0, day_change_pct=0.0, market_price=1.0,
                           price_fallback=price_fallback, fx_missing=fx_missing)


def test_copilot_tools_expose_the_flags_with_a_note():
    repo = MagicMock()
    repo.get_summary.return_value = _summary(fx_missing_currencies=["USD"], price_fallback_symbols=["USDX"])
    repo.get_positions.return_value = [_position("USDX", price_fallback="avg_cost", fx_missing=True), _position("EURX")]
    repo.get_current_cash_balance_detail.return_value = SimpleNamespace(balance=50.0, fx_missing_currencies=["USD"])

    summary = copilot_tools._get_portfolio_summary({}, repo, MagicMock(), 1, "u")
    cash = copilot_tools._get_cash_balance({}, repo, MagicMock(), 1, "u")
    positions = copilot_tools._get_positions({}, repo, MagicMock(), 1, "u")

    assert summary["fx_missing_currencies"] == ["USD"]
    assert summary["price_fallback_symbols"] == ["USDX"]
    assert "cambio" in summary["data_quality_note"]
    assert cash["fx_missing_currencies"] == ["USD"]
    assert "cambio" in cash["data_quality_note"]
    rows = {p["symbol"]: p for p in positions["positions"]}
    assert rows["USDX"]["price_fallback"] == "avg_cost" and rows["USDX"]["fx_missing"] is True
    assert rows["EURX"]["price_fallback"] is None and rows["EURX"]["fx_missing"] is False
    assert "costo medio" in positions["data_quality_note"]


def test_copilot_tools_have_no_note_when_everything_is_priced():
    repo = MagicMock()
    repo.get_summary.return_value = _summary()
    repo.get_positions.return_value = [_position("EURX")]
    repo.get_current_cash_balance_detail.return_value = SimpleNamespace(balance=50.0, fx_missing_currencies=[])

    assert "data_quality_note" not in copilot_tools._get_portfolio_summary({}, repo, MagicMock(), 1, "u")
    assert "data_quality_note" not in copilot_tools._get_cash_balance({}, repo, MagicMock(), 1, "u")
    assert "data_quality_note" not in copilot_tools._get_positions({}, repo, MagicMock(), 1, "u")


def test_aggregate_mcp_tools_expose_the_flags():
    deps = SimpleNamespace(repo=MagicMock())
    deps.repo.get_summary_multi.return_value = _summary(fx_missing_currencies=["USD"])
    deps.repo.get_positions_multi.return_value = [_position("USDX", price_fallback="avg_cost", fx_missing=True)]

    summary = aggregate_tools._summary(deps, [1, 2], "u")
    positions = aggregate_tools._positions(deps, [1, 2], "u")

    assert summary["fx_missing_currencies"] == ["USD"] and "data_quality_note" in summary
    assert positions["positions"][0]["price_fallback"] == "avg_cost"
    assert "data_quality_note" in positions
