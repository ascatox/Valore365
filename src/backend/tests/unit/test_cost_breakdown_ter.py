"""TASK-34 / V365-007: TER units, sources and coverage in get_cost_breakdown."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import copilot_tools
from app.models import Position
from app.services.portfolio_doctor import compute_weighted_ter
from app.services.portfolio_doctor._health import resolve_holding_ters
from app.services.portfolio_doctor._holdings import AnalyzedHolding


def _meta(expense_ratio):
    return SimpleNamespace(expense_ratio=expense_ratio)


class _FakeRepo:
    """Positions given as (asset_id, symbol, name, asset_type, market_value)."""

    def __init__(self, rows, enrichment=None, metadata=None):
        total = sum(r[4] for r in rows) or 1.0
        self.positions = [
            Position(
                asset_id=aid, symbol=sym, name=name, asset_type=atype,
                quantity=1, avg_cost=mv, market_price=mv, market_value=mv,
                unrealized_pl=0, unrealized_pl_pct=0, weight=mv / total * 100,
            )
            for aid, sym, name, atype, mv in rows
        ]
        self.total = sum(r[4] for r in rows)
        self.enrichment = enrichment or {}
        self.metadata = metadata or {}

    def get_positions(self, portfolio_id, user_id):
        return self.positions

    def get_summary(self, portfolio_id, user_id):
        return SimpleNamespace(market_value=self.total)

    def get_etf_enrichment_bulk(self, asset_ids):
        return {a: e for a, e in self.enrichment.items() if a in asset_ids}

    def get_asset_metadata_bulk(self, asset_ids):
        return {a: m for a, m in self.metadata.items() if a in asset_ids}

    def holdings(self):
        return [
            AnalyzedHolding(
                asset_id=p.asset_id, symbol=p.symbol, name=p.name, asset_type=p.asset_type,
                quote_currency="EUR", market_value=p.market_value, weight_pct=p.weight,
            )
            for p in self.positions
        ]


def _run(monkeypatch, repo):
    monkeypatch.setattr(copilot_tools, "_load_holdings", lambda r, pid, uid: repo.holdings())
    return copilot_tools._get_cost_breakdown({}, repo, None, 1, "u")


def _by_symbol(result):
    return {p["symbol"]: p for p in result["position_costs"]}


def test_yfinance_fraction_is_normalized_to_percent(monkeypatch):
    repo = _FakeRepo(
        [(1, "XYZ", "Obscure Fund", "etf", 10_000.0)],
        metadata={1: _meta(0.0075)},
    )
    result = _run(monkeypatch, repo)
    pos = _by_symbol(result)["XYZ"]
    assert pos["ter_pct"] == pytest.approx(0.75)
    assert pos["ter_source"] == "yfinance"
    assert pos["annual_cost_eur"] == pytest.approx(75.0)
    assert result["weighted_ter_pct"] == pytest.approx(0.75)
    assert result["ter_coverage_pct"] == 100.0
    assert result["missing_ter_symbols"] == []
    assert result["coverage_note"] is None


def test_justetf_preferred_over_yfinance(monkeypatch):
    repo = _FakeRepo(
        [(1, "XYZ", "Obscure Fund", "etf", 1_000.0)],
        enrichment={1: {"ter": 0.22}},
        metadata={1: _meta(0.0075)},
    )
    pos = _by_symbol(_run(monkeypatch, repo))["XYZ"]
    assert pos["ter_pct"] == pytest.approx(0.22)
    assert pos["ter_source"] == "justetf"


def test_coverage_zero(monkeypatch):
    repo = _FakeRepo([
        (1, "BTC", "Bitcoin", "crypto", 6_000.0),
        (2, "FOO", "Foo Fund", "fund", 4_000.0),
    ])
    result = _run(monkeypatch, repo)
    assert result["ter_coverage_pct"] == 0.0
    assert sorted(result["missing_ter_symbols"]) == ["BTC", "FOO"]
    assert result["weighted_ter_pct"] is None
    assert result["estimated_annual_cost_known_eur"] is None
    assert result["total_annual_cost_eur"] is None
    assert result["fee_drag_10y_eur"] is None
    assert result["coverage_note"]
    assert all(p["ter_source"] == "none" for p in result["position_costs"])


def test_coverage_35_percent(monkeypatch):
    repo = _FakeRepo(
        [
            (1, "AAA", "Fund A", "etf", 3_500.0),
            (2, "BTC", "Bitcoin", "crypto", 6_500.0),
        ],
        metadata={1: _meta(0.002)},  # 0.20 %
    )
    result = _run(monkeypatch, repo)
    assert result["ter_coverage_pct"] == pytest.approx(35.0)
    assert result["missing_ter_symbols"] == ["BTC"]
    assert result["weighted_ter_pct"] == pytest.approx(0.2)
    assert result["estimated_annual_cost_known_eur"] == pytest.approx(7.0)
    assert result["total_annual_cost_eur"] == result["estimated_annual_cost_known_eur"]
    # Fee drag uses the same covered perimeter (3_500 €), not the whole 10_000 €.
    assert result["covered_market_value_eur"] == pytest.approx(3_500.0)
    assert result["fee_drag_10y_eur"] == pytest.approx(3_500 * (1 - (1 - 0.002) ** 10), abs=0.01)
    assert "35" in result["coverage_note"]
    assert "BTC" in result["coverage_note"]


def test_coverage_75_percent_excludes_cash(monkeypatch):
    repo = _FakeRepo(
        [
            (1, "AAA", "Fund A", "etf", 6_000.0),
            (2, "BBB", "Fund B", "etf", 1_500.0),
            (3, "BTC", "Bitcoin", "crypto", 2_500.0),
            (4, "EUR", "Liquidità", "cash", 10_000.0),
        ],
        enrichment={1: {"ter": 0.1}, 2: {"ter": 0.3}},
    )
    result = _run(monkeypatch, repo)
    # 7_500 covered over 10_000 non-cash
    assert result["ter_coverage_pct"] == pytest.approx(75.0)
    assert result["missing_ter_symbols"] == ["BTC"]
    assert result["estimated_annual_cost_known_eur"] == pytest.approx(6.0 + 4.5)
    assert result["coverage_note"]


def test_coverage_100_percent(monkeypatch):
    repo = _FakeRepo(
        [
            (1, "AAA", "Fund A", "etf", 5_000.0),
            (2, "BBB", "Fund B", "etf", 5_000.0),
        ],
        enrichment={1: {"ter": 0.2}, 2: {"ter": 0.4}},
    )
    result = _run(monkeypatch, repo)
    assert result["ter_coverage_pct"] == 100.0
    assert result["missing_ter_symbols"] == []
    assert result["weighted_ter_pct"] == pytest.approx(0.3)
    assert result["estimated_annual_cost_known_eur"] == pytest.approx(30.0)
    assert result["covered_market_value_eur"] == pytest.approx(10_000.0)
    assert result["fee_drag_10y_eur"] == pytest.approx(10_000 * (1 - (1 - 0.003) ** 10), abs=0.01)
    assert result["coverage_note"] is None


def test_inferred_ter_is_labelled_and_counted_as_covered(monkeypatch):
    repo = _FakeRepo([
        (1, "VWCE", "Vanguard FTSE All-World", "etf", 5_000.0),
        (2, "AAPL", "Apple Inc", "stock", 5_000.0),
    ])
    result = _run(monkeypatch, repo)
    pos = _by_symbol(result)
    assert pos["VWCE"]["ter_source"] == "inferred"
    assert pos["AAPL"]["ter_source"] == "inferred"
    assert pos["AAPL"]["ter_pct"] == 0.0
    assert result["ter_coverage_pct"] == 100.0
    assert sorted(result["inferred_ter_symbols"]) == ["AAPL", "VWCE"]


def test_resolve_holding_ters_sources_and_compute_weighted_ter_unchanged():
    holdings = [
        AnalyzedHolding(1, "A", "Fund A", "etf", "EUR", 100.0, 25.0),
        AnalyzedHolding(2, "B", "Fund B", "etf", "EUR", 100.0, 25.0),
        AnalyzedHolding(3, "C", "Vanguard Something", "etf", "EUR", 100.0, 25.0),
        AnalyzedHolding(4, "D", "Crypto", "crypto", "EUR", 100.0, 25.0),
    ]
    repo = _FakeRepo([], enrichment={1: {"ter": 0.1}}, metadata={2: _meta(0.003)})
    resolved = resolve_holding_ters(holdings, repo)
    assert resolved[1] == (0.1, "justetf")
    assert resolved[2][1] == "yfinance" and resolved[2][0] == pytest.approx(0.3)
    assert resolved[3] == (0.25, "inferred")
    assert resolved[4] == (None, "none")
    # (0.1 + 0.3 + 0.25) / 3 over covered weight
    assert compute_weighted_ter(holdings, repo) == pytest.approx(0.22)
