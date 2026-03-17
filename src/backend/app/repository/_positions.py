import math
from bisect import bisect_right
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import text

from ..price_validation import check_staleness
from ..models import Position
from ._base import _finite


class PositionsMixin:
    def get_positions(self, portfolio_id: int, user_id: str, stale_days: int = 5) -> list[Position]:
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
            base_ccy = portfolio.base_currency

            # Fetch previous_close from the latest price tick per asset (yFinance previous_close).
            # Falls back to the penultimate daily bar from price_bars_1d when not available.
            prev_close_rows = conn.execute(
                text(
                    """
                    select distinct on (asset_id)
                        asset_id,
                        previous_close::float8 as previous_close
                    from price_ticks
                    where asset_id = any(:asset_ids)
                      and previous_close is not null
                    order by asset_id, ts desc
                    """
                ),
                {"asset_ids": asset_ids},
            ).mappings().all()
            prev_close_by_asset: dict[int, float] = {}
            for r in prev_close_rows:
                v = float(r["previous_close"])
                if math.isfinite(v):
                    prev_close_by_asset[int(r["asset_id"])] = v

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
                pos_day_change_pct = 0.0
                # Compare in quote currency (no FX) to match yFinance modal behaviour
                current_for_pct = raw_price if raw_price is not None else market_price
                if prev_close is not None and prev_close > 0 and math.isfinite(current_for_pct):
                    pos_day_change_pct = ((current_for_pct / prev_close) - 1) * 100.0

                positions.append(
                    Position(
                        asset_id=aid,
                        symbol=symbol,
                        name=name,
                        asset_type=asset_type,
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
