import logging
import threading
import time
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime

import httpx

from ..config import Settings
from ..finance_client import is_unpriceable_on_yahoo, make_finance_client
from ..models import PriceRefreshItem, PriceRefreshResponse
from ..price_validation import validate_quote_price
from ..repository import PortfolioRepository
from .market_hours import is_market_open

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Current instant for the repeated-timestamp check (patched in tests)."""
    return datetime.now(UTC)


class PriceIngestionService:
    def __init__(self, settings: Settings, repository: PortfolioRepository) -> None:
        self.settings = settings
        self.repository = repository
        # TASK-53: consecutive refreshes in which an asset's quote came back
        # with a market timestamp not newer than the stored one, and the day
        # its warning was last logged (one warning per asset per day).
        self._unchanged_ts_lock = threading.Lock()
        self._unchanged_ts_streak: dict[int, int] = {}
        self._unchanged_ts_warned: dict[int, date] = {}

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

        latest_tick_ts = self._latest_tick_ts(pricing_assets, provider)
        check_at = market_hours_at or _utcnow()
        unchanged_ts_symbols: list[str] = []

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
                if self._is_unchanged_ts(asset, quote, latest_tick_ts.get(asset.asset_id), check_at):
                    unchanged_ts_symbols.append(asset.provider_symbol)
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
            unchanged_ts_symbols=unchanged_ts_symbols,
        )

    def _latest_tick_ts(self, pricing_assets: list, provider: str) -> dict[int, datetime]:
        """Stored latest tick ts per asset, read before the provider calls (one short query)."""
        getter = getattr(self.repository, 'get_latest_tick_ts', None)
        if getter is None or not pricing_assets:
            return {}
        try:
            return getter([a.asset_id for a in pricing_assets], provider) or {}
        except Exception as exc:
            logger.warning('Unable to read latest tick timestamps provider=%s error=%s', provider, exc)
            return {}

    def _is_unchanged_ts(self, asset, quote, stored_ts: datetime | None, now: datetime) -> bool:
        """True when the provider repeats a market timestamp while it should be moving (TASK-53).

        The tick ts is the provider's market timestamp, so a quote that does not
        move upserts the same (asset, provider, ts) key: nothing new is stored
        and, before this check, nothing was logged (XAD1.DE). Counted when the
        asset's market is open, or after price_unchanged_ts_warn_after
        refreshes in a row; the warning is logged once per asset per day.
        """
        quote_ts = getattr(quote, 'ts', None)
        if not isinstance(quote_ts, datetime) or not isinstance(stored_ts, datetime):
            return False
        if quote_ts.tzinfo is None:
            quote_ts = quote_ts.replace(tzinfo=UTC)
        if stored_ts.tzinfo is None:
            stored_ts = stored_ts.replace(tzinfo=UTC)
        asset_id = asset.asset_id
        with self._unchanged_ts_lock:
            if quote_ts > stored_ts:
                self._unchanged_ts_streak.pop(asset_id, None)
                return False
            streak = self._unchanged_ts_streak.get(asset_id, 0) + 1
            self._unchanged_ts_streak[asset_id] = streak
            market_symbol = getattr(asset, 'market_symbol', None) or asset.provider_symbol
            market_open = is_market_open(market_symbol, now, after_close_grace_minutes=0)
            warn_after = max(1, int(getattr(self.settings, 'price_unchanged_ts_warn_after', 3)))
            if not market_open and streak < warn_after:
                return False
            today = now.astimezone(UTC).date()
            first_today = self._unchanged_ts_warned.get(asset_id) != today
            self._unchanged_ts_warned[asset_id] = today
        log = logger.warning if first_today else logger.debug
        log(
            'price_unchanged_ts asset_id=%s symbol=%s market_symbol=%s ts=%s stored_ts=%s streak=%s market_open=%s source=%s',
            asset_id, asset.provider_symbol, market_symbol, quote_ts.isoformat(), stored_ts.isoformat(),
            streak, market_open, getattr(quote, 'source', None),
        )
        return True

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
