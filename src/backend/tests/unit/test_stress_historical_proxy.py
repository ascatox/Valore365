"""TASK-38 / V365-001: historical stress scenarios depend on the portfolio.

No more ``benchmark_drawdown * 0.8`` when prices are missing: with at least
60% of the weight covered by real prices in the window the scenario is
"historical" (uncovered part filled with class proxies), below it the whole
scenario uses ``sum(weight x class proxy)``.

Synthetic instruments only.
"""

from __future__ import annotations

from datetime import date

import pytest

from app.constants.stress_scenarios import (
    HISTORICAL_CLASS_PROXIES,
    HISTORICAL_MIN_COVERAGE_PCT,
    HISTORICAL_SCENARIOS,
)
from app.services.portfolio_doctor import AnalyzedHolding
from app.services.portfolio_doctor._holdings import holding_asset_class
from app.services.portfolio_doctor._stress import (
    HISTORICAL_PROXY_METHODOLOGY_NOTE,
    _compute_historical_scenario,
)

CLASSES = ("equity", "bond", "gold", "commodity", "cash", "crypto")


def _h(asset_id, symbol, name, asset_type, weight, **extra) -> AnalyzedHolding:
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type,
        quote_currency="USD", market_value=weight * 100.0, weight_pct=weight, **extra,
    )


class _PriceRepo:
    """Fake repo answering the price_bars_1d query from in-memory rows."""

    def __init__(self, rows: list[dict] | None = None):
        rows = rows or []

        class _Result:
            def __init__(self, data):
                self._data = data

            def mappings(self):
                return self

            def all(self):
                return self._data

        class _Conn:
            def execute(self, _sql, params):
                ids = set(params["asset_ids"])
                data = [
                    r for r in rows
                    if r["asset_id"] in ids
                    and params["start_date"] <= r["price_date"] <= params.get("end_date", date.max)
                ]
                return _Result(sorted(data, key=lambda r: (r["asset_id"], r["price_date"])))

        class _Begin:
            def __enter__(self):
                return _Conn()

            def __exit__(self, *exc):
                return False

        class _Engine:
            @staticmethod
            def begin():
                return _Begin()

        self.engine = _Engine()


def _scenario(scenario_id):
    return next(s for s in HISTORICAL_SCENARIOS if s["id"] == scenario_id)


def _proxy(scenario_id, cls):
    return HISTORICAL_CLASS_PROXIES[scenario_id][cls]


EQUITY = ("VTI", "Vanguard Total Stock Market ETF", "etf")
LONG_BOND = ("TLT", "iShares 20+ Year Treasury Bond ETF", "etf")
MID_BOND = ("IEF", "iShares 7-10 Year Treasury Bond ETF", "etf")
COMMODITY = ("DJP", "iPath Bloomberg Commodity Index Total Return ETN", "etf")
GOLD = ("GLD", "SPDR Gold Shares", "etf")


def _portfolio(*parts):
    return [_h(i + 1, sym, name, atype, weight) for i, ((sym, name, atype), weight) in enumerate(parts)]


ARCHETYPES = {
    "all_equity": _portfolio((EQUITY, 100)),
    "all_bond": _portfolio((LONG_BOND, 100)),
    "sixty_forty": _portfolio((EQUITY, 60), (MID_BOND, 40)),
    "all_weather": _portfolio((EQUITY, 30), (LONG_BOND, 40), (MID_BOND, 15), (COMMODITY, 7.5), (GOLD, 7.5)),
}


def _expected_proxy_impact(holdings, scenario_id):
    total = sum(h.weight_pct for h in holdings)
    return sum(h.weight_pct * _proxy(scenario_id, holding_asset_class(h)) for h in holdings) / total


# --- proxy table ----------------------------------------------------------------


def test_every_historical_scenario_has_a_proxy_for_every_class():
    for scenario in HISTORICAL_SCENARIOS:
        assert set(CLASSES) <= set(HISTORICAL_CLASS_PROXIES[scenario["id"]]), scenario["id"]
        assert HISTORICAL_CLASS_PROXIES[scenario["id"]]["cash"] == 0.0
    assert HISTORICAL_MIN_COVERAGE_PCT == 60.0


def test_archetype_instruments_are_classified_as_expected():
    classes = {h.symbol: holding_asset_class(h) for h in ARCHETYPES["all_weather"]}
    assert classes == {"VTI": "equity", "TLT": "bond", "IEF": "bond", "DJP": "commodity", "GLD": "gold"}


