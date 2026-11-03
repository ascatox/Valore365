"""TASK-35 / V365-002, V365-012: one asset-class classifier for every consumer.

Synthetic instruments only.
"""

from __future__ import annotations

import pytest

from app.constants.stress_scenarios import SHOCK_SCENARIOS
from app.finance_client import resolve_refreshed_asset_type
from app.services.asset_classification import ASSET_CLASSES, classify_asset, classify_asset_class
from app.services.instant_portfolio_analyzer import map_asset_class
from app.services.portfolio_doctor import (
    AnalyzedHolding,
    compute_geographic_exposure,
    compute_max_single_security_weight,
)
from app.services.portfolio_doctor._health import infer_ter, resolve_holding_ters
from app.services.portfolio_doctor._holdings import _asset_class, _is_equity_like
from app.services.portfolio_doctor._stress import _compute_shock_scenario, _shock_asset_class


def _h(asset_id, symbol, name, asset_type, weight, **extra) -> AnalyzedHolding:
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type,
        quote_currency=extra.pop("quote_currency", "EUR"),
        market_value=weight * 100.0, weight_pct=weight, **extra,
    )


# --- classifier -------------------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        # ETF equity
        ({"asset_type": "etf", "name": "Vanguard FTSE All-World UCITS ETF", "symbol": "VWCE.DE"}, "equity"),
        ({"asset_type": "etf", "name": "iShares Core MSCI World", "symbol": "SWDA.MI"}, "equity"),
        # ETF bond (by name, and name-less with enrichment)
        ({"asset_type": "etf", "name": "iShares Core Global Aggregate Bond UCITS ETF", "symbol": "AGGH"}, "bond"),
        ({"asset_type": "etf", "name": "TLT", "symbol": "TLT", "category": "Long Government"}, "bond"),
        ({"asset_type": "etf", "name": "ZZZ1", "symbol": "ZZZ1", "investment_focus": "Bonds, EUR, Government"}, "bond"),
        ({"asset_type": "etf", "name": "TLT", "symbol": "TLT"}, "bond"),
        # gold ETC typed stock (QUOTE_TYPE_MAP EQUITY -> stock)
        ({"asset_type": "stock", "name": "Xtrackers IE Physical Gold ETC", "symbol": "XAD1.DE"}, "gold"),
        ({"asset_type": "stock", "name": "XAD1.DE", "symbol": "XAD1.DE", "isin": "DE000A1EK0G3"}, "gold"),
        ({"asset_type": "stock", "name": "ABCD", "symbol": "ABCD", "isin": "DE000A1EK0G3"}, "gold"),
        ({"asset_type": "etf", "name": "QQQQ", "symbol": "QQQQ", "investment_focus": "Precious Metals, Gold"}, "gold"),
        # ETN / commodity
        ({"asset_type": "stock", "name": "WisdomTree Brent Crude Oil ETN", "symbol": "BRNT.MI"}, "commodity"),
        ({"asset_type": "etf", "name": "iShares Diversified Commodity Swap", "symbol": "ICOM"}, "commodity"),
        ({"asset_type": "stock", "name": "Some Issuer Tracker ETN", "symbol": "TRKN"}, "unknown"),
        # gold miners are equity, not gold
        ({"asset_type": "etf", "name": "VanEck Gold Miners UCITS ETF", "symbol": "GDX"}, "equity"),
        # direct bond / stock / crypto / cash
        ({"asset_type": "bond", "name": "BTP 2033", "symbol": "IT0005"}, "bond"),
        ({"asset_type": "stock", "name": "Apple Inc", "symbol": "AAPL"}, "equity"),
        ({"asset_type": "stock", "name": "Barrick Gold Corp", "symbol": "GOLD"}, "equity"),
        ({"asset_type": "crypto", "name": "Bitcoin", "symbol": "BTC-EUR"}, "crypto"),
        ({"asset_type": "cash", "name": "Liquidità", "symbol": "CASH"}, "cash"),
        # unknown: never silently equity
        ({"asset_type": "etf", "name": "QWERTY", "symbol": "QWERTY"}, "unknown"),
        ({"asset_type": "fund", "name": "", "symbol": "F123"}, "unknown"),
    ],
)
def test_classify_asset(kwargs, expected):
    assert classify_asset_class(**kwargs) == expected


