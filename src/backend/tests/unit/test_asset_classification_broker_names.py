"""TASK-50 / TASK-51 (retest MCP 2026-11-03, V365-002 and V365-012).

Broker (Fineco) abbreviated names, the justETF official name as a structured
source, and the classification fields of search_asset_info.
Synthetic data shaped like the retest instruments.
"""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app import copilot_tools
from app.api.routes_assets import register_assets_routes
from app.constants.stress_scenarios import SHOCK_SCENARIOS
from app.errors import AppError, ProviderError
from app.models import AssetMetadataRead, AssetRead, Position
from app.services.asset_classification import (
    _BOND_ABBREVIATIONS,
    _EQUITY_ABBREVIATIONS,
    classify_asset,
    classify_asset_class,
)
from app.services.instant_portfolio_analyzer import map_asset_class
from app.services.portfolio_doctor import _xray
from app.services.portfolio_doctor._holdings import (
    AnalyzedHolding,
    _holdings_from_positions,
    _is_equity_like,
    holding_classification,
)
from app.services.portfolio_doctor._stress import _compute_shock_scenario

DBXP = {"asset_type": "etf", "name": "XTR2 EGB13 1CC", "symbol": "DBXP.DE", "isin": "LU0290356871"}
VEUR = {"asset_type": "etf", "name": "Azioni Europa", "symbol": "VEUR"}
XAD1 = {"asset_type": "stock", "name": "GOLD/DB ETC 60", "symbol": "XAD1.DE", "isin": "DE000A1EK0G3"}


def _h(asset_id, symbol, name, asset_type, weight, **extra) -> AnalyzedHolding:
    return AnalyzedHolding(
        asset_id=asset_id, symbol=symbol, name=name, asset_type=asset_type,
        quote_currency="EUR", market_value=weight * 100.0, weight_pct=weight, **extra,
    )


def _dbxp(asset_id=1, weight=50.0, **extra):
    return _h(asset_id, DBXP["symbol"], DBXP["name"], "etf", weight, isin=DBXP["isin"], **extra)


def _veur(asset_id=2, weight=50.0, **extra):
    return _h(asset_id, VEUR["symbol"], VEUR["name"], "etf", weight, **extra)


# --- classifier --------------------------------------------------------------------


def test_retest_instruments_are_classified_with_a_declared_source():
    dbxp = classify_asset(**DBXP)
    assert (dbxp.asset_class, dbxp.source) == ("bond", "name_abbrev")
    veur = classify_asset(**VEUR)
    assert (veur.asset_class, veur.source) == ("equity", "name_abbrev")
    assert classify_asset_class(**XAD1) == "gold"


def test_enrichment_name_from_justetf_wins_over_the_broker_name():
    # Structured data first: the official name stored for the ISIN.
    result = classify_asset(
        **DBXP, enrichment_name="Xtrackers II Eurozone Government Bond 1-3 UCITS ETF 1C",
    )
    assert (result.asset_class, result.source) == ("bond", "enrichment_name")
    # investment_focus still comes before the name
    result = classify_asset(
        **VEUR, investment_focus="Equity, Europe", enrichment_name="Vanguard FTSE Developed Europe",
    )
    assert (result.asset_class, result.source) == ("equity", "enrichment")


@pytest.mark.parametrize(
    "name, expected",
    [
        # bond abbreviations
        ("XTR2 EGB13 1CC", "bond"),
        ("XTR EGB 1C", "bond"),
        ("ISH EUR GOVT BD 1-3", "bond"),
        ("AMUNDI EUR GOV 3-5", "bond"),
        ("SPDR US TREAS 1-3", "bond"),
        ("LYX US TSY 7-10", "bond"),
        ("ISH EUR CORP BD", "bond"),
        ("VANG GLB AGG HDG", "bond"),
        ("ETF Obbligazionario Euro", "bond"),
        ("Obblig. Governative 3-7", "bond"),
        ("Titoli di Stato Italia", "bond"),
        ("XTR EUR INFL 1C", "bond"),
        ("Govies Euro 1-3", "bond"),
        ("XTR II BUND", "bond"),
        # equity abbreviations
        ("Azioni Europa", "equity"),
        ("Azionario Paesi Emergenti", "equity"),
        ("XTR WRLD 1C", "equity"),
        ("ISH CORE SP500", "equity"),
        ("AMUNDI EQ EUROPE", "equity"),
        ("ISH STX 600", "equity"),
        # ambiguous or region only: never guessed
        ("Europa", "unknown"),
        ("Europe 1C", "unknown"),
        ("XTR EQ BD MIX", "unknown"),
        ("XTR2 1CC", "unknown"),
    ],
)
def test_broker_abbreviation_tables(name, expected):
    assert classify_asset_class(asset_type="etf", name=name, symbol="ZZZ") == expected


