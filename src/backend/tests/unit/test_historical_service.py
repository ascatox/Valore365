from datetime import date

from app.historical_service import HistoricalIngestionService
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


class _FakeSettings:
    finance_provider = 'yfinance'
    price_validation_max_daily_change_pct = 50.0
    price_validation_max_ohlc_spread_pct = 100.0
    price_validation_fx_min_rate = 0.0001
    price_validation_fx_max_rate = 10000.0


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
    import app.historical_service as mod

    monkeypatch.setattr(mod, 'make_finance_client', lambda _: _FakeClient())

    repo = _FakeRepo()
    service = HistoricalIngestionService(_FakeSettings(), repo)

    result = service.backfill_daily(portfolio_id=1, days=365)
    assert isinstance(result, DailyBackfillResponse)
    assert result.assets_refreshed == 1
    assert result.fx_pairs_refreshed == 1
    assert len(repo.bars_rows) == 1
    assert len(repo.fx_rows) == 1


def test_backfill_daily_rejects_high_less_than_low(monkeypatch):
    import app.historical_service as mod

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
    import app.historical_service as mod

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
    import app.historical_service as mod

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
