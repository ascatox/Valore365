"""TASK-52: TER from verifiable sources (yFinance expense ratio keys, justETF), never invented."""

from __future__ import annotations

import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_assets import register_assets_routes
from app.errors import AppError
from app.finance_client import (
    ProviderAssetInfo,
    YahooFinanceClient,
    extract_expense_ratio_pct,
)
from app.models import AssetRead
from app.services.portfolio_doctor._health import resolve_holding_ters
from app.services.portfolio_doctor._holdings import AnalyzedHolding

# --- yfinance key extraction --------------------------------------------------------


@pytest.mark.parametrize(
    ("info", "expected", "key"),
    [
        ({"netExpenseRatio": 0.15}, 0.15, "netExpenseRatio"),            # TLT, percent points
        ({"annualReportExpenseRatio": 0.0015}, 0.15, "annualReportExpenseRatio"),  # fraction
        ({"expenseRatio": 0.0003}, 0.03, "expenseRatio"),                # legacy key, fraction
        ({"netExpenseRatio": 0.4, "annualReportExpenseRatio": 0.0070}, 0.4, "netExpenseRatio"),
        ({"netExpenseRatio": None, "annualReportExpenseRatio": 0.004}, 0.4, "annualReportExpenseRatio"),
        ({"netExpenseRatio": "n/a", "expenseRatio": 0.0025}, 0.25, "expenseRatio"),
        ({"netExpenseRatio": {"raw": 0.0009, "fmt": "0.09%"}}, 0.09, "netExpenseRatio"),
        ({}, None, None),
        ({"netExpenseRatio": -1}, None, None),
    ],
)
def test_extract_expense_ratio_reads_current_and_legacy_yfinance_keys(info, expected, key):
    value, used = extract_expense_ratio_pct(info)
    if expected is None:
        assert value is None and used is None
    else:
        assert value == pytest.approx(expected)
        assert used == key


def test_get_asset_info_uses_annual_report_expense_ratio_when_net_is_absent(monkeypatch):
    class _Ticker:
        def __init__(self, symbol):
            self.info = {"quoteType": "ETF", "longName": "SPDR Gold Shares", "annualReportExpenseRatio": 0.004}

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(Ticker=_Ticker))
    info = YahooFinanceClient(max_retries=1).get_asset_info("GLD")

    assert info.expense_ratio == pytest.approx(0.4)
    assert info.expense_ratio_source_key == "annualReportExpenseRatio"


# --- resolve_holding_ters -----------------------------------------------------------


def _h(aid, symbol, name, asset_type="etf"):
    return AnalyzedHolding(asset_id=aid, symbol=symbol, name=name, asset_type=asset_type,
                           quote_currency="USD", market_value=100.0, weight_pct=25.0)


class _Repo:
    def __init__(self, enrichment=None, metadata=None):
        self.enrichment = enrichment or {}
        self.metadata = metadata or {}

    def get_etf_enrichment_bulk(self, ids):
        return {a: e for a, e in self.enrichment.items() if a in ids}

    def get_asset_metadata_bulk(self, ids):
        return {a: m for a, m in self.metadata.items() if a in ids}


def test_stored_raw_info_fills_a_missing_expense_ratio_column():
    """Metadata stored before the key fix: the column is empty, raw_info has the value."""
    holdings = [_h(1, "TLT", "TLT"), _h(2, "DJP", "DJP")]
    repo = _Repo(metadata={
        1: SimpleNamespace(expense_ratio=None, raw_info={"netExpenseRatio": 0.15}),
        2: SimpleNamespace(expense_ratio=None, raw_info={"annualReportExpenseRatio": 0.007}),
    })

    resolved = resolve_holding_ters(holdings, repo)

    assert resolved[1] == (pytest.approx(0.15), "yfinance")
    assert resolved[2] == (pytest.approx(0.7), "yfinance")


def test_justetf_ter_of_an_etc_stored_as_stock_is_used():
    holdings = [_h(7, "XAD1.DE", "Xtrackers IE Physical Gold ETC", asset_type="stock")]
    repo = _Repo(enrichment={7: {"ter": 0.11}})

    assert resolve_holding_ters(holdings, repo)[7] == (pytest.approx(0.11), "justetf")


def test_no_source_means_no_ter_never_an_invented_one():
    holdings = [_h(1, "TLT", "TLT"), _h(5, "GLD", "GLD")]
    resolved = resolve_holding_ters(holdings, _Repo(metadata={
        1: SimpleNamespace(expense_ratio=None, raw_info={"netExpenseRatio": None}),
    }))

    assert resolved[1] == (None, "none")
    assert resolved[5] == (None, "none")


# --- owner backfill of yFinance metadata (no network in read paths) -----------------


def _asset(asset_id, symbol, name, asset_type, isin=None):
    return AssetRead(
        id=asset_id, symbol=symbol, name=name, asset_type=asset_type, exchange_code=None,
        exchange_name=None, quote_currency="USD", isin=isin, active=True, supports_fractions=True,
    )


