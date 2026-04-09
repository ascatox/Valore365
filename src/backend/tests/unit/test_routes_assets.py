from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.api.routes_assets import register_assets_routes
from app.errors import ProviderError
from app.finance_client import ProviderQuote, ProviderSymbol, resolve_provider_symbol_candidates
from app.models import AssetProviderSymbolRead, AssetRead


def test_resolve_provider_symbol_candidates_prefers_same_base_symbol(monkeypatch):
    monkeypatch.setattr(
        "app.finance_client._resolve_isin",
        lambda isin: [
            ProviderSymbol(symbol="XYZ.MI", instrument_name="Other", exchange="IM", country=None),
            ProviderSymbol(symbol="VEUR.DE", instrument_name="VEUR DE", exchange="GR", country=None),
            ProviderSymbol(symbol="VEUR.AS", instrument_name="VEUR AS", exchange="NA", country=None),
        ],
    )

    assert resolve_provider_symbol_candidates("VEUR", "IE00BK5BQX27") == ["VEUR.AS", "VEUR.DE", "XYZ.MI"]


class _EnsureRepo:
    def __init__(self) -> None:
        self.upserts: list[tuple[int, str, str]] = []

    def find_asset_by_symbol(self, symbol: str):
        return {"id": 1, "symbol": symbol, "name": "Vanguard Europe"}

    def get_asset(self, asset_id: int) -> AssetRead:
        return AssetRead(
            id=asset_id,
            symbol="VEUR",
            name="Vanguard Europe",
            asset_type="etf",
            exchange_code=None,
            exchange_name=None,
            quote_currency="EUR",
            isin="IE00BK5BQX27",
            active=True,
            supports_fractions=True,
        )

    def upsert_asset_provider_symbol(self, payload):
        self.upserts.append((payload.asset_id, payload.provider, payload.provider_symbol))
        return AssetProviderSymbolRead(
            asset_id=payload.asset_id,
            provider=payload.provider,
            provider_symbol=payload.provider_symbol,
        )


class _EnsureFinanceClient:
    pass


def test_ensure_asset_uses_isin_to_store_provider_symbol(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes_assets.resolve_provider_symbol_candidates",
        lambda symbol, isin: ["VEUR.AS"],
    )

    repo = _EnsureRepo()
    finance_client = _EnsureFinanceClient()
    settings = SimpleNamespace(finance_provider="yfinance")

    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_assets_routes(
        router,
        repo,
        settings,
        finance_client,
        justetf_client=object(),
        historical_service=object(),
        ensure_target_allocation_enabled=lambda: None,
    )
    app.include_router(router)

    client = TestClient(app)
    response = client.post(
        "/api/assets/ensure",
        json={
            "source": "provider",
            "symbol": "VEUR",
            "provider": "yfinance",
            "isin": "IE00BK5BQX27",
        },
    )

    assert response.status_code == 200
    assert repo.upserts == [(1, "yfinance", "VEUR.AS")]


class _QuoteRepo:
    def __init__(self) -> None:
        self.upserts: list[tuple[int, str, str]] = []

    def get_asset_pricing_symbol(self, asset_id: int, provider: str = "yfinance"):
        return SimpleNamespace(asset_id=asset_id, symbol="VEUR", provider_symbol="VEUR")

    def get_asset(self, asset_id: int) -> AssetRead:
        return AssetRead(
            id=asset_id,
            symbol="VEUR",
            name="Vanguard Europe",
            asset_type="etf",
            exchange_code=None,
            exchange_name=None,
            quote_currency="EUR",
            isin="IE00BK5BQX27",
            active=True,
            supports_fractions=True,
        )

    def upsert_asset_provider_symbol(self, payload):
        self.upserts.append((payload.asset_id, payload.provider, payload.provider_symbol))
        return AssetProviderSymbolRead(
            asset_id=payload.asset_id,
            provider=payload.provider,
            provider_symbol=payload.provider_symbol,
        )


class _QuoteFinanceClient:
    def get_quote(self, symbol: str):
        if symbol == "VEUR":
            raise ProviderError(
                provider="yfinance",
                operation="quote",
                symbol=symbol,
                reason="no_data",
                message=f"Nessuna quotazione disponibile per {symbol}",
            )
        if symbol == "VEUR.AS":
            return ProviderQuote(
                symbol=symbol,
                price=42.5,
                bid=None,
                ask=None,
                volume=None,
                ts=datetime(2026, 4, 9, tzinfo=UTC),
                source="fast_info",
                is_realtime=True,
                is_fallback=False,
                stale=False,
                warning=None,
                previous_close=42.0,
            )
        raise AssertionError(f"unexpected symbol {symbol}")


def test_latest_quote_repairs_provider_symbol_from_isin(monkeypatch):
    monkeypatch.setattr(
        "app.api.routes_assets.resolve_provider_symbol_candidates",
        lambda symbol, isin: ["VEUR.AS"],
    )

    repo = _QuoteRepo()
    finance_client = _QuoteFinanceClient()
    settings = SimpleNamespace(finance_provider="yfinance")

    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_assets_routes(
        router,
        repo,
        settings,
        finance_client,
        justetf_client=object(),
        historical_service=object(),
        ensure_target_allocation_enabled=lambda: None,
    )
    app.include_router(router)

    client = TestClient(app)
    response = client.get("/api/assets/1/latest-quote")

    assert response.status_code == 200
    payload = response.json()
    assert payload["provider_symbol"] == "VEUR.AS"
    assert payload["price"] == 42.5
    assert repo.upserts == [(1, "yfinance", "VEUR.AS")]
