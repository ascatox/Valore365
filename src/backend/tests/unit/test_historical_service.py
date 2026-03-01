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


class _FakeClient:
    def get_daily_bars(self, symbol: str, outputsize: int = 365, *, start_date=None, end_date=None, **kwargs):
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
