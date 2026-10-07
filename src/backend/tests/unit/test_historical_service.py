from datetime import date

from app.services.historical_service import HistoricalIngestionService
from app.models import DailyBackfillResponse


class _FakeAsset:
    def __init__(self, asset_id: int, symbol: str, provider_symbol: str) -> None:
        self.asset_id = asset_id
        self.symbol = symbol
        self.provider_symbol = provider_symbol


class _FakeRepo:
    def __init__(self) -> None:
        self.bars_rows = []
        self.fx_rows = []

    def get_assets_for_price_refresh(self, provider: str, portfolio_id: int | None = None, asset_scope: str = 'target', user_id: str | None = None):
        return [_FakeAsset(1, 'AAPL', 'AAPL')]

    def get_portfolio_base_currency(self, portfolio_id: int, user_id: str | None = None):
        return 'EUR'

    def get_quote_currencies_for_assets(self, asset_ids: list[int]):
        return {1: 'USD'}

    def batch_upsert_price_bars_1d(self, **kwargs):
        self.bars_rows.extend(kwargs['rows'])

    def batch_upsert_fx_rates_1d(self, **kwargs):
        self.fx_rows.extend(kwargs['rows'])

    def get_latest_close_price(self, asset_id: int):
        return None


class _FakeSettings:
    finance_provider = 'yfinance'
    price_validation_max_daily_change_pct = 50.0
    price_validation_max_ohlc_spread_pct = 100.0
    price_validation_ohlc_range_tolerance_pct = 2.0
    price_validation_fx_min_rate = 0.0001
    price_validation_fx_max_rate = 10000.0
    price_backfill_max_workers = 4


class _FakeClient:
    def __init__(self, bars=None, fx_rates=None):
        self._bars = bars
        self._fx_rates = fx_rates

    def get_daily_bars(self, symbol: str, outputsize: int = 365, *, start_date=None, end_date=None, **kwargs):
        if self._bars is not None:
            return self._bars

        class B:
            def __init__(self, day):
                self.day = day
                self.open = 1.0
                self.high = 1.1
                self.low = 0.9
                self.close = 1.05
                self.volume = 10.0

        return [B(date.today())]

    def get_daily_fx_rates(self, from_currency: str, to_currency: str, outputsize: int = 365, *, start_date=None, end_date=None, **kwargs):
        if self._fx_rates is not None:
            return self._fx_rates

        class F:
            def __init__(self, day):
                self.day = day
                self.rate = 0.92

        return [F(date.today())]


def test_backfill_daily_batch_upsert(monkeypatch):
    import app.services.historical_service as mod

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient())

    repo = _FakeRepo()
    service = HistoricalIngestionService(_FakeSettings(), repo)

    result = service.backfill_daily(portfolio_id=1, days=365)
    assert isinstance(result, DailyBackfillResponse)
    assert result.assets_refreshed == 1
    assert result.fx_pairs_refreshed == 1
    assert len(repo.bars_rows) == 1
    assert len(repo.fx_rows) == 1
    assert result.asset_items[0].bars_requested == 1
    assert result.asset_items[0].bars_rejected == 0
    assert result.fx_items[0].rates_requested == 1
    assert result.fx_items[0].rates_rejected == 0


def test_backfill_daily_rejects_high_less_than_low(monkeypatch):
    import app.services.historical_service as mod

    class BadBar:
        def __init__(self):
            self.day = date.today()
            self.open = 100.0
            self.high = 90.0   # high < low → invalid
            self.low = 95.0
            self.close = 92.0
            self.volume = 500

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient(bars=[BadBar()]))

    repo = _FakeRepo()
    service = HistoricalIngestionService(_FakeSettings(), repo)

    result = service.backfill_daily(portfolio_id=1, days=365)
    assert result.assets_refreshed == 1
    # The bad bar should be filtered out
    assert result.asset_items[0].bars_saved == 0
    assert len(repo.bars_rows) == 0


def test_backfill_daily_rejects_zero_close(monkeypatch):
    import app.services.historical_service as mod

    class ZeroBar:
        def __init__(self):
            self.day = date.today()
            self.open = 100.0
            self.high = 105.0
            self.low = 95.0
            self.close = 0.0
            self.volume = 500

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient(bars=[ZeroBar()]))

    repo = _FakeRepo()
    service = HistoricalIngestionService(_FakeSettings(), repo)

    result = service.backfill_daily(portfolio_id=1, days=365)
    assert result.asset_items[0].bars_saved == 0
    assert len(repo.bars_rows) == 0