def test_classification_reports_source_and_product_flag():
    gold = classify_asset(asset_type="stock", name="Xtrackers IE Physical Gold ETC", symbol="XAD1.DE")
    assert gold.source == "name"
    assert gold.is_exchange_traded_product is True
    stock = classify_asset(asset_type="stock", name="Apple Inc", symbol="AAPL")
    assert (stock.source, stock.is_exchange_traded_product) == ("default", False)
    assert set(ASSET_CLASSES) >= {"equity", "bond", "gold", "commodity", "cash", "crypto", "unknown"}


def test_holdings_consumers_use_the_shared_classifier():
    gold = _h(1, "XAD1.DE", "Xtrackers IE Physical Gold ETC", "stock", 10)
    tlt = _h(2, "TLT", "TLT", "etf", 10, investment_focus="Bonds, USD, Treasury, 20+")
    unknown = _h(3, "QWERTY", "QWERTY", "etf", 10)

    assert _shock_asset_class(gold) == "gold"
    assert _shock_asset_class(tlt) == "bond"
    assert _shock_asset_class(unknown) == "unknown"
    # long-term assumptions keep their 4 classes: gold -> commodity
    assert _asset_class(gold) == "commodity"
    assert _asset_class(tlt) == "bond"
    # health: bond ETF and gold ETC are not equity, unknown is not equity either
    assert not _is_equity_like(gold)
    assert not _is_equity_like(tlt)
    assert not _is_equity_like(unknown)
    assert _is_equity_like(_h(4, "VWCE", "Vanguard FTSE All-World", "etf", 10))


def test_instant_analyzer_delegates_to_the_classifier():
    assert map_asset_class("etf", "VanEck Gold Miners UCITS ETF", "GDX") == "Equity"
    assert map_asset_class("stock", "Xtrackers IE Physical Gold ETC", "XAD1") == "Gold"
    assert map_asset_class("etf", "iShares Core Global Aggregate Bond", "AGGH") == "Bond"
    assert map_asset_class("cash", "Cash", "CASH") == "Cash"


# --- health: gold ETC typed stock -----------------------------------------------


def test_gold_etc_typed_stock_is_not_a_single_stock_with_zero_ter():
    gold = _h(1, "XAD1.DE", "Xtrackers IE Physical Gold ETC", "stock", 30)
    apple = _h(2, "AAPL", "Apple Inc", "stock", 20, quote_currency="USD")

    assert infer_ter(gold) != 0.0
    assert infer_ter(apple) == 0.0
    ter, source = resolve_holding_ters([gold])[1]
    assert ter != 0.0
    assert source in {"inferred", "none"}
    # not counted as a single company share
    assert compute_max_single_security_weight([gold, apple]) == 20.0
    # a commodity has no country: not "europe" because it trades in EUR
    exposure = compute_geographic_exposure([gold])
    assert exposure.get("europe", 0.0) == 0.0


def test_bond_etf_typed_stock_gets_no_zero_ter():
    bond_like = _h(1, "IHYG", "iShares EUR High Yield Corp Bond UCITS ETF", "stock", 10)
    assert infer_ter(bond_like) != 0.0
    direct_bond = _h(2, "BTP33", "BTP 2033", "bond", 10)
    assert infer_ter(direct_bond) == 0.0


# --- stress ---------------------------------------------------------------------


def _scenario(scenario_id):
    return next(s for s in SHOCK_SCENARIOS if s["id"] == scenario_id)


def test_every_shock_scenario_declares_non_equity_classes():
    for scenario in SHOCK_SCENARIOS:
        assert {"equity", "bond", "gold", "commodity", "cash", "crypto"} <= set(scenario["shocks"]), scenario["id"]


def _all_weather():
    return [
        _h(1, "VWCE", "Vanguard FTSE All-World UCITS ETF", "etf", 30),
        _h(2, "TLT", "TLT", "etf", 40, investment_focus="Bonds, USD, Treasury, 20+"),
        _h(3, "IEF", "iShares 7-10 Year Treasury Bond", "etf", 15),
        _h(4, "XAD1.DE", "Xtrackers IE Physical Gold ETC", "stock", 7.5),
        _h(5, "CMOD", "Invesco Bloomberg Commodity UCITS ETF", "etf", 7.5),
    ]


def test_tech_crash_does_not_hit_bonds_and_gold_with_the_equity_shock():
    result = _compute_shock_scenario(_all_weather(), _scenario("us_tech_crash"))

    by_class = {row.asset_class: row for row in result.class_breakdown}
    equity_shock = _scenario("us_tech_crash")["shocks"]["equity"] * 100
    for cls in ("bond", "gold", "commodity"):
        assert by_class[cls].shock_pct > equity_shock, cls
    assert by_class["bond"].shock_pct >= 0
    assert by_class["gold"].shock_pct >= 0
    # contributions add up to the portfolio impact
    total = sum(row.contribution_pct for row in result.class_breakdown)
    assert total == pytest.approx(result.estimated_portfolio_impact_pct, abs=0.02)
    assert by_class["equity"].contribution_pct == pytest.approx(30 * equity_shock / 100, abs=0.01)
    # gold has a 0% shock in this scenario, so it is held but not affected
    assert set(result.affected_classes) == {"equity", "bond", "commodity"}
    # the old equity fallback would have produced about -30% * 100
    assert result.estimated_portfolio_impact_pct > -15


