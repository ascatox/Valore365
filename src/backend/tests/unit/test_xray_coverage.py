"""TASK-48: X-Ray coverage with explicit denominators, unclassified share, data dates."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app import copilot_tools
from app.finance_client import ProviderEtfHolding
from app.services.portfolio_doctor import _xray
from app.services.portfolio_doctor._holdings import AnalyzedHolding

UNCLASSIFIED = _xray.UNCLASSIFIED_LABEL


def _h(asset_id, symbol, name, asset_type, weight, **extra) -> AnalyzedHolding:
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type,
        quote_currency="EUR", market_value=weight * 100.0, weight_pct=weight, **extra,
    )


def _top10_summing(total: float) -> list[dict]:
    each = total / 10
    return [{"name": f"Co{i}", "isin": f"US{i:04d}", "percentage": each} for i in range(10)]


class _Repo:
    def __init__(self, enrichment=None, metadata=None):
        self._enrichment = enrichment or {}
        self._metadata = metadata or {}

    def get_etf_enrichment_bulk(self, ids):
        return {aid: v for aid, v in self._enrichment.items() if aid in ids}

    def get_asset_pricing_symbols(self, ids, provider):
        return {}

    def get_asset_metadata_bulk(self, ids):
        return {aid: v for aid, v in self._metadata.items() if aid in ids}


@pytest.fixture(autouse=True)
def _clear_cache():
    _xray._top_holdings_cache.clear()
    yield
    _xray._top_holdings_cache.clear()


def _run(monkeypatch, holdings, repo, yahoo=None):
    monkeypatch.setattr(_xray, "_load_holdings", lambda r, scope, user_id: holdings)
    yahoo = yahoo or {}
    finance = SimpleNamespace(get_etf_top_holdings=lambda symbol: yahoo.get(symbol, []))
    return _xray.compute_portfolio_xray(repo, 1, "u", finance, None)


def _assert_sums_to_100(dist: dict[str, float]):
    assert abs(sum(dist.values()) - 100.0) <= 0.1, dist


# --- coverage math ----------------------------------------------------------------


def test_fund_with_top10_at_45pct_and_half_weight_contributes_22_5(monkeypatch):
    holdings = [
        _h(1, "WRLD", "World Equity ETF", "etf", 50.0),
        _h(2, "NOPE", "Other Equity ETF", "etf", 50.0),
    ]
    repo = _Repo(enrichment={1: {"top_holdings": _top10_summing(45.0), "fetched_at": "2026-10-01T08:00:00+00:00"}})

    out = _run(monkeypatch, holdings, repo)

    assert out.lookthrough_coverage_pct == pytest.approx(22.5, abs=0.05)
    assert out.funds_with_holdings_pct == pytest.approx(50.0)
    # Legacy field unchanged in meaning: weight of funds with some top holdings.
    assert out.coverage_pct == 50.0
    assert "liquidità" in out.coverage_denominator.lower()
    assert "22" in out.coverage_note
    detail = next(d for d in out.etf_details if d.symbol == "WRLD")
    assert detail.listed_holdings_pct == pytest.approx(45.0)


def test_direct_single_stock_counts_as_fully_looked_through(monkeypatch):
    holdings = [
        _h(1, "WRLD", "World Equity ETF", "etf", 50.0),
        _h(3, "AAPL", "Apple Inc", "stock", 50.0),
    ]
    repo = _Repo(enrichment={1: {"top_holdings": _top10_summing(40.0)}})

    out = _run(monkeypatch, holdings, repo)

    # 50 x 40% + 50 (the stock is its own underlying holding).
    assert out.lookthrough_coverage_pct == pytest.approx(70.0, abs=0.05)
    stock = next(d for d in out.etf_details if d.symbol == "AAPL")
    assert stock.lookthrough_kind == "direct_stock"


def test_yahoo_fractions_are_used_for_the_listed_share(monkeypatch):
    holdings = [_h(1, "VWCE.DE", "Vanguard FTSE All-World", "etf", 100.0)]
    yahoo = {"VWCE.DE": [ProviderEtfHolding(symbol="AAPL", name="Apple", weight=0.05),
                         ProviderEtfHolding(symbol="MSFT", name="Microsoft", weight=0.05)]}

    out = _run(monkeypatch, holdings, _Repo(), yahoo)

    assert out.lookthrough_coverage_pct == pytest.approx(10.0, abs=0.05)
    detail = out.etf_details[0]
    assert detail.data_source == "yahoo"
    assert detail.data_as_of == datetime.now(timezone.utc).date().isoformat()
    assert detail.data_as_of_basis == "fetch_time"


# --- distributions sum to 100 ------------------------------------------------------


def test_distributions_sum_to_100_with_an_unclassified_bucket(monkeypatch):
    holdings = [
        _h(1, "WRLD", "World Equity ETF", "etf", 60.0),
        _h(2, "NOPE", "Other Equity ETF", "etf", 40.0),
    ]
    repo = _Repo(enrichment={1: {
        "top_holdings": _top10_summing(20.0),
        # Only 90% of the fund's countries listed, 100% of sectors.
        "country_weights": [{"name": "United States", "percentage": 60.0},
                            {"name": "Japan", "percentage": 30.0}],
        "sector_weights": [{"name": "Technology", "percentage": 100.0}],
    }})

    out = _run(monkeypatch, holdings, repo)

    countries = out.aggregated_country_exposure
    sectors = out.aggregated_sector_exposure
    _assert_sums_to_100(countries)
    _assert_sums_to_100(sectors)
    assert countries["United States"] == pytest.approx(36.0)
    assert countries[UNCLASSIFIED] == pytest.approx(40.0 + 6.0)
    assert sectors[UNCLASSIFIED] == pytest.approx(40.0)
    assert out.classified_country_pct == pytest.approx(54.0)
    assert out.classified_sector_pct == pytest.approx(60.0)
    assert out.unclassified_country_pct == pytest.approx(46.0)


def test_gold_and_bond_are_labelled_by_asset_class_not_missing(monkeypatch):
    holdings = [
        _h(1, "WRLD", "World Equity ETF", "etf", 50.0),
        _h(7, "XAD1.DE", "Xtrackers IE Physical Gold ETC", "stock", 20.0),
        _h(8, "AGGH", "iShares Core Global Aggregate Bond UCITS ETF", "etf", 30.0),
    ]
    repo = _Repo(enrichment={
        1: {"country_weights": [{"name": "United States", "percentage": 100.0}],
            "sector_weights": [{"name": "Technology", "percentage": 100.0}]},
        # A bond fund with countries but no sectors.
        8: {"country_weights": [{"name": "Germany", "percentage": 100.0}]},
    })

    out = _run(monkeypatch, holdings, repo)

    countries = out.aggregated_country_exposure
    sectors = out.aggregated_sector_exposure
    _assert_sums_to_100(countries)
    _assert_sums_to_100(sectors)
    gold_label = _xray.ASSET_CLASS_BUCKET_LABELS["gold"]
    bond_label = _xray.ASSET_CLASS_BUCKET_LABELS["bond"]
    assert countries[gold_label] == pytest.approx(20.0)
    assert countries["Germany"] == pytest.approx(30.0)
    assert sectors[gold_label] == pytest.approx(20.0)
    assert sectors[bond_label] == pytest.approx(30.0)
    assert UNCLASSIFIED not in sectors
    gold = next(d for d in out.etf_details if d.symbol == "XAD1.DE")
    assert gold.lookthrough_kind == "no_lookthrough"


def test_cash_positions_are_excluded_from_the_denominator(monkeypatch):
    holdings = [
        _h(1, "WRLD", "World Equity ETF", "etf", 80.0),
        _h(9, "EUR", "Cash", "cash", 20.0),
    ]
    repo = _Repo(enrichment={1: {"top_holdings": _top10_summing(50.0),
                                 "country_weights": [{"name": "United States", "percentage": 100.0}]}})

    out = _run(monkeypatch, holdings, repo)

    assert out.lookthrough_coverage_pct == pytest.approx(50.0, abs=0.05)
    assert out.funds_with_holdings_pct == pytest.approx(100.0)
    assert out.aggregated_country_exposure["United States"] == pytest.approx(100.0)
    _assert_sums_to_100(out.aggregated_sector_exposure)


def test_direct_stock_uses_metadata_country_and_sector(monkeypatch):
    holdings = [_h(3, "AAPL", "Apple Inc", "stock", 100.0)]
    meta = {3: SimpleNamespace(country="United States", sector="Technology")}

    out = _run(monkeypatch, holdings, _Repo(metadata=meta))

    assert out.aggregated_country_exposure == {"United States": 100.0}
    assert out.aggregated_sector_exposure == {"Technology": 100.0}


# --- missing data and reference date ----------------------------------------------


def test_missing_data_gives_zero_coverage_and_all_unclassified(monkeypatch):
    holdings = [_h(1, "WRLD", "World Equity ETF", "etf", 100.0)]

    out = _run(monkeypatch, holdings, _Repo())

    assert out.lookthrough_coverage_pct == 0.0
    assert out.funds_with_holdings_pct == 0.0
    assert out.aggregated_country_exposure == {UNCLASSIFIED: 100.0}
    assert out.data_as_of is None
    assert out.etf_details[0].data_source == "none"
    assert out.etf_details[0].data_as_of is None


def test_data_as_of_is_the_oldest_provider_date(monkeypatch):
    holdings = [
        _h(1, "AAA", "AAA Equity ETF", "etf", 50.0),
        _h(2, "BBB", "BBB Equity ETF", "etf", 50.0),
    ]
    repo = _Repo(enrichment={
        1: {"top_holdings": _top10_summing(30.0), "holdings_date": "30.09.2026",
            "fetched_at": "2026-10-20T08:00:00+00:00"},
        2: {"top_holdings": _top10_summing(30.0), "holdings_date": "not a date",
            "fetched_at": "2026-10-15T08:00:00+00:00"},
    })

    out = _run(monkeypatch, holdings, repo)

    by_symbol = {d.symbol: d for d in out.etf_details}
    assert by_symbol["AAA"].data_as_of == "2026-09-30"
    assert by_symbol["AAA"].data_as_of_basis == "holdings_date"
    assert by_symbol["AAA"].data_source == "justetf"
    assert by_symbol["BBB"].data_as_of == "2026-10-15"
    assert by_symbol["BBB"].data_as_of_basis == "fetched_at"
    assert out.data_as_of == "2026-09-30"


def test_the_cache_reports_when_a_symbol_was_fetched():
    cache = _xray._TopHoldingsCache(ttl_seconds=60.0, max_entries=8)
    before = datetime.now(timezone.utc).timestamp()
    result, fetched_at = cache.get_or_fetch_timed("VWCE", lambda: [1])
    again, fetched_again = cache.get_or_fetch_timed("VWCE", lambda: [2])
    assert result == again == [1]
    assert fetched_at == fetched_again
    assert fetched_at >= before - 1


# --- copilot / MCP output -------------------------------------------------------------


def test_copilot_and_mcp_summary_expose_coverage_and_dates(monkeypatch):
    holdings = [_h(1, "AAA", "AAA Equity ETF", "etf", 50.0), _h(2, "BBB", "BBB Equity ETF", "etf", 50.0)]
    monkeypatch.setattr(_xray, "_load_holdings", lambda r, scope, user_id: holdings)
    countries = [{"name": f"C{i:02d}", "percentage": 7.0} for i in range(14)]  # 98%
    repo = _Repo(enrichment={1: {"top_holdings": _top10_summing(45.0), "country_weights": countries,
                                 "holdings_date": "2026-09-30"}})
    finance = SimpleNamespace(get_etf_top_holdings=lambda symbol: [])

    out = copilot_tools._get_xray_summary({}, repo, MagicMock(), 1, "u", finance_client=finance)

    assert out["lookthrough_coverage_pct"] == pytest.approx(22.5, abs=0.05)
    assert out["funds_with_holdings_pct"] == 50.0
    assert out["coverage_pct"] == 50.0
    assert "classified_country_pct" in out and "classified_sector_pct" in out
    assert out["coverage_denominator"] and out["coverage_note"]
    assert out["data_as_of"] == "2026-09-30"
    # Truncated lists still add up to 100 (rest grouped, unclassified explicit).
    _assert_sums_to_100(out["geographic_exposure"])
    _assert_sums_to_100(out["sector_exposure"])
    assert UNCLASSIFIED in out["geographic_exposure"]
    assert any(f["symbol"] == "AAA" and f["source"] == "justetf" and f["data_as_of"] == "2026-09-30"
               for f in out["funds"])
