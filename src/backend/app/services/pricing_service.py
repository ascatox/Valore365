import logging
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import httpx

from ..config import Settings
from ..finance_client import is_unpriceable_on_yahoo, make_finance_client
from ..models import PriceRefreshItem, PriceRefreshResponse
from ..price_validation import validate_quote_price
from ..repository import PortfolioRepository
from .market_hours import is_market_open

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
        market_hours_at: datetime | None = None,
    ) -> PriceRefreshResponse:
        """Scarica le quotazioni e le salva come price tick.

        ``market_hours_at`` lo passa solo lo scheduler: salta gli asset la cui
        borsa è chiusa in quell'istante. I refresh manuali aggiornano tutto.
        """
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

        if market_hours_at is not None:
            grace_minutes = self.settings.price_scheduler_after_close_grace_minutes
            open_assets = []
            closed = []
            for asset in pricing_assets:
                # Lo scheduler chiede il simbolo nudo (VWCE): la borsa si legge
                # dal simbolo mappato (VWCE.MI), altrimenti finirebbe sugli orari USA.
                market_symbol = getattr(asset, 'market_symbol', None) or asset.provider_symbol
                is_open = is_market_open(market_symbol, market_hours_at, after_close_grace_minutes=grace_minutes)
                (open_assets if is_open else closed).append(asset)
            if closed:
                pricing_assets = open_assets
                logger.info(
                    'Price refresh skipped assets with closed market provider=%s count=%s symbols=%s',
                    provider, len(closed), ','.join(a.provider_symbol for a in closed),
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

        for asset, (quote, fetch_error) in zip(pricing_assets, self._fetch_quotes(client, pricing_assets)):
            try:
                if fetch_error is not None:
                    raise fetch_error
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

    def _fetch_quotes(self, client, pricing_assets: list) -> Iterator[tuple[object | None, Exception | None]]:
        """(quote, errore) per ogni asset, nello stesso ordine di pricing_assets.

        In parallelo su finance_quote_concurrency thread; in sequenza, con la
        pausa tra un simbolo e l'altro, se finance_symbol_request_delay_seconds > 0.
        """
        delay_seconds = max(0.0, float(self.settings.finance_symbol_request_delay_seconds))
        concurrency = max(1, int(self.settings.finance_quote_concurrency))

        def fetch(asset) -> tuple[object | None, Exception | None]:
            try:
                return client.get_quote(asset.provider_symbol), None
            except (ValueError, httpx.HTTPError) as exc:
                return None, exc

        if delay_seconds > 0 or concurrency == 1 or len(pricing_assets) <= 1:
            for index, asset in enumerate(pricing_assets):
                yield fetch(asset)
                if delay_seconds > 0 and index < len(pricing_assets) - 1:
                    time.sleep(delay_seconds)
            return

        with ThreadPoolExecutor(max_workers=min(concurrency, len(pricing_assets))) as executor:
            results = list(executor.map(fetch, pricing_assets))
        yield from results