def test_most_impacted_excludes_zero_and_positive_impacts_with_stable_ties():
    holdings = [
        _h(1, "BBB", "Vanguard FTSE All-World", "etf", 20),
        _h(2, "AAA", "iShares Core MSCI World", "etf", 20),
        _h(3, "TLT", "TLT", "etf", 40, investment_focus="Bonds, USD, Treasury"),
        _h(4, "CASH", "Liquidità", "cash", 20),
    ]
    result = _compute_shock_scenario(holdings, _scenario("us_tech_crash"))

    assert [a.symbol for a in result.most_impacted_assets] == ["AAA", "BBB"]
    assert all(a.estimated_loss_pct < 0 for a in result.most_impacted_assets)


def test_unknown_class_gets_the_equity_shock_with_an_explicit_flag():
    holdings = [_h(1, "QWERTY", "QWERTY", "etf", 100)]
    result = _compute_shock_scenario(holdings, _scenario("global_equity_crash"))

    row = result.class_breakdown[0]
    assert row.asset_class == "unknown"
    assert row.shock_pct == _scenario("global_equity_crash")["shocks"]["equity"] * 100
    assert "unknown_asset_class_equity_shock" in result.flags
    assert result.most_impacted_assets[0].asset_class == "unknown"


# --- price refresh does not downgrade etf -> stock -------------------------------


@pytest.mark.parametrize(
    "current, quote_type, expected",
    [
        ("etf", "EQUITY", "etf"),
        ("fund", "EQUITY", "fund"),
        ("etf", "WEIRD", "etf"),
        ("stock", "ETF", "etf"),
        ("stock", "EQUITY", "stock"),
        ("etf", "BOND", "etf"),
    ],
)
def test_refreshed_asset_type_never_downgrades_a_fund(current, quote_type, expected):
    assert resolve_refreshed_asset_type(current, quote_type) == expected


# --- X-Ray: commodities have no basket to look through ---------------------------


def test_xray_does_not_ask_yahoo_for_holdings_of_a_gold_etc(monkeypatch):
    from types import SimpleNamespace

    from app.services.portfolio_doctor import _xray

    gold = _h(7, "XAD1.DE", "Xtrackers IE Physical Gold ETC", "stock", 100)
    monkeypatch.setattr(_xray, "_load_holdings", lambda repo, scope, user_id: [gold])
    _xray._top_holdings_cache.clear()

    class _Repo:
        def get_etf_enrichment_bulk(self, ids):
            return {}

        def get_asset_pricing_symbols(self, ids, provider):
            return {}

    asked = []
    finance = SimpleNamespace(get_etf_top_holdings=lambda symbol: asked.append(symbol) or [])

    result = _xray.compute_portfolio_xray(_Repo(), 1, "user", finance, None)

    assert asked == []
    issue = result.coverage_issues[0]
    assert issue.symbol == "XAD1.DE"
    assert "gold" in issue.reason
    _xray._top_holdings_cache.clear()


# --- MCP stress output -----------------------------------------------------------


def test_mcp_stress_output_exposes_classes_shocks_and_contributions(monkeypatch):
    from app import copilot_tools
    from app.schemas.portfolio_doctor import StressTestResponse

    scenario = _compute_shock_scenario(_all_weather(), _scenario("us_tech_crash"))
    monkeypatch.setattr(
        copilot_tools, "run_stress_test",
        lambda repo, pid, uid: StressTestResponse(portfolio_id=1, scenarios=[scenario], analysis_date="2026-11-02"),
    )

    out = copilot_tools._get_stress_test({}, None, None, 1, "user")
    data = out["scenarios"][0]

    assert set(data["affected_classes"]) == {"equity", "bond", "commodity"}
    classes = {row["asset_class"]: row for row in data["class_breakdown"]}
    assert classes["gold"]["shock_pct"] == 0.0
    assert classes["bond"]["contribution_pct"] > 0
    assert all(item["loss_pct"] < 0 for item in data["most_impacted"])
    assert data["most_impacted"][0]["asset_class"] == "equity"


