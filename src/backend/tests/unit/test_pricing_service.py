import logging
import threading
import time
from datetime import UTC, datetime
from types import SimpleNamespace

import app.scheduler as scheduler_mod
from app.models import PriceRefreshResponse
from app.scheduler import PriceRefreshScheduler
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
    finance_quote_concurrency = 4
    price_validation_min_price = 0.0001
    price_scheduler_after_close_grace_minutes = 30


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


class _SymbolsRepo(_FakeRepo):
    def __init__(self, symbols: list[str]) -> None:
        super().__init__()
        self.symbols = symbols

    def get_assets_for_price_refresh(self, provider: str, portfolio_id=None, asset_scope='target', user_id=None):
        return [_FakeAsset(i, s, s) for i, s in enumerate(self.symbols, start=1)]


class _RecordingClient(_FakeClient):
    def __init__(self, price=100.5):
        super().__init__(price)
        self.calls: list[str] = []
        self._lock = threading.Lock()

    def get_quote(self, symbol: str):
        with self._lock:
            self.calls.append(symbol)
        return super().get_quote(symbol)


def test_refresh_fetches_quotes_in_parallel(monkeypatch):
    # Passes only if four quotes are in flight at the same time.
    barrier = threading.Barrier(4, timeout=5)

    class _BarrierClient(_FakeClient):
        def get_quote(self, symbol: str):
            barrier.wait()
            return super().get_quote(symbol)

    import app.services.pricing_service as mod
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _BarrierClient())
    repo = _MultiAssetRepo(4)

    response = PriceIngestionService(_FakeSettings(), repo).refresh_prices(portfolio_id=1)

    assert response.refreshed_assets == 4
    assert repo.tick_writes == 1


def test_parallel_refresh_keeps_the_asset_order(monkeypatch):
    class _SlowFirstClient(_FakeClient):
        def get_quote(self, symbol: str):
            if symbol == 'SYM1':
                time.sleep(0.2)
            if symbol in ('SYM2', 'SYM5'):
                raise ValueError(f'Nessuna quotazione disponibile per {symbol}')
            quote = super().get_quote(symbol)
            quote.price = float(symbol[3:])
            return quote

    import app.services.pricing_service as mod
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _SlowFirstClient())
    repo = _MultiAssetRepo(6)

    response = PriceIngestionService(_FakeSettings(), repo).refresh_prices(portfolio_id=1)

    assert [item.asset_id for item in response.items] == [1, 3, 4, 6]
    assert [t['asset_id'] for t in repo.saved] == [1, 3, 4, 6]
    assert [t['last'] for t in repo.saved] == [1.0, 3.0, 4.0, 6.0]
    assert [e.split(':')[0] for e in response.errors] == ['SYM2', 'SYM5']
    assert repo.tick_writes == 1


def test_refresh_stays_sequential_when_a_symbol_delay_is_configured(monkeypatch):
    events: list[str] = []
    main_thread = threading.current_thread()

    class _OrderedClient(_FakeClient):
        def get_quote(self, symbol: str):
            assert threading.current_thread() is main_thread
            events.append(f'fetch:{symbol}')
            return super().get_quote(symbol)

    import app.services.pricing_service as mod
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _OrderedClient())
    monkeypatch.setattr(mod.time, 'sleep', lambda seconds: events.append(f'sleep:{seconds}'))
    settings = _FakeSettings()
    settings.finance_symbol_request_delay_seconds = 0.25

    response = PriceIngestionService(settings, _MultiAssetRepo(3)).refresh_prices(portfolio_id=1)

    assert response.refreshed_assets == 3
    assert events == ['fetch:SYM1', 'sleep:0.25', 'fetch:SYM2', 'sleep:0.25', 'fetch:SYM3']


# Wednesday 28/10/2026 15:00 UTC: 11:00 in New York, 16:00 in Milan, midnight in Tokyo.
_WEDNESDAY_AFTERNOON = datetime(2026, 10, 28, 15, 0, tzinfo=UTC)
_SATURDAY = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)


