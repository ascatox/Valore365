import logging
import time

import httpx

from ..config import Settings
from ..finance_client import is_unpriceable_on_yahoo, make_finance_client
from ..models import PriceRefreshItem, PriceRefreshResponse
from ..price_validation import validate_quote_price
from ..repository import PortfolioRepository

logger = logging.getLogger(__name__)


class PriceIngestionService:
    def __init__(self, settings: Settings, repository: PortfolioRepository) -> None:
        self.settings = settings
        self.repository = repository

    def refresh_prices(
        self,
        portfolio_id: int | None = None,
        asset_scope: str = 'target',
        user_id: str | None = None,
        prefer_symbol_then_isin: bool = False,
    ) -> PriceRefreshResponse:
        provider = self.settings.finance_provider.strip().lower()
        client = make_finance_client(self.settings)

        try:
            pricing_assets = self.repository.get_assets_for_price_refresh(
                provider=provider,
                portfolio_id=portfolio_id,
                asset_scope=asset_scope,
                user_id=user_id,
                prefer_symbol_then_isin=prefer_symbol_then_isin,
            )
        except TypeError:
            # Backward compatibility for test doubles/older repository signatures.
            pricing_assets = self.repository.get_assets_for_price_refresh(
                provider=provider,
                portfolio_id=portfolio_id,
                asset_scope=asset_scope,
                user_id=user_id,
            )

        requested_count = len(pricing_assets)
        errors: list[str] = []
        skipped = [a for a in pricing_assets if is_unpriceable_on_yahoo(provider, a.provider_symbol)]
        if skipped:
            pricing_assets = [a for a in pricing_assets if a not in skipped]
            errors.extend(f"{a.provider_symbol}: nessun simbolo {provider} (solo ISIN)" for a in skipped)
            logger.warning(
                'Price refresh skipped assets without provider symbol provider=%s symbols=%s',
                provider, ','.join(a.provider_symbol for a in skipped),
            )

        logger.info(
            'Start price refresh provider=%s portfolio_id=%s asset_scope=%s assets=%s',
            provider,
            portfolio_id,
            asset_scope,
            len(pricing_assets),
        )

        items: list[PriceRefreshItem] = []
        # Ticks are collected here and written once after the provider calls
        # finish, so the refresh holds a connection for a single short
        # transaction rather than once per asset across the whole network run.
        pending_ticks: list[dict] = []
        delay_seconds = max(0.0, float(self.settings.finance_symbol_request_delay_seconds))

        for index, asset in enumerate(pricing_assets):
            try:
                quote = client.get_quote(asset.provider_symbol)
                vr = validate_quote_price(
                    asset_id=asset.asset_id,
                    symbol=asset.provider_symbol,
                    price=quote.price,
                    min_price=self.settings.price_validation_min_price,
                )
                if not vr.valid:
                    errors.append(f"{asset.provider_symbol}: rejected - {vr.rejected_reason}")
                    continue
                pending_ticks.append({
                    "asset_id": asset.asset_id,
                    "provider": provider,
                    "ts": quote.ts,
                    "last": quote.price,
                    "bid": quote.bid,
                    "ask": quote.ask,
                    "volume": quote.volume,
                    "previous_close": getattr(quote, 'previous_close', None),
                })
                items.append(
                    PriceRefreshItem(
                        asset_id=asset.asset_id,
                        symbol=asset.symbol,
                        provider_symbol=asset.provider_symbol,
                        price=quote.price,
                        ts=quote.ts,
                        quote_source=getattr(quote, 'source', None),
                        is_realtime=getattr(quote, 'is_realtime', True),
                        is_fallback=getattr(quote, 'is_fallback', False),
                        stale=getattr(quote, 'stale', False),
                        warning=getattr(quote, 'warning', None),
                    )
                )
            except (ValueError, httpx.HTTPError) as exc:
                error_message = f"{asset.provider_symbol}: {exc}"
                errors.append(error_message)
                logger.error('Price refresh failure provider=%s asset=%s error=%s', provider, asset.provider_symbol, exc)

            if delay_seconds > 0 and index < len(pricing_assets) - 1:
                time.sleep(delay_seconds)

        self.repository.save_price_ticks(pending_ticks)

        logger.info(
            'End price refresh provider=%s requested=%s refreshed=%s failed=%s',
            provider,
            requested_count,
            len(items),
            len(errors),
        )

        return PriceRefreshResponse(
            provider=provider,
            requested_assets=requested_count,
            refreshed_assets=len(items),
            failed_assets=len(errors),
            items=items,
            errors=errors,
        )