# --- proxy method (no price history) --------------------------------------------


@pytest.mark.parametrize("scenario_id", [s["id"] for s in HISTORICAL_SCENARIOS])
def test_archetypes_without_history_use_class_proxies_and_differ(scenario_id):
    impacts = {}
    for label, holdings in ARCHETYPES.items():
        result = _compute_historical_scenario(_PriceRepo(), holdings, _scenario(scenario_id))
        assert result.method == "proxy", label
        assert result.coverage_pct == 0.0
        expected = _expected_proxy_impact(holdings, scenario_id)
        assert result.estimated_portfolio_impact_pct == pytest.approx(expected, abs=0.01), label
        # contributions add up to the impact and every row is a proxy row
        assert sum(r.contribution_pct for r in result.class_breakdown) == pytest.approx(
            result.estimated_portfolio_impact_pct, abs=0.02
        )
        assert {r.source for r in result.class_breakdown} == {"proxy"}
        # never the old portfolio-independent fallback
        assert result.estimated_portfolio_impact_pct != pytest.approx(
            _scenario(scenario_id)["benchmark_drawdown"] * 0.8
        )
        impacts[label] = result.estimated_portfolio_impact_pct
    assert len(set(impacts.values())) == len(impacts), impacts


def test_sixty_forty_proxy_is_the_weighted_sum_of_class_drawdowns():
    result = _compute_historical_scenario(_PriceRepo(), ARCHETYPES["sixty_forty"], _scenario("bear_market_2022"))

    expected = 0.6 * _proxy("bear_market_2022", "equity") + 0.4 * _proxy("bear_market_2022", "bond")
    assert result.estimated_portfolio_impact_pct == pytest.approx(expected, abs=0.01)
    rows = {r.asset_class: r for r in result.class_breakdown}
    assert rows["equity"].weight_pct == 60
    assert rows["equity"].drawdown_pct == _proxy("bear_market_2022", "equity")
    assert rows["bond"].contribution_pct == pytest.approx(0.4 * _proxy("bear_market_2022", "bond"), abs=0.01)
    assert "class_proxy_drawdowns" in result.flags
    assert result.methodology_note == HISTORICAL_PROXY_METHODOLOGY_NOTE
    assert "USD" in result.methodology_note and "EUR/USD" in result.methodology_note


def test_empty_portfolio_is_not_available():
    result = _compute_historical_scenario(_PriceRepo(), [], _scenario("gfc_2008"))

    assert result.method == "not_available"
    assert result.estimated_portfolio_impact_pct == 0.0
    assert result.class_breakdown == []
    assert result.coverage_pct is None
    assert result.methodology_note is None


def test_crypto_before_inception_and_unknown_take_equity_proxy_with_flags():
    holdings = [
        _h(1, "BTC", "Bitcoin", "crypto", 50),
        _h(2, "TRKN", "Some Issuer Tracker ETN", "stock", 50),
    ]
    assert holding_asset_class(holdings[1]) == "unknown"

    result = _compute_historical_scenario(_PriceRepo(), holdings, _scenario("gfc_2008"))

    assert result.method == "proxy"
    assert result.estimated_portfolio_impact_pct == pytest.approx(_proxy("gfc_2008", "equity"), abs=0.01)
    assert "crypto_pre_inception_equity_proxy" in result.flags
    assert "unknown_asset_class_equity_proxy" in result.flags
    rows = {r.asset_class: r for r in result.class_breakdown}
    assert rows["crypto"].drawdown_pct == _proxy("gfc_2008", "equity")
    assert rows["unknown"].drawdown_pct == _proxy("gfc_2008", "equity")

    covid = _compute_historical_scenario(_PriceRepo(), holdings[:1], _scenario("covid_crash"))
    assert covid.estimated_portfolio_impact_pct == pytest.approx(_proxy("covid_crash", "crypto"), abs=0.01)
    assert "crypto_pre_inception_equity_proxy" not in covid.flags


# --- partial coverage -----------------------------------------------------------


def _covid_rows(asset_id, first, last):
    return [
        {"asset_id": asset_id, "price_date": date(2020, 2, 19), "close": first},
        {"asset_id": asset_id, "price_date": date(2020, 3, 23), "close": last},
    ]


