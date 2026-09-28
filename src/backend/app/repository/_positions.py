import math
from bisect import bisect_right
from collections import defaultdict
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import date, datetime, timedelta

from sqlalchemy import text

from ..price_validation import check_staleness
from ..models import PeriodPerformer, Position
from ._base import _finite


# Per-scope memo for get_positions, active only inside memoize_positions().
_positions_memo: ContextVar[dict | None] = ContextVar("_positions_memo", default=None)


class PositionsMixin:
    @contextmanager
    def memoize_positions(self):
        """Compute each portfolio's positions at most once inside this block.

        get_summary and get_allocation both call get_positions, so code that
        needs summary + positions + allocation (e.g. the copilot snapshot)
        would otherwise rebuild them from all transactions three times.
        """
        token = _positions_memo.set({})
        try:
            yield
        finally:
            _positions_memo.reset(token)

    def get_positions(self, portfolio_id: int, user_id: str, stale_days: int = 5) -> list[Position]:
        memo = _positions_memo.get()
        if memo is None:
            return self._compute_positions(portfolio_id, user_id, stale_days)
        key = (portfolio_id, user_id, stale_days)
        if key not in memo:
            memo[key] = self._compute_positions(portfolio_id, user_id, stale_days)
        return [p.model_copy() for p in memo[key]]

    def get_period_performers(
        self, portfolio_id: int, user_id: str, days: int, today: date | None = None,
    ) -> list[PeriodPerformer]:
        """Price return of each open position over the last ``days`` days.

        Uses the same window as the dashboard chart so "Migliori/Peggiori"
        match the portfolio variation shown above them. For ``days == 1`` the
        positions' day_change_pct is reused so values match the "Oggi" KPI.
        Returns are in quote currency, like day_change_pct.
        """
        positions = [p for p in self.get_positions(portfolio_id, user_id) if p.quantity > 0]
        if not positions:
            return []
        if days <= 1:
            return [
                PeriodPerformer(
                    asset_id=p.asset_id, symbol=p.symbol, name=p.name,
                    return_pct=p.day_change_pct, start_date=None,
                )
                for p in positions
            ]

        start_date = (today or date.today()) - timedelta(days=days)
        prices = self._get_period_prices([p.asset_id for p in positions], start_date)
        result: list[PeriodPerformer] = []
        for p in positions:
            start_info, end_price = prices.get(p.asset_id, (None, None))
            if start_info is None or end_price is None:
                continue
            start_day, start_close = start_info
            if not (start_close > 0 and math.isfinite(start_close) and math.isfinite(end_price)):
                continue
            result.append(
                PeriodPerformer(
                    asset_id=p.asset_id,
                    symbol=p.symbol,
                    name=p.name,
                    return_pct=round(((end_price / start_close) - 1) * 100.0, 2),
                    start_date=start_day,
                )
            )
        return result

    def _get_period_prices(
        self, asset_ids: list[int], start_date: date,
    ) -> dict[int, tuple[tuple[date, float] | None, float | None]]:
        """Per asset: (start bar on/before start_date, current quote price).

        The start bar falls back to the first bar after start_date when the
        history does not reach that far back. The current price prefers the
        latest tick (as in get_positions) over the latest daily close.
        """
        with self.engine.begin() as conn:
            start_rows = conn.execute(
                text(
                    """
                    select asset_id, price_date, close from (
                        select distinct on (asset_id) asset_id, price_date, close::float8 as close
                        from price_bars_1d
                        where asset_id = any(:asset_ids) and price_date <= :start_date
                        order by asset_id, price_date desc
                    ) before_start
                    union all
                    select asset_id, price_date, close from (
                        select distinct on (asset_id) asset_id, price_date, close::float8 as close
                        from price_bars_1d
                        where asset_id = any(:asset_ids) and price_date > :start_date
                        order by asset_id, price_date asc
                    ) after_start
                    """
                ),
                {"asset_ids": asset_ids, "start_date": start_date},
            ).mappings().all()
            latest_daily = self._get_latest_daily_prices(conn, asset_ids)
            tick_rows = conn.execute(
                text(
                    """
                    select distinct on (asset_id) asset_id, last::float8 as last
                    from price_ticks
                    where asset_id = any(:asset_ids)
                    order by asset_id, ts desc
                    """
                ),
                {"asset_ids": asset_ids},
            ).mappings().all()

        start_by_asset: dict[int, tuple[date, float]] = {}
        for r in start_rows:
            aid = int(r["asset_id"])
            current = start_by_asset.get(aid)
            # Prefer the bar on/before start_date; the first later bar is only a fallback.
            if current is None or (r["price_date"] <= start_date and current[0] > start_date):
                start_by_asset[aid] = (r["price_date"], float(r["close"]))
        end_by_asset: dict[int, float] = {aid: close for aid, (_, close) in latest_daily.items()}
        for r in tick_rows:
            if r["last"] is not None and math.isfinite(float(r["last"])):
                end_by_asset[int(r["asset_id"])] = float(r["last"])
        return {aid: (start_by_asset.get(aid), end_by_asset.get(aid)) for aid in asset_ids}

    def _compute_positions(self, portfolio_id: int, user_id: str, stale_days: int) -> list[Position]:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio_for_user(conn, portfolio_id, user_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")

            tx_rows = conn.execute(
                text(
                    """
                    select asset_id,
                           side,
                           trade_at,
                           trade_at::date as trade_date,
                           quantity::float8 as quantity,
                           price::float8 as price,
                           fees::float8 as fees,
                           taxes::float8 as taxes,
                           trade_currency
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

            asset_ids = sorted({int(r["asset_id"]) for r in tx_rows})
            assets = self._get_assets(conn, asset_ids)
            asset_meta = self._get_asset_meta(conn, asset_ids)
            daily_prices = self._get_latest_daily_prices(conn, asset_ids)

            # Fetch investment_focus from etf_enrichment
            inv_focus_rows = conn.execute(
                text(
                    """
                    select asset_id, investment_focus
                    from etf_enrichment
                    where asset_id = any(:asset_ids)
                      and investment_focus is not null
                    """
                ),
                {"asset_ids": asset_ids},
            ).mappings().all()
            inv_focus_by_asset: dict[int, str] = {
                int(r["asset_id"]): str(r["investment_focus"]) for r in inv_focus_rows
            }
            base_ccy = portfolio.base_currency

            # Fetch the latest tick snapshot per asset. When available, use tick last/previous_close
            # for day-change so the percentage is computed from a coherent quote source.
            latest_tick_rows = conn.execute(
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
            tick_last_by_asset: dict[int, float] = {}
            prev_close_by_asset: dict[int, float] = {}
            for r in latest_tick_rows:
                asset_id = int(r["asset_id"])
                last = r.get("last")
                if last is not None:
                    last_value = float(last)
                    if math.isfinite(last_value):
                        tick_last_by_asset[asset_id] = last_value
                prev_close = r.get("previous_close")
                if prev_close is not None:
                    prev_close_value = float(prev_close)
                    if math.isfinite(prev_close_value):
                        prev_close_by_asset[asset_id] = prev_close_value

            # Fallback: for assets without previous_close in ticks, use penultimate daily bar
            missing_assets = [aid for aid in asset_ids if aid not in prev_close_by_asset]
            if missing_assets:
                fallback_rows = conn.execute(
                    text(
                        """
                        with ranked as (
                            select asset_id, close::float8 as close,
                                   row_number() over (partition by asset_id order by price_date desc) as rn
                            from price_bars_1d
                            where asset_id = any(:asset_ids)
                        )
                        select asset_id, close
                        from ranked
                        where rn = 2
                        """
                    ),
                    {"asset_ids": missing_assets},
                ).mappings().all()
                for r in fallback_rows:
                    v = float(r["close"])
                    if math.isfinite(v):
                        prev_close_by_asset[int(r["asset_id"])] = v

            fx_currencies = sorted(
                {
                    str(r["trade_currency"])
                    for r in tx_rows
                    if r.get("trade_currency") and str(r["trade_currency"]) != base_ccy
                }
                | {
                    meta.quote_currency
                    for meta in asset_meta.values()
                    if meta.quote_currency != base_ccy
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
                    {"from_ccy": fx_currencies, "to_ccy": base_ccy},
                ).mappings().all()

            grouped: dict[int, dict[str, float]] = defaultdict(lambda: {"quantity": 0.0, "cost": 0.0})
            first_trade_at_by_asset: dict[int, datetime] = {}
            fx_series: dict[str, list[tuple[date, float]]] = defaultdict(list)
            for row in fx_rows:
                fx_series[str(row["from_ccy"])].append((row["price_date"], float(row["rate"])))

            fx_dates = {ccy: [d for d, _ in series] for ccy, series in fx_series.items()}

            def fx_rate_on_or_before(currency: str, day: date | None) -> float | None:
                if currency == base_ccy:
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

            for tx in tx_rows:
                aid = int(tx["asset_id"])
                lot = grouped[aid]
                trade_at_ts = tx.get("trade_at")
                if isinstance(trade_at_ts, datetime):
                    prev_first = first_trade_at_by_asset.get(aid)
                    if prev_first is None or trade_at_ts < prev_first:
                        first_trade_at_by_asset[aid] = trade_at_ts
                qty = float(tx["quantity"])
                price = float(tx["price"])
                fees = float(tx["fees"])
                taxes = float(tx["taxes"])
                trade_day = tx["trade_date"]
                trade_ccy = str(tx["trade_currency"])
                tx_fx = fx_rate_on_or_before(trade_ccy, trade_day) or 1.0
                gross_cost_base = qty * price * tx_fx
                fees_taxes_base = (fees + taxes) * tx_fx

                if tx["side"] == "buy":
                    lot["quantity"] += qty
                    lot["cost"] += gross_cost_base + fees_taxes_base
                else:
                    if lot["quantity"] <= 0:
                        continue
                    avg_cost = lot["cost"] / lot["quantity"]
                    sold_qty = min(qty, lot["quantity"])
                    lot["quantity"] -= sold_qty
                    lot["cost"] -= avg_cost * sold_qty
                    lot["cost"] = max(lot["cost"], 0.0)

            positions: list[Position] = []
            for aid, lot in grouped.items():
                qty = lot["quantity"]
                if qty <= 0:
                    continue
                avg_cost = lot["cost"] / qty if qty else 0.0
                price_info = daily_prices.get(aid)
                meta = asset_meta.get(aid)
                market_price = avg_cost
                raw_price: float | None = None  # price in quote currency (no FX)
                price_day_val: date | None = None
                if price_info and meta is not None:
                    price_day, latest_close = price_info
                    raw_price = latest_close
                    price_day_val = price_day
                    quote_fx = fx_rate_on_or_before(meta.quote_currency, price_day)
                    if quote_fx is not None:
                        market_price = latest_close * quote_fx
                market_value = qty * market_price
                cost_basis = qty * avg_cost
                pl = market_value - cost_basis
                pl_pct = (pl / cost_basis * 100.0) if cost_basis else 0.0
                asset_details = assets.get(aid, {})
                symbol = asset_details.get("symbol", f"ASSET-{aid}")
                name = asset_details.get("name", "")
                asset_type = asset_details.get("asset_type", "stock")

                stale = check_staleness(
                    asset_id=aid,
                    symbol=symbol,
                    price_date=price_day_val,
                    today=date.today(),
                    stale_days=stale_days,
                )

                prev_close = prev_close_by_asset.get(aid)
                current_quote_price = tick_last_by_asset.get(aid)
                if current_quote_price is None:
                    current_quote_price = raw_price
                pos_day_change_pct = 0.0
                # Compare in quote currency (no FX) to match yFinance modal behaviour.
                # Avoid falling back to market_price here because that is in base currency.
                if prev_close is not None and prev_close > 0 and current_quote_price is not None and math.isfinite(current_quote_price):
                    pos_day_change_pct = ((current_quote_price / prev_close) - 1) * 100.0

                positions.append(
                    Position(
                        asset_id=aid,
                        symbol=symbol,
                        name=name,
                        asset_type=asset_type,
                        investment_focus=inv_focus_by_asset.get(aid),
                        quantity=round(_finite(qty), 8),
                        avg_cost=round(_finite(avg_cost), 4),
                        market_price=round(_finite(market_price), 4),
                        market_value=round(_finite(market_value), 2),
                        unrealized_pl=round(_finite(pl), 2),
                        unrealized_pl_pct=round(_finite(pl_pct), 2),
                        day_change_pct=round(_finite(pos_day_change_pct), 2),
                        weight=0,  # Placeholder, will be calculated next
                        first_trade_at=first_trade_at_by_asset.get(aid),
                        price_stale=stale,
                        price_date=price_day_val,
                    )
                )

            total_market_value = sum(p.market_value for p in positions)

            if total_market_value > 0:
                for p in positions:
                    p.weight = round((p.market_value / total_market_value) * 100, 2)

            positions.sort(key=lambda p: p.market_value, reverse=True)
            return positions