def test_abbreviation_tables_are_explicit_and_word_bounded():
    assert _BOND_ABBREVIATIONS and _EQUITY_ABBREVIATIONS
    # "Europa" / "Europe" are not equity cues on their own
    assert not any("europ" in pattern for pattern in _EQUITY_ABBREVIATIONS)
    # tokens embedded in other words do not match
    assert classify_asset_class(asset_type="etf", name="EGBERT FUND", symbol="ZZZ") == "unknown"
    assert classify_asset_class(asset_type="etf", name="GOVERNOR TRUST", symbol="ZZZ") == "unknown"


@pytest.mark.parametrize(
    "kwargs, expected",
    [
        # single shares: the name is not read, so abbreviations cannot misfire
        ({"asset_type": "stock", "name": "Barrick Gold Corp", "symbol": "GOLD"}, "equity"),
        ({"asset_type": "stock", "name": "Treasury Wine Estates", "symbol": "TWE.AX"}, "equity"),
        ({"asset_type": "stock", "name": "BD Bancorp", "symbol": "BDB"}, "equity"),
        ({"asset_type": "stock", "name": "Agg Industries", "symbol": "AGGI"}, "equity"),
        # full-name rules still come first
        ({"asset_type": "etf", "name": "iShares Core MSCI World", "symbol": "SWDA.MI"}, "equity"),
        ({"asset_type": "etf", "name": "VanEck Gold Miners UCITS ETF", "symbol": "GDX"}, "equity"),
        ({"asset_type": "etf", "name": "QWERTY", "symbol": "QWERTY"}, "unknown"),
    ],
)
def test_no_regression_on_existing_classifications(kwargs, expected):
    assert classify_asset_class(**kwargs) == expected


# --- instrument_type (TASK-51) ------------------------------------------------------


@pytest.mark.parametrize(
    "kwargs, asset_class, instrument_type",
    [
        (XAD1, "gold", "etc"),
        ({"asset_type": "stock", "name": "XAD1.DE", "symbol": "XAD1.DE", "isin": "DE000A1EK0G3"}, "gold", "etc"),
        ({"asset_type": "etf", "name": "Vanguard FTSE All-World UCITS ETF", "symbol": "VWCE.DE"}, "equity", "etf"),
        (DBXP, "bond", "etf"),
        ({"asset_type": "stock", "name": "WisdomTree Brent Crude Oil ETN", "symbol": "BRNT.MI"}, "commodity", "etn"),
        ({"asset_type": "stock", "name": "Apple Inc", "symbol": "AAPL"}, "equity", "stock"),
        ({"asset_type": "stock", "name": "iShares Core MSCI World UCITS ETF", "symbol": "SWDA"}, "equity", "etf"),
        ({"asset_type": "fund", "name": "Fondo Azionario Globale", "symbol": "F1"}, "equity", "fund"),
        ({"asset_type": "bond", "name": "BTP 2033", "symbol": "IT0005"}, "bond", "bond"),
        ({"asset_type": "cash", "name": "Liquidità", "symbol": "CASH"}, "cash", "cash"),
        ({"asset_type": "crypto", "name": "Bitcoin", "symbol": "BTC-EUR"}, "crypto", "crypto"),
        ({"asset_type": None, "name": "", "symbol": "ZZZ"}, "unknown", None),
    ],
)
def test_instrument_type(kwargs, asset_class, instrument_type):
    result = classify_asset(**kwargs)
    assert (result.asset_class, result.instrument_type) == (asset_class, instrument_type)