# --- TASK-36: income projection buckets ------------------------------------------


def _income_output(rows, *, tax_setting=None):
    """rows: (asset_id, symbol, name, asset_type, investment_focus, market_value, category, yield_pct)."""
    from types import SimpleNamespace

    from app import copilot_tools
    from app.models import AssetMetadataRead, Position

    positions = [
        Position(
            asset_id=aid, symbol=sym, name=name, asset_type=atype, quantity=1, avg_cost=mv,
            market_price=mv, market_value=mv, unrealized_pl=0, unrealized_pl_pct=0,
            weight=0, investment_focus=focus,
        )
        for aid, sym, name, atype, focus, mv, _cat, _y in rows
    ]
    metadata = {
        aid: AssetMetadataRead(asset_id=aid, category=cat, dividend_yield=y)
        for aid, _s, _n, _t, _f, _mv, cat, y in rows
        if cat is not None or y is not None
    }

    class _Repo:
        def get_positions(self, pid, uid):
            return positions

        def get_summary(self, pid, uid):
            return SimpleNamespace(market_value=sum(p.market_value for p in positions), cost_basis=10_000.0)

        def get_user_settings(self, uid):
            return SimpleNamespace(fire_capital_gains_tax_rate=tax_setting)

        def get_asset_metadata_bulk(self, ids):
            return {i: metadata[i] for i in ids if i in metadata}

        def get_asset_by_symbol(self, symbol):  # must not be used any more
            raise AssertionError("get_asset_by_symbol called")

    return copilot_tools._get_income_projection({}, _Repo(), None, 1, "user")


def test_income_projection_puts_bond_etfs_in_fixed_income():
    out = _income_output([
        # IHYG-like HY bond ETF, typed etf
        (1, "IHYG.MI", "iShares EUR High Yield Corp Bond UCITS ETF", "etf", None, 1000.0, None, 5.0),
        # FRC3-like inflation-linked bond ETF, name-less, enrichment only
        (2, "FRC3.DE", "FRC3.DE", "etf", "Bonds, EUR, Inflation-Linked", 1000.0, None, 2.0),
        # distributing equity ETF
        (3, "VHYL.MI", "Vanguard FTSE All-World High Dividend Yield", "etf", None, 1000.0, None, 3.0),
    ])

    assert out["fixed_income_annual_dividends_eur"] == 70.0
    assert out["equity_annual_dividends_eur"] == 30.0
    assert out["other_or_unknown_annual_dividends_eur"] == 0.0
    assert out["dividend_growth_fixed_income_pct"] == 0.0
    # no growth on fixed income: 3-year cumulative = 3 x 70 + equity with 3% growth
    three = next(p for p in out["projections"] if p["years"] == 3)
    expected = 70 * 3 + sum(30 * 1.03 ** y for y in (1, 2, 3))
    assert three["cumulative_gross_eur"] == pytest.approx(expected, abs=0.01)
    assert out["tax_rate_pct"] == 26.0
    assert "12,5%" in out["tax_note"]


def test_income_projection_unknown_and_missing_yield_are_explicit():
    out = _income_output([
        # accumulating equity fund without yield
        (1, "SWDA.MI", "iShares Core MSCI World UCITS ETF Acc", "etf", None, 5000.0, None, None),
        # bond ETF with metadata but no yield
        (2, "AGGH.MI", "AGGH.MI", "etf", None, 1000.0, "Global Bond", None),
        # unknown category with a yield: never equity by default
        (3, "QWERTY", "QWERTY", "fund", None, 1000.0, "Miscellaneous", 4.0),
        # plain dividend stock
        (4, "ENI.MI", "Eni SpA", "stock", None, 1000.0, None, 6.0),
    ])

    assert out["equity_annual_dividends_eur"] == 60.0
    assert out["fixed_income_annual_dividends_eur"] == 0.0
    assert out["other_or_unknown_annual_dividends_eur"] == 40.0
    assert out["unknown_class_symbols"] == ["QWERTY"]
    assert out["missing_yield_symbols"] == ["SWDA.MI", "AGGH.MI"]
    # invariant: buckets add up to the gross income
    assert (
        out["equity_annual_dividends_eur"]
        + out["fixed_income_annual_dividends_eur"]
        + out["other_or_unknown_annual_dividends_eur"]
    ) == pytest.approx(out["current_annual_dividends_gross_eur"], abs=0.01)
    one = next(p for p in out["projections"] if p["years"] == 1)
    assert one["cumulative_gross_eur"] == pytest.approx(60 * 1.03 + 40, abs=0.01)
