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


class _BenchmarkRepo:
    """Only SPY exists already (as created by older versions, quoted in EUR)."""

    def __init__(self) -> None:
        self.assets: dict[str, dict] = {"SPY": {"id": 10, "symbol": "SPY", "name": "SPDR S&P 500 ETF Trust"}}
        self.created: list = []
        self.provider_symbols: list[tuple[int, str, str]] = []

    def get_asset_by_symbol(self, symbol: str):
        return self.assets.get(symbol)

    def create_asset(self, payload):
        asset_id = 100 + len(self.created)
        self.created.append(payload)
        self.assets[payload.symbol] = {"id": asset_id, "symbol": payload.symbol, "name": payload.name}
        return AssetRead(
            id=asset_id,
            symbol=payload.symbol,
            name=payload.name,
            asset_type=payload.asset_type,
            exchange_code=payload.exchange_code,
            exchange_name=payload.exchange_name,
            quote_currency=payload.quote_currency,
            isin=payload.isin,
            active=True,
            supports_fractions=True,
        )

    def create_asset_provider_symbol(self, payload):
        self.provider_symbols.append((payload.asset_id, payload.provider, payload.provider_symbol))


def _benchmark_client(repo) -> TestClient:
    from app.auth import AuthContext
    from app.rate_limit import require_auth_rate_limited

    app = FastAPI()
    router = APIRouter(prefix="/api")
    register_assets_routes(
        router,
        repo,
        SimpleNamespace(finance_provider="yfinance"),
        object(),
        justetf_client=object(),
        historical_service=object(),
        ensure_target_allocation_enabled=lambda: None,
    )
    app.include_router(router)
    app.dependency_overrides[require_auth_rate_limited] = lambda: AuthContext(user_id="u1")
    return TestClient(app)


def test_benchmark_list_covers_us_markets_and_europe():
    from app.constants.benchmarks import BENCHMARK_SYMBOLS, BENCHMARKS

    assert BENCHMARK_SYMBOLS == ("SPY", "QQQ", "DIA", "IWM", "EXSA.DE")
    by_symbol = {b["symbol"]: b for b in BENCHMARKS}
    assert {s for s, b in by_symbol.items() if b["quote_currency"] == "USD"} == {"SPY", "QQQ", "DIA", "IWM"}
    assert by_symbol["EXSA.DE"]["quote_currency"] == "EUR"
    assert by_symbol["EXSA.DE"]["label"] == "STOXX Europe 600"
    assert all(b["label"] and b["name"] for b in BENCHMARKS)


def test_scheduler_backfills_every_benchmark():
    from app import scheduler
    from app.constants.benchmarks import BENCHMARK_SYMBOLS

    assert scheduler.BENCHMARK_SYMBOLS is BENCHMARK_SYMBOLS


def test_get_benchmarks_creates_missing_ones_and_keeps_existing_spy():
    repo = _BenchmarkRepo()
    response = _benchmark_client(repo).get("/api/benchmarks")

    assert response.status_code == 200
    items = response.json()
    assert [i["symbol"] for i in items] == ["SPY", "QQQ", "DIA", "IWM", "EXSA.DE"]
    assert items[0] == {"asset_id": 10, "symbol": "SPY", "name": "SPDR S&P 500 ETF Trust", "label": "S&P 500"}
    assert items[-1]["label"] == "STOXX Europe 600"

    # SPY already existed: it is not recreated.
    created = {p.symbol: p for p in repo.created}
    assert set(created) == {"QQQ", "DIA", "IWM", "EXSA.DE"}
    assert created["QQQ"].quote_currency == "USD"
    assert created["EXSA.DE"].quote_currency == "EUR"
    assert all(p.asset_type == "etf" for p in created.values())
    assert sorted(ps for _, _, ps in repo.provider_symbols) == ["DIA", "EXSA.DE", "IWM", "QQQ"]
    assert all(provider == "yfinance" for _, provider, _ in repo.provider_symbols)

    # A second call finds every asset and creates nothing.
    _benchmark_client(repo).get("/api/benchmarks")
    assert len(repo.created) == 4
