import logging
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
from bisect import bisect_right

from sqlalchemy import text
from sqlalchemy.engine import Engine

from ..sql import load_sql


def _finite(v: float, fallback: float = 0.0) -> float:
    """Return v if finite, else fallback."""
    return v if math.isfinite(v) else fallback


@dataclass
class PortfolioData:
    id: int
    base_currency: str
    cash_balance: float


@dataclass
class PricingAsset:
    asset_id: int
    symbol: str
    provider_symbol: str


@dataclass
class AssetMeta:
    symbol: str
    quote_currency: str


@dataclass
class PositionDelta:
    asset_id: int
    side: str
    quantity: float


class BaseRepositoryMixin:
    def _get_portfolio_for_user(self, conn, portfolio_id: int, user_id: str) -> PortfolioData | None:
        row = conn.execute(
            text("select id, base_currency, cash_balance from portfolios where id = :id and owner_user_id = :user_id"),
            {"id": portfolio_id, "user_id": user_id},
        ).mappings().fetchone()
        if row is None:
            return None
        return PortfolioData(
            id=int(row["id"]),
            base_currency=str(row["base_currency"]),
            cash_balance=float(row["cash_balance"]),
        )

    def _asset_exists(self, conn, asset_id: int) -> bool:
        row = conn.execute(text("select 1 from assets where id = :id"), {"id": asset_id}).fetchone()
        return row is not None

    def _current_quantity(self, conn, portfolio_id: int, asset_id: int) -> float:
        row = conn.execute(
            text(
                """
                select coalesce(sum(case when side='buy' then quantity else -quantity end), 0)::float8 as quantity
                from transactions
                where portfolio_id = :portfolio_id and asset_id = :asset_id
                """
            ),
            {"portfolio_id": portfolio_id, "asset_id": asset_id},
        ).mappings().fetchone()
        return float(row["quantity"]) if row is not None else 0.0

    def _assert_non_negative_inventory_timeline(
        self,
        conn,
        portfolio_id: int,
        asset_id: int,
        *,
        candidate: dict | None = None,
        exclude_transaction_id: int | None = None,
    ) -> None:
        params: dict[str, object] = {"portfolio_id": portfolio_id, "asset_id": asset_id}
        exclude_clause = ""
        if exclude_transaction_id is not None:
            exclude_clause = "and id <> :exclude_transaction_id"
            params["exclude_transaction_id"] = exclude_transaction_id

        rows = conn.execute(
            text(
                f"""
                select id, trade_at, side, quantity::float8 as quantity
                from transactions
                where portfolio_id = :portfolio_id
                  and asset_id = :asset_id
                  {exclude_clause}
                order by trade_at asc, id asc
                """
            ),
            params,
        ).mappings().all()

        timeline = [
            {
                "id": int(row["id"]),
                "trade_at": row["trade_at"],
                "side": str(row["side"]),
                "quantity": float(row["quantity"]),
            }
            for row in rows
        ]
        if candidate is not None:
            timeline.append(candidate)

        timeline.sort(
            key=lambda item: (
                item["trade_at"],
                int(item["id"]) if item.get("id") is not None else 10**18,
            )
        )

        running_qty = 0.0
        epsilon = 1e-9
        for item in timeline:
            if item.get("trade_at") is None:
                raise ValueError("trade_at non puo essere nullo")
            side = str(item["side"]).lower()
            qty = float(item["quantity"])
            running_qty = running_qty + qty if side == "buy" else running_qty - qty
            if running_qty < -epsilon:
                raise ValueError("Quantita insufficiente per sell alla data operazione")

    def _current_quantity_excluding_transaction(self, conn, portfolio_id: int, asset_id: int, transaction_id: int) -> float:
        row = conn.execute(
            text(
                """
                select coalesce(sum(case when side='buy' then quantity else -quantity end), 0)::float8 as quantity
                from transactions
                where portfolio_id = :portfolio_id
                  and asset_id = :asset_id
                  and id <> :transaction_id
                """
            ),
            {"portfolio_id": portfolio_id, "asset_id": asset_id, "transaction_id": transaction_id},
        ).mappings().fetchone()
        return float(row["quantity"]) if row is not None else 0.0

    def _get_transaction_for_user(self, conn, transaction_id: int, user_id: str):
        return conn.execute(
            text(
                """
                select id,
                       portfolio_id,
                       asset_id,
                       side,
                       trade_at,
                       quantity::float8 as quantity,
                       price::float8 as price,
                       fees::float8 as fees,
                       taxes::float8 as taxes,
                       trade_currency,
                       notes
                from transactions
                where id = :transaction_id and owner_user_id = :user_id
                """
            ),
            {"transaction_id": transaction_id, "user_id": user_id},
        ).mappings().fetchone()

    def _get_assets(self, conn, asset_ids: list[int]) -> dict[int, dict[str, str]]:
        rows = conn.execute(
            text(
                """
                select id, symbol, name, asset_type
                from assets
                where id = any(:asset_ids)
                """
            ),
            {"asset_ids": asset_ids},
        ).mappings().all()
        return {int(r["id"]): {"symbol": str(r["symbol"]), "name": str(r["name"]), "asset_type": str(r["asset_type"])} for r in rows}

    def _get_asset_meta(self, conn, asset_ids: list[int]) -> dict[int, AssetMeta]:
        rows = conn.execute(
            text(
                """
                select id, symbol, quote_currency
                from assets
                where id = any(:asset_ids)
                """
            ),
            {"asset_ids": asset_ids},
        ).mappings().all()
        return {
            int(r["id"]): AssetMeta(symbol=str(r["symbol"]), quote_currency=str(r["quote_currency"]))
            for r in rows
        }

    def _get_latest_prices(self, conn, asset_ids: list[int]) -> dict[int, float]:
        rows = conn.execute(
            text(
                """
                with latest_ticks as (
                    select distinct on (asset_id) asset_id, last::float8 as last
                    from price_ticks
                    where asset_id = any(:asset_ids)
                    order by asset_id, ts desc
                )
                select asset_id, last
                from latest_ticks
                """
            ),
            {"asset_ids": asset_ids},
        ).mappings().all()
        return {int(r["asset_id"]): float(r["last"]) for r in rows}

    def _get_latest_daily_prices(self, conn, asset_ids: list[int]) -> dict[int, tuple[date, float]]:
        rows = conn.execute(
            text(
                """
                with latest_daily as (
                    select distinct on (asset_id)
                        asset_id,
                        price_date,
                        close::float8 as close
                    from price_bars_1d
                    where asset_id = any(:asset_ids)
                    order by asset_id, price_date desc
                )
                select asset_id, price_date, close
                from latest_daily
                """
            ),
            {"asset_ids": asset_ids},
        ).mappings().all()
        return {int(r["asset_id"]): (r["price_date"], float(r["close"])) for r in rows}