# --- consumers ------------------------------------------------------------------------


def _scenario(scenario_id):
    return next(s for s in SHOCK_SCENARIOS if s["id"] == scenario_id)


def test_stress_us_tech_crash_gives_dbxp_the_bond_shock():
    scenario = _scenario("us_tech_crash")
    result = _compute_shock_scenario([_dbxp(), _veur()], scenario)

    by_class = {row.asset_class: row for row in result.class_breakdown}
    assert set(by_class) == {"bond", "equity"}
    assert by_class["bond"].shock_pct == pytest.approx(scenario["shocks"]["bond"] * 100)
    assert by_class["equity"].shock_pct == pytest.approx(scenario["shocks"]["equity"] * 100)
    assert "unknown_asset_class_equity_shock" not in result.flags


def test_health_equity_weight_excludes_dbxp_and_includes_veur():
    assert not _is_equity_like(_dbxp())
    assert _is_equity_like(_veur())


def test_xray_puts_dbxp_in_the_bond_bucket(monkeypatch):
    holdings = [_dbxp(weight=40.0), _veur(weight=60.0)]
    monkeypatch.setattr(_xray, "_load_holdings", lambda r, scope, user_id: holdings)
    _xray._top_holdings_cache.clear()

    class _Repo:
        def get_etf_enrichment_bulk(self, ids):
            return {}

        def get_asset_pricing_symbols(self, ids, provider):
            return {}

        def get_asset_metadata_bulk(self, ids):
            return {}

    finance = SimpleNamespace(get_etf_top_holdings=lambda symbol: [])
    out = _xray.compute_portfolio_xray(_Repo(), 1, "u", finance, None)
    _xray._top_holdings_cache.clear()

    bond_label = _xray.ASSET_CLASS_BUCKET_LABELS["bond"]
    assert out.aggregated_country_exposure[bond_label] == pytest.approx(40.0)
    assert out.aggregated_sector_exposure[bond_label] == pytest.approx(40.0)


def _income(rows, inputs):
    positions = [
        Position(
            asset_id=aid, symbol=sym, name=name, asset_type=atype, quantity=1, avg_cost=mv,
            market_price=mv, market_value=mv, unrealized_pl=0, unrealized_pl_pct=0, weight=0,
        )
        for aid, sym, name, atype, mv, _y in rows
    ]
    metadata = {aid: AssetMetadataRead(asset_id=aid, dividend_yield=y) for aid, *_r, y in rows}

    class _Repo:
        engine = _FakeEngine(inputs)

        def get_positions(self, pid, uid):
            return positions

        def get_summary(self, pid, uid):
            return SimpleNamespace(market_value=sum(p.market_value for p in positions), cost_basis=1.0)

        def get_user_settings(self, uid):
            return SimpleNamespace(fire_capital_gains_tax_rate=None)

        def get_asset_metadata_bulk(self, ids):
            return {i: metadata[i] for i in ids if i in metadata}

    return copilot_tools._get_income_projection({}, _Repo(), None, 1, "user")


def test_income_projection_puts_dbxp_in_fixed_income():
    out = _income(
        [
            (1, "DBXP.DE", "XTR2 EGB13 1CC", "etf", 1000.0, 2.0),
            (2, "VEUR", "Azioni Europa", "etf", 1000.0, 3.0),
        ],
        inputs=[
            {"id": 1, "asset_type": "etf", "isin": "LU0290356871"},
            {"id": 2, "asset_type": "etf"},
        ],
    )
    assert out["fixed_income_annual_dividends_eur"] == 20.0
    assert out["equity_annual_dividends_eur"] == 30.0
    assert out["unknown_class_symbols"] == []


def test_income_projection_reads_the_enrichment_by_asset():
    # A broker name with no cue: the stored justETF data classifies it.
    out = _income(
        [(1, "ZZZ.DE", "XTR2 1CC", "etf", 1000.0, 2.0)],
        inputs=[{
            "id": 1, "asset_type": "etf", "isin": "LU0290356871",
            "enrichment_name": "Xtrackers II Eurozone Government Bond 1-3 UCITS ETF 1C",
        }],
    )
    assert out["fixed_income_annual_dividends_eur"] == 20.0


