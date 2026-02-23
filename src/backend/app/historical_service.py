import logging
from datetime import date, timedelta

from .config import Settings
from .finance_client import TwelveDataClient
from .models import DailyBackfillItem, DailyBackfillResponse, FxBackfillItem
from .repository import PortfolioRepository

logger = logging.getLogger(__name__)


class HistoricalIngestionService:
    def __init__(self, settings: Settings, repository: PortfolioRepository) -> None:
        self.settings = settings
        self.repository = repository

    def backfill_daily(self, *, portfolio_id: int, days: int = 365, asset_scope: str = 'target') -> DailyBackfillResponse:
        provider = self.settings.finance_provider.strip().lower()
        if provider != 'twelvedata':
            raise ValueError(f"Provider non supportato: {provider}")

        outputsize = max(30, min(days, 2000))
        end_date = date.today()
        start_date = end_date - timedelta(days=outputsize - 1)

        client = TwelveDataClient(
            base_url=self.settings.finance_api_base_url,
            api_key=self.settings.finance_api_key,
            timeout_seconds=self.settings.finance_request_timeout_seconds,
            max_retries=self.settings.finance_max_retries,
            retry_backoff_seconds=self.settings.finance_retry_backoff_seconds,
        )

        pricing_assets = self.repository.get_assets_for_price_refresh(
            provider=provider,
            portfolio_id=portfolio_id,
            asset_scope=asset_scope,
        )
        base_currency = self.repository.get_portfolio_base_currency(portfolio_id)

        asset_items: list[DailyBackfillItem] = []
        fx_items: list[FxBackfillItem] = []
        errors: list[str] = []

        quote_ccy_by_asset = self.repository.get_quote_currencies_for_assets([a.asset_id for a in pricing_assets])

        for asset in pricing_assets:
            try:
                bars = client.get_daily_bars(
                    asset.provider_symbol,
                    outputsize=outputsize,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
                rows = [
                    {
                        "price_date": bar.day,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                    if start_date <= bar.day <= end_date
                ]
                self.repository.batch_upsert_price_bars_1d(
                    asset_id=asset.asset_id,
                    provider=provider,
                    rows=rows,
                )
                asset_items.append(
                    DailyBackfillItem(
                        asset_id=asset.asset_id,
                        symbol=asset.symbol,
                        provider_symbol=asset.provider_symbol,
                        bars_saved=len(rows),
                    )
                )
            except ValueError as exc:
                msg = f"{asset.provider_symbol}: {exc}"
                errors.append(msg)
                logger.error('Daily backfill failure asset=%s error=%s', asset.provider_symbol, exc)

        needed_fx = sorted({
            ccy for ccy in quote_ccy_by_asset.values() if ccy and ccy.upper() != base_currency.upper()
        })
        for from_ccy in needed_fx:
            try:
                rates = client.get_daily_fx_rates(
                    from_ccy,
                    base_currency,
                    outputsize=outputsize,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
                rows = [
                    {
                        "price_date": fx.day,
                        "rate": fx.rate,
                    }
                    for fx in rates
                    if start_date <= fx.day <= end_date
                ]
                self.repository.batch_upsert_fx_rates_1d(
                    from_ccy=from_ccy,
                    to_ccy=base_currency,
                    provider=provider,
                    rows=rows,
                )
                fx_items.append(
                    FxBackfillItem(
                        from_currency=from_ccy,
                        to_currency=base_currency,
                        rates_saved=len(rows),
                    )
                )
            except ValueError as exc:
                msg = f"{from_ccy}/{base_currency}: {exc}"
                errors.append(msg)
                logger.error('Daily FX backfill failure pair=%s/%s error=%s', from_ccy, base_currency, exc)

        logger.info(
            'Daily backfill completed portfolio=%s asset_scope=%s assets=%s fx_pairs=%s errors=%s',
            portfolio_id,
            asset_scope,
            len(asset_items),
            len(fx_items),
            len(errors),
        )

        return DailyBackfillResponse(
            provider=provider,
            portfolio_id=portfolio_id,
            start_date=start_date,
            end_date=end_date,
            assets_requested=len(pricing_assets),
            assets_refreshed=len(asset_items),
            fx_pairs_refreshed=len(fx_items),
            asset_items=asset_items,
            fx_items=fx_items,
            errors=errors,
        )
