import logging
import math
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime, timedelta

from sqlalchemy import text

from ..models import (
    AllocationItem,
    IntradayTimeseriesPoint,
    PortfolioSummary,
    TimeSeriesPoint,
)
from ._base import PositionDelta, _finite


class SummaryMixin:
    def get_summary(self, portfolio_id: int, user_id: str) -> PortfolioSummary:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")

        current_cash_balance = self.get_current_cash_balance_value(portfolio_id, user_id)
        positions = self.get_positions(portfolio_id, user_id)
        market_value = sum(p.market_value for p in positions)
        cost_basis = sum(p.quantity * p.avg_cost for p in positions)
        pl = market_value - cost_basis
        pl_pct = (pl / cost_basis * 100.0) if cost_basis else 0.0
        day_change = 0.0
        day_change_pct = 0.0

        if positions:
            asset_ids = [p.asset_id for p in positions]
            qty_by_asset = {p.asset_id: p.quantity for p in positions}

            with self.engine.begin() as conn:
                asset_meta = self._get_asset_meta(conn, asset_ids)
                rows = conn.execute(
                    text(
                        """
                        with ranked_daily as (
                            select
                                asset_id,
                                price_date,
                                close::float8 as close,
                                row_number() over (partition by asset_id order by price_date desc) as rn
                            from price_bars_1d
                            where asset_id = any(:asset_ids)
                        )
                        select asset_id, price_date, close, rn
                        from ranked_daily
                        where rn <= 2
                        order by asset_id asc, rn asc
                        """
                    ),
                    {"asset_ids": asset_ids},
                ).mappings().all()

                daily_by_asset: dict[int, list[tuple[date, float]]] = defaultdict(list)
                for row in rows:
                    daily_by_asset[int(row["asset_id"])].append((row["price_date"], float(row["close"])))

                fx_currencies = sorted(
                    {
                        meta.quote_currency
                        for meta in asset_meta.values()
                        if meta.quote_currency != portfolio.base_currency
                    }
                )
                fx_rows = []
                if fx_currencies:
                    fx_rows = conn.execute(
                        text(
                            """
                            select from_ccy, price_date, rate::float8 as rate
                            from fx_rates_1d
                            where from_ccy = any(:from_ccy)
                              and to_ccy = :to_ccy
                            order by from_ccy asc, price_date asc
                            """
                        ),
                        {"from_ccy": fx_currencies, "to_ccy": portfolio.base_currency},
                    ).mappings().all()

            fx_series: dict[str, list[tuple[date, float]]] = defaultdict(list)
            for row in fx_rows:
                fx_series[str(row["from_ccy"])].append((row["price_date"], float(row["rate"])))
            fx_dates = {ccy: [d for d, _ in series] for ccy, series in fx_series.items()}

            def fx_rate_on_or_before(currency: str, day: date | None) -> float | None:
                if currency == portfolio.base_currency:
                    return 1.0
                if day is None:
                    return None
                series = fx_series.get(currency)
                dates = fx_dates.get(currency)
                if not series or not dates:
                    return None
                idx = bisect_right(dates, day) - 1
                if idx < 0:
                    return None
                return series[idx][1]

            _log = logging.getLogger(__name__)

            # Fetch the latest tick snapshot per asset. When available, use tick last/previous_close
            # for day-change so current and previous prices come from the same quote source.
            tick_last: dict[int, float] = {}
            tick_prev_close: dict[int, float] = {}
            tick_day_by_asset: dict[int, date] = {}
            with self.engine.begin() as conn2:
                tick_rows = conn2.execute(
                    text(
                        """
                        select distinct on (asset_id)
                            asset_id,
                            ts::date as tick_date,
                            last::float8 as last,
                            previous_close::float8 as previous_close
                        from price_ticks
                        where asset_id = any(:asset_ids)
                        order by asset_id, ts desc
                        """
                    ),
                    {"asset_ids": asset_ids},
                ).mappings().all()
            for r in tick_rows:
                asset_id = int(r["asset_id"])
                tick_day = r.get("tick_date")
                if isinstance(tick_day, date):
                    tick_day_by_asset[asset_id] = tick_day
                last = r.get("last")
                if last is not None:
                    last_value = float(last)
                    if math.isfinite(last_value):
                        tick_last[asset_id] = last_value
                prev_close = r.get("previous_close")
                if prev_close is not None:
                    prev_close_value = float(prev_close)
                    if math.isfinite(prev_close_value):
                        tick_prev_close[asset_id] = prev_close_value

            previous_market_value = 0.0
            for asset_id, quantity in qty_by_asset.items():
                series = daily_by_asset.get(asset_id, [])
                latest_day = series[0][0] if series else None
                latest_close = series[0][1] if series else None

                current_quote: float | None = tick_last.get(asset_id)
                current_day: date | None = tick_day_by_asset.get(asset_id)
                if current_quote is None and latest_close is not None:
                    current_quote = latest_close
                    current_day = latest_day

                # Prefer yFinance previous_close, fall back to penultimate daily bar.
                prev_close: float | None = tick_prev_close.get(asset_id)
                prev_day: date | None = None

                if prev_close is None:
                    if len(series) < 2:
                        _log.warning("day_change: asset %s has only %d bars in price_bars_1d and no tick previous_close, skipping", asset_id, len(series))
                        continue
                    prev_day, prev_close = series[1]
                    if latest_day == prev_day:
                        _log.warning("day_change: asset %s latest_day==prev_day (%s), skipping", asset_id, latest_day)
                        continue
                    if current_quote is None or current_day is None:
                        current_quote = latest_close
                        current_day = latest_day
                elif len(series) >= 2:
                    prev_day = series[1][0]
                elif latest_day is not None:
                    prev_day = latest_day
                else:
                    prev_day = current_day or date.today()

                meta = asset_meta.get(asset_id)
                if meta is None:
                    _log.warning("day_change: asset %s has no meta, skipping", asset_id)
                    continue
                current_fx = fx_rate_on_or_before(meta.quote_currency, current_day)
                prev_fx = fx_rate_on_or_before(meta.quote_currency, prev_day)
                if current_quote is None or current_day is None or current_fx is None:
                    _log.warning("day_change: asset %s no current quote/fx for %s on %s, skipping", asset_id, meta.quote_currency, current_day)
                    continue
                if prev_fx is None:
                    _log.warning("day_change: asset %s no FX rate for %s on %s, skipping", asset_id, meta.quote_currency, prev_day)
                    continue
                current_price_base = current_quote * current_fx
                previous_price_base = prev_close * prev_fx
                if not math.isfinite(current_price_base) or not math.isfinite(previous_price_base):
                    _log.warning("day_change: asset %s has NaN/Inf price (curr=%.4f prev=%.4f), skipping", asset_id, current_price_base, previous_price_base)
                    continue
                _log.info("day_change: asset %s qty=%.4f curr=%.4f prev=%.4f (quote=%.4f prev_close=%.4f fx=%.4f/%.4f) dates=%s→%s",
                          asset_id, quantity, current_price_base, previous_price_base, current_quote, prev_close, current_fx, prev_fx, prev_day, current_day)
                day_change += quantity * (current_price_base - previous_price_base)
                previous_market_value += quantity * previous_price_base

            if previous_market_value > 0:
                day_change_pct = (day_change / previous_market_value) * 100.0

        return PortfolioSummary(
            portfolio_id=portfolio_id,
            base_currency=portfolio.base_currency,
            market_value=round(_finite(market_value), 2),
            cost_basis=round(_finite(cost_basis), 2),
            unrealized_pl=round(_finite(pl), 2),
            unrealized_pl_pct=round(_finite(pl_pct), 2),
            day_change=round(_finite(day_change), 2),
            day_change_pct=round(_finite(day_change_pct), 2),
            cash_balance=current_cash_balance,
        )

    def get_intraday_timeseries(self, portfolio_id: int, user_id: str, finance_client) -> list[IntradayTimeseriesPoint]:
        """Compute portfolio market value at hourly intervals using yFinance intraday bars."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")

            tx_rows = conn.execute(
                text(
                    """
                    select asset_id, side, quantity::float8 as quantity
                    from transactions
                    where portfolio_id = :portfolio_id
                      and side in ('buy', 'sell')
                      and asset_id is not null
                    order by trade_at asc, id asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            if not tx_rows:
                return []

            holdings: dict[int, float] = defaultdict(float)
            for row in tx_rows:
                aid = int(row["asset_id"])
                qty = float(row["quantity"])
                if str(row["side"]) == "buy":
                    holdings[aid] += qty
                else:
                    holdings[aid] -= qty

            # Only keep assets with positive holdings
            holdings = {aid: qty for aid, qty in holdings.items() if qty > 1e-9}
            if not holdings:
                return []

            asset_ids = sorted(holdings.keys())
            asset_meta = self._get_asset_meta(conn, asset_ids)

            # Get provider symbols for yFinance calls
            provider_rows = conn.execute(
                text(
                    """
                    select a.id as asset_id,
                           coalesce(aps.provider_symbol, a.symbol) as provider_symbol
                    from assets a
                    left join asset_provider_symbols aps
                      on aps.asset_id = a.id and aps.provider = 'yfinance'
                    where a.id = any(:asset_ids)
                    """
                ),
                {"asset_ids": asset_ids},
            ).mappings().all()
            provider_by_asset = {int(r["asset_id"]): str(r["provider_symbol"]) for r in provider_rows}

            # Get latest FX rates for currency conversion
            base_ccy = portfolio.base_currency
            fx_currencies = sorted(
                {meta.quote_currency for meta in asset_meta.values() if meta.quote_currency != base_ccy}
            )
            fx_rate_map: dict[str, float] = {}
            if fx_currencies:
                fx_rows = conn.execute(
                    text(
                        """
                        select distinct on (from_ccy) from_ccy, rate::float8 as rate
                        from fx_rates_1d
                        where from_ccy = any(:from_ccy) and to_ccy = :to_ccy
                        order by from_ccy, price_date desc
                        """
                    ),
                    {"from_ccy": fx_currencies, "to_ccy": base_ccy},
                ).mappings().all()
                for r in fx_rows:
                    fx_rate_map[str(r["from_ccy"])] = float(r["rate"])

        # Fetch intraday bars in parallel
        _log = logging.getLogger(__name__)
        bars_by_asset: dict[int, list] = {}

        def fetch_bars(asset_id: int) -> tuple[int, list]:
            symbol = provider_by_asset.get(asset_id, asset_meta[asset_id].symbol)
            try:
                return asset_id, finance_client.get_intraday_bars(symbol, period='1d', interval='1h')
            except Exception as exc:
                _log.warning("intraday_timeseries: failed to fetch %s: %s", symbol, exc)
                return asset_id, []

        with ThreadPoolExecutor(max_workers=min(len(asset_ids), 10)) as executor:
            futures = [executor.submit(fetch_bars, aid) for aid in asset_ids]
            for future in as_completed(futures):
                aid, bars = future.result()
                if bars:
                    bars_by_asset[aid] = bars

        if not bars_by_asset:
            return []

        # Collect all unique timestamps across all assets
        all_timestamps: set[datetime] = set()
        for bars in bars_by_asset.values():
            for bar in bars:
                all_timestamps.add(bar.ts)
        sorted_ts = sorted(all_timestamps)

        # For each timestamp, compute portfolio market value
        # Build price lookup: asset_id -> {ts: close}
        price_lookup: dict[int, dict[datetime, float]] = defaultdict(dict)
        for aid, bars in bars_by_asset.items():
            for bar in bars:
                price_lookup[aid][bar.ts] = bar.close

        cash = self.get_current_cash_balance_value(portfolio_id, user_id)
        points: list[IntradayTimeseriesPoint] = []

        for ts in sorted_ts:
            mv = cash
            for aid, qty in holdings.items():
                prices = price_lookup.get(aid)
                if not prices:
                    continue
                # Use this timestamp's price, or the latest available before it
                close = prices.get(ts)
                if close is None:
                    # Find closest earlier timestamp for this asset
                    earlier = [t for t in sorted(prices.keys()) if t <= ts]
                    if earlier:
                        close = prices[earlier[-1]]
                    else:
                        continue
                meta = asset_meta.get(aid)
                fx = 1.0
                if meta and meta.quote_currency != base_ccy:
                    fx = fx_rate_map.get(meta.quote_currency, 1.0)
                mv += qty * close * fx

            points.append(IntradayTimeseriesPoint(
                ts=ts.strftime('%Y-%m-%dT%H:%M:%S'),
                market_value=round(mv, 2),
            ))

        return points

    def get_timeseries(self, portfolio_id: int, range_value: str, interval: str, user_id: str) -> list[TimeSeriesPoint]:
        if range_value != "1y" or interval != "1d":
            raise ValueError("Solo range=1y e interval=1d supportati in V1")

        end_date = date.today()
        start_date = end_date - timedelta(days=364)

        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")
            base_ccy = portfolio.base_currency

            tx_rows = conn.execute(
                text(
                    """
                    select trade_at::date as trade_date, asset_id, side, quantity::float8 as quantity
                    from transactions
                    where portfolio_id = :portfolio_id and trade_at::date <= :end_date
                      and side in ('buy', 'sell')
                      and asset_id is not null
                    order by trade_at asc, id asc
                    """
                ),
                {"portfolio_id": portfolio_id, "end_date": end_date},
            ).mappings().all()

            if not tx_rows:
                return [
                    TimeSeriesPoint(date=(start_date + timedelta(days=offset)).isoformat(), market_value=0.0)
                    for offset in range(365)
                ]

            asset_ids = sorted({int(r["asset_id"]) for r in tx_rows})
            assets = self._get_asset_meta(conn, asset_ids)

            price_rows = conn.execute(
                text(
                    """
                    select asset_id, price_date, close::float8 as close
                    from price_bars_1d
                    where asset_id = any(:asset_ids) and price_date <= :end_date
                    order by asset_id asc, price_date asc
                    """
                ),
                {"asset_ids": asset_ids, "end_date": end_date},
            ).mappings().all()

            fx_needed = sorted({meta.quote_currency for meta in assets.values() if meta.quote_currency != base_ccy})
            fx_rows = []
            if fx_needed:
                fx_rows = conn.execute(
                    text(
                        """
                        select from_ccy, price_date, rate::float8 as rate
                        from fx_rates_1d
                        where from_ccy = any(:from_ccy)
                          and to_ccy = :to_ccy
                          and price_date <= :end_date
                        order by from_ccy asc, price_date asc
                        """
                    ),
                    {"from_ccy": fx_needed, "to_ccy": base_ccy, "end_date": end_date},
                ).mappings().all()

        deltas_by_day: dict[date, list[PositionDelta]] = defaultdict(list)
        for row in tx_rows:
            trade_day = row["trade_date"]
            if trade_day is None:
                continue
            deltas_by_day[trade_day].append(
                PositionDelta(asset_id=int(row["asset_id"]), side=str(row["side"]), quantity=float(row["quantity"]))
            )

        price_series: dict[int, list[tuple[date, float]]] = defaultdict(list)
        for row in price_rows:
            price_series[int(row["asset_id"])].append((row["price_date"], float(row["close"])))

        fx_series: dict[str, list[tuple[date, float]]] = defaultdict(list)
        for row in fx_rows:
            fx_series[str(row["from_ccy"])].append((row["price_date"], float(row["rate"])))

        holdings: dict[int, float] = defaultdict(float)

        # Pre-compute holdings for transactions before start_date
        for day in sorted(deltas_by_day.keys()):
            if day >= start_date:
                break
            for delta in deltas_by_day[day]:
                if delta.side == "buy":
                    holdings[delta.asset_id] += delta.quantity
                else:
                    holdings[delta.asset_id] -= delta.quantity

        price_index: dict[int, int] = {aid: -1 for aid in asset_ids}
        current_price: dict[int, float | None] = {aid: None for aid in asset_ids}

        fx_index: dict[str, int] = {ccy: -1 for ccy in fx_series.keys()}
        current_fx: dict[str, float | None] = {ccy: None for ccy in fx_series.keys()}

        points: list[TimeSeriesPoint] = []
        cursor = start_date
        while cursor <= end_date:
            for delta in deltas_by_day.get(cursor, []):
                if delta.side == "buy":
                    holdings[delta.asset_id] += delta.quantity
                else:
                    holdings[delta.asset_id] -= delta.quantity

            for asset_id, series in price_series.items():
                idx = price_index[asset_id]
                while idx + 1 < len(series) and series[idx + 1][0] <= cursor:
                    idx += 1
                price_index[asset_id] = idx
                current_price[asset_id] = series[idx][1] if idx >= 0 else None

            for from_ccy, series in fx_series.items():
                idx = fx_index[from_ccy]
                while idx + 1 < len(series) and series[idx + 1][0] <= cursor:
                    idx += 1
                fx_index[from_ccy] = idx
                current_fx[from_ccy] = series[idx][1] if idx >= 0 else None

            total_value = 0.0
            for asset_id, qty in holdings.items():
                if qty <= 0:
                    continue
                meta = assets.get(asset_id)
                if meta is None:
                    continue
                px = current_price.get(asset_id)
                if px is None:
                    continue

                if meta.quote_currency == base_ccy:
                    fx_rate = 1.0
                else:
                    fx_rate = current_fx.get(meta.quote_currency)
                    if fx_rate is None:
                        continue

                total_value += qty * px * fx_rate

            points.append(TimeSeriesPoint(date=cursor.isoformat(), market_value=round(total_value, 2)))
            cursor += timedelta(days=1)

        return points

    def get_allocation(self, portfolio_id: int, user_id: str) -> list[AllocationItem]:
        positions = self.get_positions(portfolio_id, user_id)
        total = sum(p.market_value for p in positions)
        if total == 0:
            return []
        return [
            AllocationItem(
                asset_id=p.asset_id,
                symbol=p.symbol,
                market_value=p.market_value,
                weight_pct=round((p.market_value / total) * 100.0, 2),
            )
            for p in positions
        ]
