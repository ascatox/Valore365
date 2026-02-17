import logging
import time

import httpx

from .config import Settings
from .finance_client import TwelveDataClient
from .models import PriceRefreshItem, PriceRefreshResponse
from .repository import PortfolioRepository

logger = logging.getLogger(__name__)


class PriceIngestionService:
    def __init__(self, settings: Settings, repository: PortfolioRepository) -> None:
        self.settings = settings
        self.repository = repository

    def refresh_prices(self, portfolio_id: int | None = None) -> PriceRefreshResponse:
        provider = self.settings.finance_provider.strip().lower()
        if provider != 'twelvedata':
            raise ValueError(f"Provider non supportato: {provider}")

        client = TwelveDataClient(
            base_url=self.settings.finance_api_base_url,
            api_key=self.settings.finance_api_key,
            timeout_seconds=self.settings.finance_request_timeout_seconds,
            max_retries=self.settings.finance_max_retries,
            retry_backoff_seconds=self.settings.finance_retry_backoff_seconds,
        )

        pricing_assets = self.repository.get_assets_for_price_refresh(provider=provider, portfolio_id=portfolio_id)

        logger.info(
            'Start price refresh provider=%s portfolio_id=%s assets=%s',
            provider,
            portfolio_id,
            len(pricing_assets),
        )

        items: list[PriceRefreshItem] = []
        errors: list[str] = []
        delay_seconds = max(0.0, float(self.settings.finance_symbol_request_delay_seconds))

        for index, asset in enumerate(pricing_assets):
            try:
                quote = client.get_quote(asset.provider_symbol)
                self.repository.save_price_tick(
                    asset_id=asset.asset_id,
                    provider=provider,
                    ts=quote.ts,
                    last=quote.price,
                    bid=quote.bid,
                    ask=quote.ask,
                    volume=quote.volume,
                )
                items.append(
                    PriceRefreshItem(
                        asset_id=asset.asset_id,
                        symbol=asset.symbol,
                        provider_symbol=asset.provider_symbol,
                        price=quote.price,
                        ts=quote.ts,
                    )
                )
            except (ValueError, httpx.HTTPError) as exc:
                error_message = f"{asset.provider_symbol}: {exc}"
                errors.append(error_message)
                logger.error('Price refresh failure provider=%s asset=%s error=%s', provider, asset.provider_symbol, exc)

            if delay_seconds > 0 and index < len(pricing_assets) - 1:
                time.sleep(delay_seconds)

        logger.info(
            'End price refresh provider=%s requested=%s refreshed=%s failed=%s',
            provider,
            len(pricing_assets),
            len(items),
            len(errors),
        )

        return PriceRefreshResponse(
            provider=provider,
            requested_assets=len(pricing_assets),
            refreshed_assets=len(items),
            failed_assets=len(errors),
            items=items,
            errors=errors,
        )
