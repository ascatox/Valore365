import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from ..config import Settings
from ..finance_client import is_unpriceable_on_yahoo, make_finance_client
from ..models import DailyBackfillItem, DailyBackfillResponse, FxBackfillItem
from ..price_validation import validate_fx_rate, validate_price_bar
from ..repository import PortfolioRepository

logger = logging.getLogger(__name__)


class HistoricalIngestionService:
    def __init__(self, settings: Settings, repository: PortfolioRepository) -> None:
        self.settings = settings
        self.repository = repository

    def _validate_bars(
        self,
        bars,
        asset_id: int,
        symbol: str,
        start_date,
        end_date,
        reference_close: float | None = None,
    ) -> list[dict]:
        sorted_bars = sorted(
            (b for b in bars if start_date <= b.day <= end_date),
            key=lambda b: b.day,
        )
        rows: list[dict] = []
        previous_close: float | None = reference_close
        adjusted = 0
        range_tolerance_pct = self.settings.price_validation_ohlc_range_tolerance_pct
        for bar in sorted_bars:
            vr = validate_price_bar(
                asset_id=asset_id,
                symbol=symbol,
                price_date=bar.day,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
                previous_close=previous_close,
                max_daily_change_pct=self.settings.price_validation_max_daily_change_pct,
                max_ohlc_spread_pct=self.settings.price_validation_max_ohlc_spread_pct,
                range_tolerance_pct=range_tolerance_pct,
            )
            if not vr.valid:
                continue
            if vr.adjustments:
                adjusted += 1
            rows.append({
                "price_date": bar.day,
                "open": bar.open,
                # Widen the range so stored bars are always OHLC-consistent.
                "high": max(bar.high, bar.open, bar.close),
                "low": min(bar.low, bar.open, bar.close),
                "close": bar.close,
                "volume": bar.volume,
            })
            previous_close = bar.close
        if adjusted:
            logger.info(
                "price_bars_range_adjusted asset_id=%s symbol=%s bars=%s/%s tolerance_pct=%s",
                asset_id, symbol, adjusted, len(sorted_bars), range_tolerance_pct,
            )
        return rows

    def _validate_fx_rows(self, rates, from_ccy: str, to_ccy: str, start_date, end_date) -> list[dict]:
        rows: list[dict] = []
        for fx in sorted((f for f in rates if start_date <= f.day <= end_date), key=lambda f: f.day):
            vr = validate_fx_rate(
                from_ccy=from_ccy,
                to_ccy=to_ccy,
                price_date=fx.day,
                rate=fx.rate,
                min_rate=self.settings.price_validation_fx_min_rate,
                max_rate=self.settings.price_validation_fx_max_rate,
            )
            if not vr.valid:
                continue
            rows.append({"price_date": fx.day, "rate": fx.rate})
        return rows

    def backfill_single_asset(self, *, asset_id: int, portfolio_id: int, days: int = 365, user_id: str | None = None) -> None:
        """Background backfill for a single asset (prices + FX). Never raises."""
        try:
            provider = self.settings.finance_provider.strip().lower()
            outputsize = max(30, min(days, 2000))
            end_date = date.today()
            start_date = end_date - timedelta(days=outputsize - 1)

            client = make_finance_client(self.settings)
            pricing_asset = self.repository.get_asset_pricing_symbol(asset_id, provider)
            base_currency = self.repository.get_portfolio_base_currency(portfolio_id, user_id=user_id)
            reference_close = self.repository.get_latest_close_price(asset_id)

            # Price bars
            bars = client.get_daily_bars(
                pricing_asset.provider_symbol,
                outputsize=outputsize,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
            rows = self._validate_bars(
                bars,
                asset_id,
                pricing_asset.provider_symbol,
                start_date,
                end_date,
                reference_close=reference_close,
            )
            self.repository.batch_upsert_price_bars_1d(
                asset_id=asset_id,
                provider=provider,
                rows=rows,
            )
            logger.info(
                'Single-asset backfill asset=%s bars=%s',
                pricing_asset.provider_symbol,
                len(rows),
            )

            # FX rates if needed
            quote_ccys = self.repository.get_quote_currencies_for_assets([asset_id])
            quote_ccy = quote_ccys.get(asset_id, '')
            if quote_ccy and quote_ccy.upper() != base_currency.upper():
                rates = client.get_daily_fx_rates(
                    quote_ccy,
                    base_currency,
                    outputsize=outputsize,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
                fx_rows = self._validate_fx_rows(rates, quote_ccy, base_currency, start_date, end_date)
                self.repository.batch_upsert_fx_rates_1d(
                    from_ccy=quote_ccy,
                    to_ccy=base_currency,
                    provider=provider,
                    rows=fx_rows,
                )
                logger.info(
                    'Single-asset FX backfill pair=%s/%s rates=%s',
                    quote_ccy, base_currency, len(fx_rows),
                )
        except Exception as exc:
            logger.error('Single-asset backfill failed asset_id=%s error=%s', asset_id, exc)

    def _store_backfilled_asset(self, asset, future, provider, start_date, end_date, asset_items, errors) -> None:
        try:
            bars = future.result()
            reference_close = self.repository.get_latest_close_price(asset.asset_id)
            rows = self._validate_bars(
                bars,
                asset.asset_id,
                asset.provider_symbol,
                start_date,
                end_date,
                reference_close=reference_close,
            )
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
                    bars_requested=len(bars),
                    bars_rejected=max(0, len(bars) - len(rows)),
                )
            )
        except ValueError as exc:
            errors.append(f"{asset.provider_symbol}: {exc}")
            logger.error('Daily backfill failure asset=%s error=%s', asset.provider_symbol, exc)

    def _store_backfilled_fx(self, from_ccy, base_currency, future, provider, start_date, end_date, fx_items, errors) -> None:
        try:
            rates = future.result()
            rows = self._validate_fx_rows(rates, from_ccy, base_currency, start_date, end_date)
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
                    rates_requested=len(rates),
                    rates_rejected=max(0, len(rates) - len(rows)),
                )
            )
        except ValueError as exc:
            errors.append(f"{from_ccy}/{base_currency}: {exc}")
            logger.error('Daily FX backfill failure pair=%s/%s error=%s', from_ccy, base_currency, exc)

    def backfill_daily(self, *, portfolio_id: int, days: int = 365, asset_scope: str = 'target', user_id: str | None = None) -> DailyBackfillResponse:
        provider = self.settings.finance_provider.strip().lower()
        outputsize = max(30, min(days, 2000))
        end_date = date.today()
        start_date = end_date - timedelta(days=outputsize - 1)

        client = make_finance_client(self.settings)

        pricing_assets = self.repository.get_assets_for_price_refresh(
            provider=provider,
            portfolio_id=portfolio_id,
            asset_scope=asset_scope,
            user_id=user_id,
        )
        base_currency = self.repository.get_portfolio_base_currency(portfolio_id, user_id=user_id)

        asset_items: list[DailyBackfillItem] = []
        fx_items: list[FxBackfillItem] = []
        errors: list[str] = []

        quote_ccy_by_asset = self.repository.get_quote_currencies_for_assets([a.asset_id for a in pricing_assets])

        requested_count = len(pricing_assets)
        skipped = [a for a in pricing_assets if is_unpriceable_on_yahoo(provider, a.provider_symbol)]
        if skipped:
            pricing_assets = [a for a in pricing_assets if a not in skipped]
            errors.extend(f"{a.provider_symbol}: nessun simbolo {provider} (solo ISIN)" for a in skipped)
            logger.warning(
                'Daily backfill skipped assets without provider symbol provider=%s symbols=%s',
                provider, ','.join(a.provider_symbol for a in skipped),
            )

        needed_fx = sorted({
            ccy for ccy in quote_ccy_by_asset.values() if ccy and ccy.upper() != base_currency.upper()
        })

        # Provider calls are network-bound and independent: run them
        # concurrently, then validate and write sequentially as before.
        def fetch_bars(asset):
            return client.get_daily_bars(
                asset.provider_symbol,
                outputsize=outputsize,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )

        def fetch_fx(from_ccy):
            return client.get_daily_fx_rates(
                from_ccy,
                base_currency,
                outputsize=outputsize,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )

        max_workers = max(1, self.settings.price_backfill_max_workers)
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            bar_futures = [(asset, pool.submit(fetch_bars, asset)) for asset in pricing_assets]
            fx_futures = [(ccy, pool.submit(fetch_fx, ccy)) for ccy in needed_fx]

            for asset, future in bar_futures:
                self._store_backfilled_asset(asset, future, provider, start_date, end_date, asset_items, errors)

            for from_ccy, future in fx_futures:
                self._store_backfilled_fx(from_ccy, base_currency, future, provider, start_date, end_date, fx_items, errors)

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
            assets_requested=requested_count,
            assets_refreshed=len(asset_items),
            fx_pairs_refreshed=len(fx_items),
            asset_items=asset_items,
            fx_items=fx_items,
            errors=errors,
        )