class _MetaRepo:
    def __init__(self):
        self.assets = {
            1: _asset(1, "TLT", "iShares 20+ Year Treasury Bond ETF", "etf"),
            2: _asset(2, "GLD", "SPDR Gold Shares", "etf"),
            3: _asset(3, "VTI", "Vanguard Total Stock Market ETF", "etf"),
            4: _asset(4, "AAPL", "Apple Inc", "stock"),
            5: _asset(5, "CASH", "Cash", "cash"),
            6: _asset(6, "IEF", "iShares 7-10 Year Treasury Bond ETF", "etf"),
        }
        # VTI already has a TER; AAPL has metadata (a share: no TER expected).
        self.metadata = {
            3: SimpleNamespace(expense_ratio=0.03, raw_info=None),
            4: SimpleNamespace(expense_ratio=None, raw_info=None),
        }
        self.upserts: list[tuple[int, float | None]] = []

    def get_portfolio_asset_ids(self, portfolio_id, user_id):
        if portfolio_id != 26:
            raise ValueError("Portfolio non trovato")
        return list(self.assets)

    def get_asset(self, asset_id):
        return self.assets[asset_id]

    def get_asset_metadata_bulk(self, ids):
        return {a: m for a, m in self.metadata.items() if a in ids}

    def get_asset_pricing_symbol(self, asset_id, provider):
        return SimpleNamespace(provider_symbol=self.assets[asset_id].symbol)

    def upsert_asset_metadata(self, asset_id, data):
        self.upserts.append((asset_id, data.get("expense_ratio")))


class _Finance:
    def __init__(self):
        self.calls: list[str] = []

    def get_asset_info(self, symbol):
        self.calls.append(symbol)
        if symbol == "IEF":
            raise RuntimeError("provider down")
        values = {"TLT": (0.15, "netExpenseRatio"), "GLD": (None, None)}
        ratio, key = values[symbol]
        return ProviderAssetInfo(
            symbol=symbol, name=symbol, sector=None, industry=None, country=None, market_cap=None,
            trailing_pe=None, forward_pe=None, dividend_yield=None, beta=None, fifty_two_week_high=None,
            fifty_two_week_low=None, avg_volume=None, currency="USD", current_price=None,
            previous_close=None, description=None, quote_type="ETF",
            expense_ratio=ratio, expense_ratio_source_key=key,
        )


def _client(repo, finance):
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_assets_routes(
        router, repo, SimpleNamespace(finance_provider="yfinance"), finance,
        justetf_client=object(), historical_service=object(),
        ensure_target_allocation_enabled=lambda: None,
    )
    app.include_router(router)
    return TestClient(app)


def test_metadata_backfill_fetches_funds_without_ter_only():
    repo, finance = _MetaRepo(), _Finance()

    response = _client(repo, finance).post("/api/portfolios/26/asset-metadata/backfill")

    assert response.status_code == 200
    body = response.json()
    # VTI has a TER, AAPL is a share with metadata, CASH is skipped.
    assert finance.calls == ["TLT", "GLD", "IEF"]
    assert repo.upserts == [(1, 0.15), (2, None)]
    by_symbol = {u["symbol"]: u for u in body["updated"]}
    assert by_symbol["TLT"]["expense_ratio_pct"] == 0.15
    assert by_symbol["TLT"]["expense_ratio_source_key"] == "netExpenseRatio"
    assert by_symbol["GLD"]["expense_ratio_pct"] is None
    assert body["failed"] == [{"asset_id": 6, "symbol": "IEF", "reason": "RuntimeError"}]
    assert {(s["symbol"], s["reason"]) for s in body["skipped"]} >= {("CASH", "asset_type")}


def test_metadata_backfill_unknown_portfolio_is_not_found():
    with pytest.raises(AppError) as exc:
        _client(_MetaRepo(), _Finance()).post("/api/portfolios/99/asset-metadata/backfill")
    assert exc.value.status_code == 404


class _EtcRepo:
    """XAD1.DE: an ETC typed stock, enriched once without a TER."""

    def __init__(self):
        self.upserts: list[tuple[int, str]] = []

    def get_portfolio_asset_ids(self, portfolio_id, user_id):
        return [7]

    def get_etf_enrichment_bulk(self, ids):
        return {7: {"isin": "DE000A2T0VU5", "ter": None}}

    def get_etf_enrichment(self, asset_id):
        return {"isin": "DE000A2T0VU5"}

    def get_asset(self, asset_id):
        return _asset(7, "XAD1.DE", "Xtrackers IE Physical Gold ETC", "stock", "DE000A2T0VU5")

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
        return {"name": "Xtrackers IE Physical Gold ETC", "ter": 0.11}


def test_etf_enrichment_backfill_refreshes_a_row_without_ter_only_on_request():
    repo, justetf = _EtcRepo(), _JustEtf()
    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_assets_routes(
        router, repo, SimpleNamespace(finance_provider="yfinance"), object(),
        justetf_client=justetf, historical_service=object(),
        ensure_target_allocation_enabled=lambda: None,
    )
    app.include_router(router)
    client = TestClient(app)

    client.post("/api/portfolios/1/etf-enrichment/backfill")
    assert justetf.calls == []  # default: existing rows are left alone

    response = client.post("/api/portfolios/1/etf-enrichment/backfill?refresh_missing_ter=true")
    assert response.status_code == 200
    # Typed stock, but not skipped: the ETC's TER is on justETF.
    assert justetf.calls == ["DE000A2T0VU5"]
    assert repo.upserts == [(7, "DE000A2T0VU5")]
