"""TASK-33: get_day_movers (V365-005) and get_monte_carlo (V365-006)."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.copilot_tools as copilot_tools
from app.models import Position
from app.schemas.portfolio_doctor import MonteCarloProjectionResponse, MonteCarloYearProjection


def _pos(symbol: str, day_change_pct: float = 0.0, *, stale: bool = False, price_date: date | None = date(2026, 11, 2)) -> Position:
    return Position(
        asset_id=hash(symbol) % 1000,
        symbol=symbol,
        name=f"{symbol} name",
        quantity=1,
        avg_cost=100,
        market_price=100,
        market_value=100,
        unrealized_pl=0,
        unrealized_pl_pct=0,
        weight=10,
        day_change_pct=day_change_pct,
        price_stale=stale,
        price_date=price_date,
        previous_close_available=True,
    )


def _repo(positions: list[Position]) -> MagicMock:
    repo = MagicMock()
    repo.get_positions.return_value = positions
    # Must NOT be used: it returns 1-year returns of target assets.
    repo.get_portfolio_target_performance.return_value = SimpleNamespace(
        best=SimpleNamespace(symbol="TARGET1Y", day_change_pct=99.0),
        worst=SimpleNamespace(symbol="TARGET1Y", day_change_pct=-99.0),
    )
    return repo


def _movers(positions: list[Position]) -> dict:
    return copilot_tools._get_day_movers({}, _repo(positions), MagicMock(), 1, "u")


# --- V365-005 -----------------------------------------------------------------

def test_day_movers_uses_positions_not_target_performance():
    out = _movers([_pos("AAA", 1.5), _pos("BBB", -2.25), _pos("CCC", 0.3)])
    assert out["best"]["symbol"] == "AAA"
    assert out["best"]["day_change_pct"] == 1.5
    assert out["best"]["name"] == "AAA name"
    assert out["worst"]["symbol"] == "BBB"
    assert out["worst"]["day_change_pct"] == -2.25


def test_day_movers_skips_stale_and_unpriced_positions():
    out = _movers([
        _pos("STALE", 9.0, stale=True),
        _pos("NOPRICE", -9.0, price_date=None),
        _pos("OK1", 0.5),
        _pos("OK2", -0.5),
    ])
    assert out["best"]["symbol"] == "OK1"
    assert out["worst"]["symbol"] == "OK2"
    assert out["valid_positions"] == 2
    assert out["excluded_stale"] == 2


def test_day_movers_stable_tie_break_by_symbol():
    out = _movers([_pos("ZZZ", 0.0), _pos("AAA", 0.0), _pos("MMM", 0.0)])
    # All zero is still valid data: deterministic order by symbol.
    assert out["best"]["symbol"] == "AAA"
    assert out["worst"]["symbol"] == "AAA"
    out = _movers([_pos("ZZZ", 1.0), _pos("AAA", 1.0), _pos("BBB", -1.0), _pos("ABB", -1.0)])
    assert out["best"]["symbol"] == "AAA"
    assert out["worst"]["symbol"] == "ABB"


def test_day_movers_no_valid_positions_returns_reason():
    out = _movers([_pos("STALE", 3.0, stale=True)])
    assert out["best"] is None and out["worst"] is None
    assert isinstance(out["reason"], str) and out["reason"]
    out = _movers([])
    assert out["best"] is None and out["worst"] is None
    assert out["reason"]


def test_day_movers_without_reason_when_data_present():
    out = _movers([_pos("AAA", 1.0)])
    assert "reason" not in out


# --- V365-006 -----------------------------------------------------------------

def _mc_response() -> MonteCarloProjectionResponse:
    projections = []
    for year in range(0, 21):
        base = 100 * (1.05 ** year)
        projections.append(MonteCarloYearProjection(
            year=year, p10=base * 0.7, p25=base * 0.85, p50=base, p75=base * 1.15, p90=base * 1.3,
        ))
    return MonteCarloProjectionResponse(
        portfolio_id=1, num_simulations=1000, horizons=[5, 10, 20], projections=projections,
        annualized_mean_return_pct=5.0, annualized_volatility_pct=12.0,
    )


def test_monte_carlo_returns_years_1_to_10_with_unit(monkeypatch):
    resp = _mc_response()
    # Shuffled input: the output must still be sorted.
    resp.projections = list(reversed(resp.projections))
    monkeypatch.setattr(copilot_tools, "run_monte_carlo_projection", lambda *a, **k: resp)
    out = copilot_tools._get_monte_carlo({}, MagicMock(), MagicMock(), 1, "u")
    years = [p["year"] for p in out["projections"]]
    assert years == list(range(1, 11))
    for p in out["projections"]:
        assert p["p25"] <= p["p50"] <= p["p75"]
    assert out["unit"] == "indice_base_100"
    assert out["initial_value"] == 100
    assert "100" in out["unit_note"]


def test_monte_carlo_tool_description_mentions_index_unit():
    definition = next(d for d in copilot_tools.TOOL_DEFINITIONS if d["name"] == "get_monte_carlo")
    assert "base 100" in definition["description"]
