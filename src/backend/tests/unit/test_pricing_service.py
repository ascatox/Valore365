from datetime import UTC, datetime

from app.models import PriceRefreshResponse
from app.services.pricing_service import PriceIngestionService


class _FakeAsset:
    def __init__(self, asset_id: int, symbol: str, provider_symbol: str) -> None:
        self.asset_id = asset_id
        self.symbol = symbol
        self.provider_symbol = provider_symbol


class _FakeRepo:
    def __init__(self) -> None:
        self.saved = []
        self.tick_writes = 0
        self.bars_rows = []

    def get_assets_for_price_refresh(self, provider: str, portfolio_id: int | None = None, asset_scope: str = 'target', user_id: str | None = None):
        return [_FakeAsset(1, 'AAPL', 'AAPL')]

    def save_price_tick(self, **kwargs):
        self.saved.append(kwargs)

    def save_price_ticks(self, ticks):
        self.tick_writes += 1
        for tick in ticks:
            self.saved.append({
                'asset_id': tick['asset_id'],
                'provider': tick['provider'],
                'ts': tick['ts'],
                'last': tick['last'],
                'bid': tick.get('bid'),
                'ask': tick.get('ask'),
                'volume': tick.get('volume'),
                'previous_close': tick.get('previous_close'),
            })

    def batch_upsert_price_bars_1d(self, **kwargs):
        self.bars_rows.extend(kwargs.get('rows', []))


class _FakeSettings:
    finance_provider = 'yfinance'
    finance_symbol_request_delay_seconds = 0.0
    price_validation_min_price = 0.0001


class _FakeClient:
    def __init__(self, price=100.5):
        self._price = price

    def get_quote(self, symbol: str):
        price = self._price

        class Q:
            ts = datetime.now(UTC)
            bid = 100.4
            ask = 100.6
            volume = 1000

        Q.price = price
        return Q()


def test_refresh_prices_success(monkeypatch):
    import app.services.pricing_service as mod

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient())

    repo = _FakeRepo()
    service = PriceIngestionService(_FakeSettings(), repo)
    result = service.refresh_prices(portfolio_id=1)

    assert isinstance(result, PriceRefreshResponse)
    assert result.refreshed_assets == 1
    assert result.failed_assets == 0
    assert len(repo.saved) == 1
    assert repo.saved[0]['asset_id'] == 1
    assert repo.bars_rows == []


def test_refresh_prices_zero_price_rejected(monkeypatch):
    import app.services.pricing_service as mod

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient(price=0.0))

    repo = _FakeRepo()
    service = PriceIngestionService(_FakeSettings(), repo)
    result = service.refresh_prices(portfolio_id=1)

    assert isinstance(result, PriceRefreshResponse)
    assert result.refreshed_assets == 0
    assert result.failed_assets == 1
    assert len(repo.saved) == 0
    assert any("rejected" in e for e in result.errors)


class _MultiAssetRepo(_FakeRepo):
    def __init__(self, count: int) -> None:
        super().__init__()
        self.count = count

    def get_assets_for_price_refresh(self, provider: str, portfolio_id=None, asset_scope='target', user_id=None):
        return [_FakeAsset(i, f'SYM{i}', f'SYM{i}') for i in range(1, self.count + 1)]

    def save_price_tick(self, **kwargs):
        raise AssertionError(
            "saving one tick per asset takes a connection per asset, interleaved "
            "with provider calls. Use save_price_ticks for the whole run."
        )


def test_refresh_writes_all_ticks_in_one_transaction(monkeypatch):
    import app.services.pricing_service as mod
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient())
    repo = _MultiAssetRepo(33)
    service = PriceIngestionService(_FakeSettings(), repo)

    response = service.refresh_prices(portfolio_id=1, asset_scope='all', user_id='u')

    assert response.refreshed_assets == 33
    assert len(repo.saved) == 33
    assert repo.tick_writes == 1


class _PartlyFailingClient(_FakeClient):
    """Fails for one symbol the way an unresolvable ISIN does."""

    def get_quote(self, symbol: str):
        if symbol == 'SYM2':
            raise ValueError(f'Invalid ISIN number: {symbol}')
        return super().get_quote(symbol)


def test_refresh_still_writes_the_ticks_it_did_fetch(monkeypatch):
    import app.services.pricing_service as mod
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _PartlyFailingClient())
    repo = _MultiAssetRepo(3)
    service = PriceIngestionService(_FakeSettings(), repo)

    response = service.refresh_prices(portfolio_id=1, asset_scope='all', user_id='u')

    assert response.refreshed_assets == 2
    assert response.failed_assets == 1
    assert [t['asset_id'] for t in repo.saved] == [1, 3]
    assert repo.tick_writes == 1


def test_refresh_without_any_successful_quote_writes_nothing(monkeypatch):
    class _AlwaysFails(_FakeClient):
        def get_quote(self, symbol: str):
            raise ValueError(f'Invalid ISIN number: {symbol}')

    import app.services.pricing_service as mod
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _AlwaysFails())
    repo = _MultiAssetRepo(1)
    service = PriceIngestionService(_FakeSettings(), repo)

    response = service.refresh_prices(portfolio_id=1, asset_scope='all', user_id='u')

    assert response.refreshed_assets == 0
    assert repo.saved == []
