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

    def get_assets_for_price_refresh(self, provider: str, portfolio_id: int | None = None):
        return [_FakeAsset(1, 'AAPL', 'AAPL')]

    def save_price_tick(self, **kwargs):
        self.saved.append(kwargs)


class _FakeSettings:
    finance_provider = 'twelvedata'
    finance_api_base_url = 'https://api.twelvedata.com'
    finance_api_key = 'k'
    finance_request_timeout_seconds = 5.0
    finance_max_retries = 1
    finance_retry_backoff_seconds = 0.1
    finance_symbol_request_delay_seconds = 0.0


class _FakeClient:
    def __init__(self, **kwargs):
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

    monkeypatch.setattr(mod, 'TwelveDataClient', _FakeClient)

    repo = _FakeRepo()
    service = PriceIngestionService(_FakeSettings(), repo)
    result = service.refresh_prices(portfolio_id=1)

    assert isinstance(result, PriceRefreshResponse)
    assert result.refreshed_assets == 1
    assert result.failed_assets == 0
    assert len(repo.saved) == 1
    assert repo.saved[0]['asset_id'] == 1