def test_market_hours_refresh_skips_assets_whose_market_is_closed(monkeypatch, caplog):
    import app.services.pricing_service as mod
    client = _RecordingClient()
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: client)
    repo = _SymbolsRepo(['AAPL', 'ENI.MI', '7203.T', 'BTC-USD'])

    with caplog.at_level(logging.INFO, logger=mod.__name__):
        response = PriceIngestionService(_FakeSettings(), repo).refresh_prices(
            portfolio_id=1, market_hours_at=_WEDNESDAY_AFTERNOON,
        )

    assert sorted(client.calls) == ['AAPL', 'BTC-USD', 'ENI.MI']
    assert [item.provider_symbol for item in response.items] == ['AAPL', 'ENI.MI', 'BTC-USD']
    assert response.failed_assets == 0
    assert 'closed market' in caplog.text and 'count=1' in caplog.text and '7203.T' in caplog.text


def test_market_hours_refresh_with_every_market_closed_makes_no_provider_call(monkeypatch):
    import app.services.pricing_service as mod
    client = _RecordingClient()
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: client)
    repo = _SymbolsRepo(['AAPL', 'ENI.MI', 'EURUSD=X'])

    response = PriceIngestionService(_FakeSettings(), repo).refresh_prices(portfolio_id=1, market_hours_at=_SATURDAY)

    assert client.calls == []
    assert (response.refreshed_assets, response.failed_assets) == (0, 0)


def test_market_hours_use_the_mapped_symbol_when_the_bare_symbol_is_requested(monkeypatch):
    # The scheduler requests 'VWCE' (prefer_symbol_then_isin) but the asset trades
    # in Milan (VWCE.MI): gate it on Milan hours, not on US hours.
    import app.services.pricing_service as mod
    client = _RecordingClient()
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: client)
    vwce = _FakeAsset(1, 'VWCE', 'VWCE')
    vwce.market_symbol = 'VWCE.MI'

    class _Repo(_FakeRepo):
        def get_assets_for_price_refresh(self, *args, **kwargs):
            return [vwce]

    service = PriceIngestionService(_FakeSettings(), _Repo())
    # Wednesday 10:00 in Milan, 05:00 in New York.
    service.refresh_prices(portfolio_id=1, market_hours_at=datetime(2026, 10, 28, 9, 0, tzinfo=UTC))
    assert client.calls == ['VWCE']

    client.calls.clear()
    # Wednesday 21:00 in Milan, 16:00 in New York (inside the US grace window).
    service.refresh_prices(portfolio_id=1, market_hours_at=datetime(2026, 10, 28, 20, 0, tzinfo=UTC))
    assert client.calls == []


def test_refresh_without_market_hours_fetches_every_asset(monkeypatch):
    # Manual refreshes (API routes) never pass market_hours_at.
    import app.services.pricing_service as mod
    client = _RecordingClient()
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: client)
    repo = _SymbolsRepo(['AAPL', 'ENI.MI', 'EURUSD=X'])

    response = PriceIngestionService(_FakeSettings(), repo).refresh_prices(portfolio_id=1)

    assert sorted(client.calls) == ['AAPL', 'ENI.MI', 'EURUSD=X']
    assert response.refreshed_assets == 3


def _scheduler_settings(**overrides) -> SimpleNamespace:
    values = {
        'price_scheduler_market_hours_only': True,
        'enable_target_allocation': True,
        'price_scheduler_portfolio_id': None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_scheduler_job_skips_closed_markets(monkeypatch):
    class _FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return _SATURDAY

    import app.services.pricing_service as mod
    client = _RecordingClient()
    monkeypatch.setattr(mod, 'make_finance_client', lambda _: client)
    monkeypatch.setattr(scheduler_mod, 'datetime', _FrozenDatetime)
    service = PriceIngestionService(_FakeSettings(), _SymbolsRepo(['AAPL', 'ENI.MI', 'BTC-USD']))

    PriceRefreshScheduler(_scheduler_settings(), service)._run_refresh()

    assert client.calls == ['BTC-USD']


def test_scheduler_job_can_ignore_market_hours():
    class _Service:
        def refresh_prices(self, **kwargs):
            self.kwargs = kwargs
            return PriceRefreshResponse(
                provider='yfinance', requested_assets=0, refreshed_assets=0, failed_assets=0, items=[], errors=[],
            )

    service = _Service()
    PriceRefreshScheduler(_scheduler_settings(price_scheduler_market_hours_only=False), service)._run_refresh()

    assert service.kwargs['market_hours_at'] is None
