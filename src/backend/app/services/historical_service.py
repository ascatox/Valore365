import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from ..config import Settings
from ..errors import ProviderError
from ..finance_client import is_unpriceable_on_yahoo, make_finance_client, resolve_provider_symbol_candidates
from ..models import AssetProviderSymbolCreate, DailyBackfillItem, DailyBackfillResponse, FxBackfillItem
from ..price_validation import validate_fx_rate, validate_price_bar
from ..repository import PortfolioRepository
from .market_hours import completed_sessions_after

logger = logging.getLogger(__name__)

# Sotto questa quota di giorni lavorativi coperti lo storico e' considerato insufficiente
# (es. 0GGH.L: Yahoo restituisce solo la barra odierna) e si cercano altre quotazioni via ISIN.
MIN_HISTORY_COVERAGE = 0.5
# Scarto massimo tra l'ultima chiusura nota e quella della quotazione alternativa:
# evita di passare a una linea in altra valuta o a uno strumento diverso.
FALLBACK_MAX_PRICE_GAP_PCT = 5.0


def _weekdays_between(start_date: date, end_date: date) -> int:
    days = (end_date - start_date).days + 1
    if days <= 0:
        return 0
    full_weeks, remainder = divmod(days, 7)
    count = full_weeks * 5
    for offset in range(remainder):
        if (start_date + timedelta(days=full_weeks * 7 + offset)).weekday() < 5:
            count += 1
    return count


def _last_close(bars) -> float | None:
    if not bars:
        return None
    return max(bars, key=lambda b: b.day).close


@dataclass
class DailyBarsJobResult:
    """Outcome of refresh_recent_daily_bars (the scheduler's daily bars job)."""

    requested: int = 0
    updated: list[str] = field(default_factory=list)
    no_new_bar: list[str] = field(default_factory=list)
    # no new bar although the asset's market closed a session after the last bar
    lagging: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def log_bars_outcome(
    *,
    asset_id: int,
    symbol: str,
    provider_symbol: str,
    market_symbol: str | None,
    bars_from_provider: int,
    rows: list[dict],
    previous_last_day: date | None,
    now: datetime,
    context: str,
) -> str:
    """Per-asset log of a daily bars write; returns 'updated', 'no_new_bar' or 'lagging'.

    TASK-53: a backfill that stored nothing new for an asset used to leave no
    trace (XAD1.DE stuck at 30/10 for days). Rejected bars, empty results and
    a history that lags the asset's market calendar are now logged with the
    symbol; a normal "nothing new yet" stays at debug.
    """
    rejected = max(0, bars_from_provider - len(rows))
    last_saved = max((r["price_date"] for r in rows), default=None)
    if rejected:
        logger.warning(
            'daily_bars_rejected context=%s asset_id=%s symbol=%s provider_symbol=%s rejected=%s/%s '
            '(see price_bar_rejected lines for the reason)',
            context, asset_id, symbol, provider_symbol, rejected, bars_from_provider,
        )
    if last_saved is not None and (previous_last_day is None or last_saved > previous_last_day):
        logger.debug(
            'daily_bars_updated context=%s asset_id=%s symbol=%s last_bar=%s previous_last_bar=%s',
            context, asset_id, symbol, last_saved, previous_last_day,
        )
        return 'updated'

    known_days = [d for d in (last_saved, previous_last_day) if d is not None]
    last_known = max(known_days) if known_days else None
    missed = completed_sessions_after(market_symbol or provider_symbol, last_known, now) if last_known else None
    if last_known is None or (missed or 0) >= 1:
        reason = 'nessuna barra valida dal provider' if not rows else 'il provider non ha barre piu recenti'
        logger.warning(
            'daily_bars_no_new_bar context=%s asset_id=%s symbol=%s provider_symbol=%s last_bar=%s '
            'missed_sessions=%s bars_from_provider=%s saved=%s rejected=%s reason=%s',
            context, asset_id, symbol, provider_symbol, last_known, missed, bars_from_provider,
            len(rows), rejected, reason,
        )
        return 'lagging'
    logger.debug(
        'daily_bars_no_new_bar context=%s asset_id=%s symbol=%s last_bar=%s (up to date)',
        context, asset_id, symbol, last_known,
    )
    return 'no_new_bar'


def _now_utc() -> datetime:
    return datetime.now(UTC)