def test_coverage_above_threshold_is_historical_with_proxy_filled_remainder():
    holdings = _portfolio((EQUITY, 70), (LONG_BOND, 30))
    repo = _PriceRepo(_covid_rows(1, 100.0, 60.0))  # equity -40% real

    result = _compute_historical_scenario(repo, holdings, _scenario("covid_crash"))

    assert result.method == "historical"
    assert result.coverage_pct == 70.0
    expected = 0.7 * -40.0 + 0.3 * _proxy("covid_crash", "bond")
    assert result.estimated_portfolio_impact_pct == pytest.approx(expected, abs=0.01)
    rows = {(r.asset_class, r.source): r for r in result.class_breakdown}
    assert rows[("equity", "historical")].drawdown_pct == -40.0
    assert rows[("bond", "proxy")].drawdown_pct == _proxy("covid_crash", "bond")
    assert "uncovered_weight_filled_with_class_proxy" in result.flags
    assert result.methodology_note == HISTORICAL_PROXY_METHODOLOGY_NOTE
    assert result.max_drawdown_pct <= result.estimated_portfolio_impact_pct


def test_cash_counts_as_covered_with_zero_return():
    holdings = [
        _h(1, "VTI", "Vanguard Total Stock Market ETF", "etf", 50),
        _h(2, "CASH", "Cash", "cash", 50),
    ]
    result = _compute_historical_scenario(_PriceRepo(_covid_rows(1, 100.0, 80.0)), holdings, _scenario("covid_crash"))

    assert result.method == "historical"
    assert result.coverage_pct == 100.0
    assert result.estimated_portfolio_impact_pct == -10.0
    assert result.flags == []
    assert result.methodology_note is None


def test_coverage_below_threshold_switches_to_proxy():
    holdings = _portfolio((EQUITY, 50), (LONG_BOND, 50))
    repo = _PriceRepo(_covid_rows(1, 100.0, 60.0))

    result = _compute_historical_scenario(repo, holdings, _scenario("covid_crash"))

    assert result.method == "proxy"
    assert result.coverage_pct == 50.0
    expected = 0.5 * _proxy("covid_crash", "equity") + 0.5 * _proxy("covid_crash", "bond")
    assert result.estimated_portfolio_impact_pct == pytest.approx(expected, abs=0.01)
    assert {r.source for r in result.class_breakdown} == {"proxy"}


# --- MCP output -----------------------------------------------------------------


def test_mcp_stress_output_exposes_method_coverage_and_class_sources(monkeypatch):
    from app import copilot_tools
    from app.schemas.portfolio_doctor import StressTestResponse

    holdings = _portfolio((EQUITY, 70), (LONG_BOND, 30))
    scenario = _compute_historical_scenario(
        _PriceRepo(_covid_rows(1, 100.0, 60.0)), holdings, _scenario("covid_crash")
    )
    monkeypatch.setattr(
        copilot_tools, "run_stress_test",
        lambda repo, pid, uid: StressTestResponse(portfolio_id=1, scenarios=[scenario], analysis_date="2026-11-02"),
    )

    data = copilot_tools._get_stress_test({}, None, None, 1, "user")["scenarios"][0]

    assert data["method"] == "historical"
    assert data["coverage_pct"] == 70.0
    assert "uncovered_weight_filled_with_class_proxy" in data["flags"]
    assert data["methodology_note"] == HISTORICAL_PROXY_METHODOLOGY_NOTE
    sources = {(r["asset_class"], r["source"]) for r in data["class_breakdown"]}
    assert sources == {("equity", "historical"), ("bond", "proxy")}
    assert all("drawdown_pct" in r and "contribution_pct" in r for r in data["class_breakdown"])


def test_mcp_stress_output_omits_methodology_note_for_fully_historical(monkeypatch):
    from app import copilot_tools
    from app.schemas.portfolio_doctor import StressTestResponse

    holdings = [
        _h(1, "VTI", "Vanguard Total Stock Market ETF", "etf", 50),
        _h(2, "CASH", "Cash", "cash", 50),
    ]
    scenario = _compute_historical_scenario(
        _PriceRepo(_covid_rows(1, 100.0, 80.0)), holdings, _scenario("covid_crash")
    )
    monkeypatch.setattr(
        copilot_tools, "run_stress_test",
        lambda repo, pid, uid: StressTestResponse(portfolio_id=1, scenarios=[scenario], analysis_date="2026-11-02"),
    )

    data = copilot_tools._get_stress_test({}, None, None, 1, "user")["scenarios"][0]

    assert data["method"] == "historical"
    assert "methodology_note" not in data
