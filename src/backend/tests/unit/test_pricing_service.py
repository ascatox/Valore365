from datetime import UTC, datetime

from app.models import PriceRefreshResponse
from app.pricing_service import PriceIngestionService


class _FakeAsset:
    def __init__(self, asset_id: int, symbol: str, provider_symbol: str) -> None:
        self.asset_id = asset_id
        self.symbol = symbol
        self.provider_symbol = provider_symbol


class _FakeRepo:
    def __init__(self) -> None:
        self.saved = []
        self.bars_rows = []

    def get_assets_for_price_refresh(self, provider: str, portfolio_id: int | None = None, asset_scope: str = 'target', user_id: str | None = None):
        return [_FakeAsset(1, 'AAPL', 'AAPL')]

    def save_price_tick(self, **kwargs):
        self.saved.append(kwargs)

    def batch_upsert_price_bars_1d(self, **kwargs):
        self.bars_rows.extend(kwargs.get('rows', []))


class _FakeSettings:
    finance_provider = 'yfinance'
    finance_symbol_request_delay_seconds = 0.0


class _FakeClient:
    pass

    def get_quote(self, symbol: str):
        class Q:
            ts = datetime.now(UTC)
            price = 100.5
            bid = 100.4
            ask = 100.6
            volume = 1000

        return Q()


def test_refresh_prices_success(monkeypatch):
    import app.pricing_service as mod

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient())

    repo = _FakeRepo()
    service = PriceIngestionService(_FakeSettings(), repo)
    result = service.refresh_prices(portfolio_id=1)

    assert isinstance(result, PriceRefreshResponse)
    assert result.refreshed_assets == 1
    assert result.failed_assets == 0
    assert len(repo.saved) == 1
    assert repo.saved[0]['asset_id'] == 1