def test_instant_analyzer_maps_broker_names():
    assert map_asset_class("etf", "XTR2 EGB13 1CC", "DBXP.DE", "LU0290356871") == "Bond"
    assert map_asset_class("etf", "Azioni Europa", "VEUR") == "Equity"


# --- holdings loader: ISIN and enrichment reach the classifier ----------------------


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _FakeEngine:
    _COLUMNS = (
        "asset_type", "quote_currency", "isin", "category", "index_tracked",
        "investment_focus", "enrichment_name",
    )

    def __init__(self, rows):
        # Every column of the loader query, None unless given.
        self.rows = [{**dict.fromkeys(self._COLUMNS), **row} for row in rows]
        self.sql: list[str] = []

    @contextmanager
    def begin(self):
        engine = self

        class _Conn:
            def execute(self, statement, params):
                engine.sql.append(str(statement))
                return _FakeResult([r for r in engine.rows if r["id"] in params["asset_ids"]])

        yield _Conn()


def test_holdings_loader_passes_isin_and_justetf_name():
    engine = _FakeEngine([{
        "id": 1, "asset_type": "etf", "quote_currency": "EUR", "isin": "LU0290356871",
        "category": None, "index_tracked": None, "investment_focus": None,
        "enrichment_name": "Xtrackers II Eurozone Government Bond 1-3 UCITS ETF 1C",
    }])
    repo = SimpleNamespace(engine=engine)
    position = SimpleNamespace(asset_id=1, symbol="DBXP.DE", name="XTR2 1CC", market_value=100.0, weight=100.0)

    [holding] = _holdings_from_positions(repo, [position])

    assert holding.isin == "LU0290356871"
    assert "ee.name as enrichment_name" in engine.sql[0]
    classification = holding_classification(holding)
    assert (classification.asset_class, classification.source) == ("bond", "enrichment_name")


# --- search_asset_info (TASK-51) --------------------------------------------------------


def _asset_repo(asset_type, name, symbol, isin=None, enrichment=None, category=None):
    repo = MagicMock()
    repo.get_positions.return_value = [SimpleNamespace(symbol=symbol, asset_id=7)]
    repo.get_asset.return_value = SimpleNamespace(
        symbol=symbol, name=name, asset_type=asset_type, quote_currency="EUR", isin=isin,
    )
    repo.get_asset_metadata.return_value = (
        AssetMetadataRead(asset_id=7, category=category) if category else None
    )
    repo.get_etf_enrichment.return_value = enrichment
    return repo


@pytest.mark.parametrize(
    "asset, expected",
    [
        (("stock", "GOLD/DB ETC 60", "XAD1.DE", "DE000A1EK0G3"), ("stock", "gold", "etc")),
        (("etf", "Vanguard FTSE All-World UCITS ETF", "VWCE.DE", None), ("etf", "equity", "etf")),
        (("etf", "XTR2 EGB13 1CC", "DBXP.DE", "LU0290356871"), ("etf", "bond", "etf")),
        (("stock", "WisdomTree Brent Crude Oil ETN", "BRNT.MI", None), ("stock", "commodity", "etn")),
        (("stock", "Apple Inc", "AAPL", None), ("stock", "equity", "stock")),
    ],
)
def test_search_asset_info_exposes_class_and_instrument_type(asset, expected):
    repo = _asset_repo(*asset)
    out = copilot_tools._search_asset_info({"symbol": asset[2]}, repo, MagicMock(), 1, "u")

    assert (out["type"], out["asset_class"], out["instrument_type"]) == expected
    assert out["classification_source"]
    assert "asset_class" in out["classification_note"]