def _start_of_day_utc(day: date) -> datetime:
    """Reference instant for backfills whose provider window excludes ``day`` (end bound exclusive)."""
    return datetime(day.year, day.month, day.day, tzinfo=UTC)


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

    def _has_enough_history(self, bars, start_date: date, end_date: date) -> bool:
        expected = _weekdays_between(start_date, end_date)
        if expected <= 1:
            return bool(bars)
        return len(bars) >= expected * MIN_HISTORY_COVERAGE

    def _fetch_daily_bars(
        self,
        client,
        *,
        asset_id: int,
        provider: str,
        provider_symbol: str,
        outputsize: int,
        start_date: date,
        end_date: date,
        known_close: float | None = None,
    ) -> tuple[str, list]:
        """Scarica le barre giornaliere; se lo storico e' insufficiente prova le altre quotazioni dello stesso ISIN.

        Restituisce il simbolo effettivamente usato e le barre. Se viene trovata una quotazione
        migliore, il mapping ``asset_provider_symbols`` viene aggiornato.
        """
        provider_error: ProviderError | None = None
        try:
            bars = client.get_daily_bars(
                provider_symbol,
                outputsize=outputsize,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )
        except ProviderError as exc:
            bars = []
            provider_error = exc

        if self._has_enough_history(bars, start_date, end_date):
            return provider_symbol, bars

        fallback = self._find_isin_fallback_bars(
            client,
            asset_id=asset_id,
            provider_symbol=provider_symbol,
            current_bars=bars,
            outputsize=outputsize,
            start_date=start_date,
            end_date=end_date,
            known_close=known_close,
        )
        if fallback is None:
            if provider_error is not None:
                raise provider_error
            return provider_symbol, bars

        fallback_symbol, fallback_bars = fallback
        logger.warning(
            'Insufficient history for asset_id=%s symbol=%s (%s bars): switching to %s (%s bars)',
            asset_id, provider_symbol, len(bars), fallback_symbol, len(fallback_bars),
        )
        try:
            self.repository.upsert_asset_provider_symbol(
                AssetProviderSymbolCreate(asset_id=asset_id, provider=provider, provider_symbol=fallback_symbol)
            )
        except Exception as exc:
            # Best effort: un errore DB qui non deve far fallire il backfill dell'asset ne' del batch.
            logger.warning(
                'Unable to persist fallback provider symbol asset_id=%s symbol=%s error=%s',
                asset_id, fallback_symbol, exc,
            )
        return fallback_symbol, fallback_bars

    def _find_isin_fallback_bars(
        self,
        client,
        *,
        asset_id: int,
        provider_symbol: str,
        current_bars: list,
        outputsize: int,
        start_date: date,
        end_date: date,
        known_close: float | None = None,
    ) -> tuple[str, list] | None:
        try:
            isin = self.repository.get_asset(asset_id).isin
        except Exception:
            return None
        if not isin:
            return None

        reference_close = _last_close(current_bars) or known_close
        if not reference_close and known_close is None:
            reference_close = self.repository.get_latest_close_price(asset_id)
        if not reference_close:
            # Nessuna barra ne' storico in DB: usa la quotazione live del simbolo corrente.
            try:
                reference_close = client.get_quote(provider_symbol).price
            except Exception:
                reference_close = None
        if not reference_close or reference_close <= 0:
            return None

        current_symbol = provider_symbol.strip().upper()
        base_symbol = current_symbol.split('.', 1)[0]
        best: tuple[str, list] | None = None
        for candidate in resolve_provider_symbol_candidates(base_symbol, isin):
            if candidate == current_symbol:
                continue
            try:
                candidate_bars = client.get_daily_bars(
                    candidate,
                    outputsize=outputsize,
                    start_date=start_date.isoformat(),
                    end_date=end_date.isoformat(),
                )
            except Exception:
                continue
            if len(candidate_bars) <= len(current_bars):
                continue
            candidate_close = _last_close(candidate_bars)
            if not candidate_close:
                continue
            gap_pct = abs(candidate_close - reference_close) / reference_close * 100
            if gap_pct > FALLBACK_MAX_PRICE_GAP_PCT:
                continue
            # I candidati sono gia' ordinati per priorita': il primo con storico sufficiente vince.
            if self._has_enough_history(candidate_bars, start_date, end_date):
                return candidate, candidate_bars
            if best is None or len(candidate_bars) > len(best[1]):
                best = (candidate, candidate_bars)
        return best

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
            previous_last_day = self._previous_last_days([asset_id]).get(asset_id)

            # Price bars
            used_symbol, bars = self._fetch_daily_bars(
                client,
                asset_id=asset_id,
                provider=provider,
                provider_symbol=pricing_asset.provider_symbol,
                outputsize=outputsize,
                start_date=start_date,
                end_date=end_date,
                known_close=reference_close,
            )
            rows = self._validate_bars(
                bars,
                asset_id,
                used_symbol,
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
                used_symbol,
                len(rows),
            )
            log_bars_outcome(
                asset_id=asset_id,
                symbol=used_symbol,
                provider_symbol=used_symbol,
                market_symbol=used_symbol,
                bars_from_provider=len([b for b in bars if start_date <= b.day <= end_date]),
                rows=rows,
                previous_last_day=previous_last_day,
                now=_start_of_day_utc(end_date),
                context='single_asset',
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

    def _previous_last_days(self, asset_ids: list[int]) -> dict[int, date]:
        """Latest stored bar date per asset (one query); {} for repositories without it."""
        getter = getattr(self.repository, 'get_latest_daily_bars', None)
        if getter is None:
            return {}
        try:
            return {aid: day for aid, (day, _close) in (getter(asset_ids) or {}).items()}
        except Exception as exc:
            logger.warning('Unable to read latest daily bars error=%s', exc)
            return {}

    def _store_backfilled_asset(
        self, asset, future, provider, start_date, end_date, asset_items, errors, previous_last_day=None,
    ) -> None:
        try:
            used_symbol, bars = future.result()
            reference_close = self.repository.get_latest_close_price(asset.asset_id)
            rows = self._validate_bars(
                bars,
                asset.asset_id,
                used_symbol,
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
                    provider_symbol=used_symbol,
                    bars_saved=len(rows),
                    bars_requested=len(bars),
                    bars_rejected=max(0, len(bars) - len(rows)),
                )
            )
            log_bars_outcome(
                asset_id=asset.asset_id,
                symbol=asset.symbol,
                provider_symbol=used_symbol,
                market_symbol=getattr(asset, 'market_symbol', None) or used_symbol,
                bars_from_provider=len([b for b in bars if start_date <= b.day <= end_date]),
                rows=rows,
                previous_last_day=previous_last_day,
                now=_start_of_day_utc(end_date),
                context='backfill_daily',
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
        previous_last_days = self._previous_last_days([a.asset_id for a in pricing_assets])

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
            return self._fetch_daily_bars(
                client,
                asset_id=asset.asset_id,
                provider=provider,
                provider_symbol=asset.provider_symbol,
                outputsize=outputsize,
                start_date=start_date,
                end_date=end_date,
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
                self._store_backfilled_asset(
                    asset, future, provider, start_date, end_date, asset_items, errors,
                    previous_last_day=previous_last_days.get(asset.asset_id),
                )

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

    def refresh_recent_daily_bars(self, *, days: int = 10, now: datetime | None = None) -> DailyBarsJobResult:
        """Daily bars of the last ``days`` calendar days for every active asset held in any portfolio.

        Run by the scheduler after the markets close (TASK-53): until then bars
        were written only by manual backfills, new transactions or the asset
        page. Today's session is included (the job runs after the close). DB
        access is two short reads up front and one short write per asset;
        provider calls run on price_backfill_max_workers threads with no
        connection held. Prices only: FX rates keep their own paths.
        """
        now = now or _now_utc()
        provider = self.settings.finance_provider.strip().lower()
        window = max(2, int(days))
        today = now.astimezone(UTC).date()
        start_date = today - timedelta(days=window - 1)
        # Yahoo's end bound is exclusive: tomorrow, so today's close is included.
        fetch_end = today + timedelta(days=1)

        assets = self.repository.get_held_assets_for_daily_bars(provider)
        result = DailyBarsJobResult(requested=len(assets))
        skipped = [a for a in assets if is_unpriceable_on_yahoo(provider, a.provider_symbol)]
        if skipped:
            assets = [a for a in assets if a not in skipped]
            result.skipped = [a.provider_symbol for a in skipped]
        if not assets:
            return result

        latest = self.repository.get_latest_daily_bars([a.asset_id for a in assets])
        client = make_finance_client(self.settings)

        def fetch(asset):
            return self._fetch_daily_bars(
                client,
                asset_id=asset.asset_id,
                provider=provider,
                provider_symbol=asset.provider_symbol,
                outputsize=window,
                start_date=start_date,
                end_date=fetch_end,
                known_close=(latest.get(asset.asset_id) or (None, None))[1],
            )

        max_workers = max(1, int(self.settings.price_backfill_max_workers))
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [(asset, pool.submit(fetch, asset)) for asset in assets]
            for asset, future in futures:
                previous_day, previous_close = latest.get(asset.asset_id) or (None, None)
                try:
                    used_symbol, bars = future.result()
                    rows = self._validate_bars(
                        bars, asset.asset_id, used_symbol, start_date, today, reference_close=previous_close,
                    )
                    self.repository.batch_upsert_price_bars_1d(asset_id=asset.asset_id, provider=provider, rows=rows)
                except Exception as exc:
                    result.failed.append(asset.provider_symbol)
                    logger.warning(
                        'daily_bars_failed context=daily_job asset_id=%s symbol=%s provider_symbol=%s last_bar=%s error=%s',
                        asset.asset_id, asset.symbol, asset.provider_symbol, previous_day, exc,
                    )
                    continue
                outcome = log_bars_outcome(
                    asset_id=asset.asset_id,
                    symbol=asset.symbol,
                    provider_symbol=used_symbol,
                    market_symbol=asset.market_symbol or used_symbol,
                    bars_from_provider=len([b for b in bars if start_date <= b.day <= today]),
                    rows=rows,
                    previous_last_day=previous_day,
                    now=now,
                    context='daily_job',
                )
                {'updated': result.updated, 'lagging': result.lagging}.get(outcome, result.no_new_bar).append(
                    asset.provider_symbol
                )
        return result