def test_backfill_daily_rejects_invalid_fx_rate(monkeypatch):
    import app.services.historical_service as mod

    class BadFx:
        def __init__(self):
            self.day = date.today()
            self.rate = 0.0

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient(fx_rates=[BadFx()]))

    repo = _FakeRepo()
    service = HistoricalIngestionService(_FakeSettings(), repo)

    result = service.backfill_daily(portfolio_id=1, days=365)
    # Valid bars should still be saved
    assert len(repo.bars_rows) == 1
    # Invalid FX rate should be filtered
    assert len(repo.fx_rows) == 0


def test_backfill_daily_skips_bare_isin_without_provider_call(monkeypatch):
    import app.services.historical_service as mod

    requested: list[str] = []

    class _RecordingClient(_FakeClient):
        def get_daily_bars(self, symbol, **kwargs):
            requested.append(symbol)
            return super().get_daily_bars(symbol, **kwargs)

    class _IsinRepo(_FakeRepo):
        def get_assets_for_price_refresh(self, **kwargs):
            return [_FakeAsset(1, 'AAPL', 'AAPL'), _FakeAsset(2, 'IT0005549388', 'IT0005549388')]

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _RecordingClient())
    result = HistoricalIngestionService(_FakeSettings(), _IsinRepo()).backfill_daily(portfolio_id=1, days=365)

    assert requested == ['AAPL']
    assert result.assets_requested == 2
    assert result.assets_refreshed == 1
    assert any('IT0005549388' in e for e in result.errors)


def test_is_unpriceable_on_yahoo():
    from app.finance_client import is_unpriceable_on_yahoo

    assert is_unpriceable_on_yahoo('yfinance', 'IT0005549388')
    assert not is_unpriceable_on_yahoo('twelvedata', 'IT0005549388')
    for symbol in ('VWCG.AS', '0GGH.L', 'AAPL', 'BTC-USD'):
        assert not is_unpriceable_on_yahoo('yfinance', symbol)


# --- Fallback ISIN quando lo storico del simbolo e' insufficiente (es. 0GGH.L) ---

from datetime import timedelta

from app.errors import ProviderError


class _Bar:
    def __init__(self, day, close):
        self.day = day
        self.open = close
        self.high = close
        self.low = close
        self.close = close
        self.volume = 100.0


def _history(days: int, close: float):
    today = date.today()
    return [_Bar(today - timedelta(days=i), close) for i in range(days) if (today - timedelta(days=i)).weekday() < 5]


class _IsinRepo(_FakeRepo):
    def __init__(self, isin='IE00BDBRDM35') -> None:
        super().__init__()
        self.isin = isin
        self.upserted = []

    def get_assets_for_price_refresh(self, provider: str, portfolio_id: int | None = None, asset_scope: str = 'target', user_id: str | None = None):
        return [_FakeAsset(1, '0GGH', '0GGH.L')]

    def get_quote_currencies_for_assets(self, asset_ids: list[int]):
        return {1: 'EUR'}

    def get_asset(self, asset_id: int):
        class A:
            pass
        a = A()
        a.isin = self.isin
        return a

    def upsert_asset_provider_symbol(self, payload):
        self.upserted.append(payload.provider_symbol)


class _SymbolClient(_FakeClient):
    def __init__(self, bars_by_symbol):
        super().__init__()
        self.bars_by_symbol = bars_by_symbol
        self.requested = []

    def get_daily_bars(self, symbol: str, outputsize: int = 365, *, start_date=None, end_date=None, **kwargs):
        self.requested.append(symbol)
        value = self.bars_by_symbol.get(symbol, [])
        if isinstance(value, Exception):
            raise value
        return value


def _patch(monkeypatch, client, candidates):
    import app.services.historical_service as mod

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: client)
    monkeypatch.setattr(mod, 'resolve_provider_symbol_candidates', lambda symbol, isin: candidates)


def test_backfill_switches_to_isin_candidate_when_history_is_insufficient(monkeypatch):
    client = _SymbolClient({
        '0GGH.L': _history(1, 4.80),
        'AGGH.AS': _history(30, 4.81),       # storico corto: scartato a favore di uno completo
        'AGGH.MI': _history(365, 4.81),
    })
    _patch(monkeypatch, client, ['0GGH.L', 'AGGH.AS', 'AGGH.MI', 'EUNA.DE'])

    repo = _IsinRepo()
    result = HistoricalIngestionService(_FakeSettings(), repo).backfill_daily(portfolio_id=1, days=365)

    assert result.asset_items[0].provider_symbol == 'AGGH.MI'
    assert result.asset_items[0].bars_saved > 200
    assert repo.upserted == ['AGGH.MI']
    assert 'EUNA.DE' not in client.requested