def test_search_asset_info_uses_stored_enrichment():
    repo = _asset_repo(
        "etf", "XTR2 1CC", "DBXP.DE", "LU0290356871",
        enrichment={"isin": "LU0290356871", "investment_focus": "Bonds, EUR, Government, 1-3"},
    )
    out = copilot_tools._search_asset_info({"symbol": "DBXP.DE"}, repo, MagicMock(), 1, "u")
    assert (out["asset_class"], out["classification_source"]) == ("bond", "enrichment")


def test_search_asset_info_description_names_the_field_for_allocation():
    definition = next(t for t in copilot_tools.TOOL_DEFINITIONS if t["name"] == "search_asset_info")
    for field in ("asset_class", "instrument_type", "classification_source", "type"):
        assert field in definition["description"]


# --- enrichment backfill (owner action) ----------------------------------------------------


def _asset(asset_id, symbol, asset_type, isin):
    return AssetRead(
        id=asset_id, symbol=symbol, name=symbol, asset_type=asset_type, exchange_code=None,
        exchange_name=None, quote_currency="EUR", isin=isin, active=True, supports_fractions=True,
    )


class _BackfillRepo:
    def __init__(self):
        self.assets = {
            1: _asset(1, "DBXP.DE", "etf", "LU0290356871"),
            2: _asset(2, "VEUR", "etf", "IE00BKX55T58"),
            3: _asset(3, "SWDA", "etf", "IE00B4L5Y983"),
            4: _asset(4, "CASH", "cash", None),
            5: _asset(5, "NOISIN", "etf", None),
        }
        self.upserts: list[tuple[int, str]] = []

    def get_portfolio_asset_ids(self, portfolio_id, user_id):
        if portfolio_id != 19:
            raise ValueError("Portfolio non trovato")
        return list(self.assets)

    def get_etf_enrichment_bulk(self, ids):
        return {3: {"isin": "IE00B4L5Y983"}}

    def get_etf_enrichment(self, asset_id):
        return None

    def get_asset(self, asset_id):
        return self.assets[asset_id]

    def get_asset_metadata(self, asset_id):
        return None

    def get_asset_pricing_symbol(self, asset_id, provider):
        raise ValueError("none")

    def upsert_etf_enrichment(self, asset_id, isin, data):
        self.upserts.append((asset_id, isin))


class _JustEtf:
    def __init__(self):
        self.calls: list[str] = []

    def fetch_profile(self, isin, symbol=None):
        self.calls.append(isin)
        if isin == "IE00BKX55T58":
            raise ProviderError(
                provider="justetf", operation="fetch_profile", symbol=isin,
                reason="temporarily_blocked", message="blocked",
            )
        return {"name": "Xtrackers II Eurozone Government Bond 1-3 UCITS ETF 1C",
                "investment_focus": "Bonds, EUR, Government, 1-3"}


def _backfill_client(repo, justetf):
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_assets_routes(
        router, repo, SimpleNamespace(finance_provider="yfinance"), object(),
        justetf_client=justetf, historical_service=object(),
        ensure_target_allocation_enabled=lambda: None,
    )
    app.include_router(router)
    return TestClient(app)


def test_backfill_enriches_only_assets_without_enrichment():
    repo, justetf = _BackfillRepo(), _JustEtf()
    response = _backfill_client(repo, justetf).post("/api/portfolios/19/etf-enrichment/backfill")

    assert response.status_code == 200
    body = response.json()
    assert repo.upserts == [(1, "LU0290356871")]
    assert justetf.calls == ["LU0290356871", "IE00BKX55T58"]  # SWDA already enriched
    assert [e["symbol"] for e in body["enriched"]] == ["DBXP.DE"]
    assert body["failed"] == [{"asset_id": 2, "symbol": "VEUR", "isin": "IE00BKX55T58", "reason": "temporarily_blocked"}]
    assert {(s["symbol"], s["reason"]) for s in body["skipped"]} == {("CASH", "asset_type"), ("NOISIN", "missing_isin")}
    assert body["already_enriched"] == 1


def test_backfill_unknown_portfolio_is_not_found():
    with pytest.raises(AppError) as exc:
        _backfill_client(_BackfillRepo(), _JustEtf()).post("/api/portfolios/99/etf-enrichment/backfill")
    assert exc.value.status_code == 404
