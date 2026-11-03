"""TASK-44 part 1: leftovers of the MCP audit (TASK-33/35/36/42).

a) day movers must not treat a missing previous close as a flat day;
b) a Yahoo BOND quote type does not turn an etf/fund into a bond;
c) dividend summary / search_asset_info resolve held symbols by exact
   symbol (asset_id), never through the loose base-ticker match;
d) dividend summary does not sum amounts in different currencies.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.copilot_tools as copilot_tools
from app.finance_client import resolve_refreshed_asset_type
from app.models import Position


def _pos(
    symbol: str,
    day_change_pct: float = 0.0,
    *,
    asset_id: int = 1,
    previous_close_available: bool | None = True,
    market_value: float = 100.0,
    weight: float = 50.0,
) -> Position:
    kwargs = dict(
        asset_id=asset_id,
        symbol=symbol,
        name=f"{symbol} name",
        quantity=1,
        avg_cost=100,
        market_price=100,
        market_value=market_value,
        unrealized_pl=0,
        unrealized_pl_pct=0,
        weight=weight,
        day_change_pct=day_change_pct,
        price_date=date(2026, 11, 2),
    )
    if previous_close_available is not None:
        kwargs["previous_close_available"] = previous_close_available
    return Position(**kwargs)


# --- a) previous close ----------------------------------------------------------


def test_position_previous_close_defaults_to_unavailable():
    # The 0.0 default of day_change_pct is not a measurement.
    assert _pos("AAA", previous_close_available=None).previous_close_available is False


def test_day_movers_excludes_positions_without_previous_close():
    repo = MagicMock()
    repo.get_positions.return_value = [
        _pos("NOPREV", 0.0, previous_close_available=False),
        _pos("UP", 1.2),
        _pos("DOWN", -0.4),
    ]
    out = copilot_tools._get_day_movers({}, repo, MagicMock(), 1, "u")
    assert out["best"]["symbol"] == "UP"
    assert out["worst"]["symbol"] == "DOWN"
    assert out["valid_positions"] == 2
    assert out["excluded_no_previous_close"] == 1


def test_day_movers_all_without_previous_close_gives_reason():
    repo = MagicMock()
    repo.get_positions.return_value = [_pos("A", 0.0, previous_close_available=False)]
    out = copilot_tools._get_day_movers({}, repo, MagicMock(), 1, "u")
    assert out["best"] is None and out["worst"] is None
    assert "chiusura precedente" in out["reason"]


def test_flat_day_with_previous_close_is_still_valid():
    repo = MagicMock()
    repo.get_positions.return_value = [_pos("FLAT", 0.0, previous_close_available=True)]
    out = copilot_tools._get_day_movers({}, repo, MagicMock(), 1, "u")
    assert out["best"]["symbol"] == "FLAT"


# --- b) BOND quote type -----------------------------------------------------------


@pytest.mark.parametrize(
    "current, expected",
    [("etf", "etf"), ("fund", "fund"), ("stock", "bond"), (None, "bond"), ("bond", "bond")],
)
def test_bond_quote_type_does_not_retype_funds(current, expected):
    assert resolve_refreshed_asset_type(current, "BOND") == expected


# --- c) exact symbol resolution ---------------------------------------------------


def _meta(dividend_yield: float | None = None, **extra) -> SimpleNamespace:
    base = dict(dividend_yield=dividend_yield, description=None)
    base.update(extra)
    return SimpleNamespace(**base)


def _div_repo(positions, txns, metadata: dict[int, SimpleNamespace], base_currency="EUR"):
    repo = MagicMock()
    repo.get_positions.return_value = positions
    repo.list_transactions.return_value = txns
    repo.get_summary.return_value = SimpleNamespace(
        market_value=sum(p.market_value for p in positions), base_currency=base_currency,
    )
    repo.get_asset_metadata.side_effect = lambda aid: metadata.get(aid)
    # Loose base-ticker match: would resolve XAD1.DE to another listing (id 99).
    repo.get_asset_by_symbol.side_effect = lambda s: {"id": 99, "symbol": "XAD1.MI", "name": "Other listing"}
    return repo


def test_dividend_summary_uses_position_asset_id_not_loose_symbol_match():
    positions = [_pos("XAD1.DE", asset_id=7, market_value=1000, weight=100)]
    metadata = {7: _meta(2.0), 99: _meta(9.0)}
    repo = _div_repo(positions, [], metadata)
    out = copilot_tools._get_dividend_summary({}, repo, MagicMock(), 1, "u")
    assert out["portfolio_weighted_yield_pct"] == 2.0
    assert out["top_yielding_positions"][0]["dividend_yield_pct"] == 2.0
    repo.get_asset_by_symbol.assert_not_called()


def _asset_detail(symbol: str, asset_id: int):
    return SimpleNamespace(id=asset_id, symbol=symbol, asset_type="etf", quote_currency="EUR", isin=f"ISIN{asset_id}")


def test_search_asset_info_resolves_held_symbol_by_asset_id():
    repo = MagicMock()
    repo.get_positions.return_value = [_pos("XAD1.DE", asset_id=7)]
    repo.get_asset.side_effect = lambda aid: _asset_detail("XAD1.DE" if aid == 7 else "XAD1.MI", aid)
    repo.get_asset_metadata.return_value = None
    repo.get_asset_by_symbol.return_value = {"id": 99, "symbol": "XAD1.MI", "name": "Other listing"}
    out = copilot_tools._search_asset_info({"symbol": "xad1.de"}, repo, MagicMock(), 1, "u")
    assert out["symbol"] == "XAD1.DE"
    assert out["isin"] == "ISIN7"
    assert out["match"] == "portfolio"
    repo.get_asset_by_symbol.assert_not_called()


def test_search_asset_info_resolves_closed_position_from_transactions():
    repo = MagicMock()
    repo.get_positions.return_value = []
    repo.list_transactions.return_value = [SimpleNamespace(symbol="SOLD.L", asset_id=5, side="sell")]
    repo.get_asset.side_effect = lambda aid: _asset_detail("SOLD.L", aid)
    repo.get_asset_metadata.return_value = None
    out = copilot_tools._search_asset_info({"symbol": "SOLD.L"}, repo, MagicMock(), 1, "u")
    assert out["isin"] == "ISIN5"
    repo.get_asset_by_symbol.assert_not_called()


def test_search_asset_info_flags_a_different_listing_for_unheld_symbols():
    repo = MagicMock()
    repo.get_positions.return_value = []
    repo.list_transactions.return_value = []
    repo.get_asset_by_symbol.return_value = {"id": 99, "symbol": "XAD1.MI", "name": "Other listing"}
    repo.get_asset.side_effect = lambda aid: _asset_detail("XAD1.MI", aid)
    repo.get_asset_metadata.return_value = None
    out = copilot_tools._search_asset_info({"symbol": "XAD1.DE"}, repo, MagicMock(), 1, "u")
    assert out["symbol"] == "XAD1.MI"
    assert out["requested_symbol"] == "XAD1.DE"
    assert out["match"] == "different_listing"
    assert "warning" in out


def test_search_asset_info_exact_unheld_symbol_is_exact():
    repo = MagicMock()
    repo.get_positions.return_value = []
    repo.list_transactions.return_value = []
    repo.get_asset_by_symbol.return_value = {"id": 3, "symbol": "VWCE.DE", "name": "VWCE"}
    repo.get_asset.side_effect = lambda aid: _asset_detail("VWCE.DE", aid)
    repo.get_asset_metadata.return_value = None
    out = copilot_tools._search_asset_info({"symbol": "vwce.de"}, repo, MagicMock(), 1, "u")
    assert out["match"] == "exact"
    assert "warning" not in out


# --- d) dividends in more than one currency ------------------------------------


def _div(amount: float, ccy: str, days_ago: int = 10) -> SimpleNamespace:
    return SimpleNamespace(
        side="dividend", quantity=1, price=amount, trade_currency=ccy,
        trade_at=datetime.combine(date.today() - timedelta(days=days_ago), datetime.min.time()),
    )


def test_dividend_summary_single_currency_unchanged():
    repo = _div_repo([_pos("A", asset_id=1)], [_div(10, "EUR"), _div(5, "EUR", 400)], {})
    out = copilot_tools._get_dividend_summary({}, repo, MagicMock(), 1, "u")
    assert out["total_dividends_received"] == 15.0
    assert out["dividends_last_12m"] == 10.0
    assert out["mixed_currencies"] is False
    assert out["dividends_by_currency"] == {
        "EUR": {"total": 15.0, "last_12m": 10.0, "count": 2},
    }


def test_dividend_summary_mixed_currencies_are_not_summed():
    repo = _div_repo([_pos("A", asset_id=1)], [_div(10, "EUR"), _div(7, "USD")], {})
    out = copilot_tools._get_dividend_summary({}, repo, MagicMock(), 1, "u")
    assert out["mixed_currencies"] is True
    assert out["total_dividends_received"] is None
    assert out["dividends_last_12m"] is None
    assert out["dividends_by_currency"]["EUR"]["total"] == 10.0
    assert out["dividends_by_currency"]["USD"]["total"] == 7.0
    assert out["dividend_transactions_count"] == 2
    assert "currency_note" in out