def test_backfill_ignores_candidates_with_different_price_level(monkeypatch):
    client = _SymbolClient({
        '0GGH.L': _history(1, 4.80),
        'AGGH.SW': _history(365, 5.40),      # altra valuta / linea: prezzo troppo distante
    })
    _patch(monkeypatch, client, ['0GGH.L', 'AGGH.SW'])

    repo = _IsinRepo()
    result = HistoricalIngestionService(_FakeSettings(), repo).backfill_daily(portfolio_id=1, days=365)

    assert result.asset_items[0].provider_symbol == '0GGH.L'
    assert result.asset_items[0].bars_saved == 1
    assert repo.upserted == []


def test_backfill_uses_isin_candidate_when_provider_has_no_data(monkeypatch):
    client = _SymbolClient({
        '0GGH.L': ProviderError(provider='yfinance', operation='daily_bars', symbol='0GGH.L', reason='no_data', message='no data'),
        'AGGH.MI': _history(365, 4.81),
    })
    _patch(monkeypatch, client, ['0GGH.L', 'AGGH.MI'])

    repo = _IsinRepo()
    repo.get_latest_close_price = lambda asset_id: 4.80
    result = HistoricalIngestionService(_FakeSettings(), repo).backfill_daily(portfolio_id=1, days=365)

    assert result.errors == []
    assert result.asset_items[0].provider_symbol == 'AGGH.MI'
    assert repo.upserted == ['AGGH.MI']


def test_backfill_without_isin_keeps_original_symbol(monkeypatch):
    client = _SymbolClient({'0GGH.L': _history(1, 4.80)})
    _patch(monkeypatch, client, [])

    repo = _IsinRepo(isin=None)
    result = HistoricalIngestionService(_FakeSettings(), repo).backfill_daily(portfolio_id=1, days=365)

    assert result.asset_items[0].provider_symbol == '0GGH.L'
    assert client.requested == ['0GGH.L']


def test_backfill_uses_live_quote_as_reference_when_no_history(monkeypatch):
    class Quote:
        price = 4.80

    client = _SymbolClient({
        '0GGH.L': ProviderError(provider='yfinance', operation='daily_bars', symbol='0GGH.L', reason='no_data', message='no data'),
        'AGGH.MI': _history(365, 4.81),
    })
    client.get_quote = lambda symbol: Quote()
    _patch(monkeypatch, client, ['0GGH.L', 'AGGH.MI'])

    repo = _IsinRepo()
    result = HistoricalIngestionService(_FakeSettings(), repo).backfill_daily(portfolio_id=1, days=365)

    assert result.errors == []
    assert result.asset_items[0].provider_symbol == 'AGGH.MI'


def test_backfill_continues_when_fallback_symbol_cannot_be_persisted(monkeypatch):
    client = _SymbolClient({
        '0GGH.L': _history(1, 4.80),
        'AGGH.MI': _history(365, 4.81),
    })
    _patch(monkeypatch, client, ['0GGH.L', 'AGGH.MI'])

    repo = _IsinRepo()

    def broken_upsert(payload):
        raise RuntimeError('connection pool exhausted')

    repo.upsert_asset_provider_symbol = broken_upsert
    result = HistoricalIngestionService(_FakeSettings(), repo).backfill_daily(portfolio_id=1, days=365)

    assert result.errors == []
    assert result.asset_items[0].provider_symbol == 'AGGH.MI'
    assert result.asset_items[0].bars_saved > 200


def test_single_asset_backfill_reuses_known_close_for_fallback(monkeypatch):
    client = _SymbolClient({
        '0GGH.L': ProviderError(provider='yfinance', operation='daily_bars', symbol='0GGH.L', reason='no_data', message='no data'),
        'AGGH.MI': _history(365, 4.81),
    })
    _patch(monkeypatch, client, ['0GGH.L', 'AGGH.MI'])

    class Pricing:
        provider_symbol = '0GGH.L'

    repo = _IsinRepo()
    calls = []

    def latest_close(asset_id):
        calls.append(asset_id)
        return 4.80

    repo.get_latest_close_price = latest_close
    repo.get_asset_pricing_symbol = lambda asset_id, provider: Pricing()
    HistoricalIngestionService(_FakeSettings(), repo).backfill_single_asset(asset_id=1, portfolio_id=1, days=365)

    assert calls == [1]
    assert repo.upserted == ['AGGH.MI']
    assert len(repo.bars_rows) > 200
