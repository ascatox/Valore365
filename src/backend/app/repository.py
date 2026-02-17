from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
import json

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .models import (
    AllocationItem,
    AssetCreate,
    AssetProviderSymbolCreate,
    AssetProviderSymbolRead,
    AssetRead,
    PortfolioSummary,
    Position,
    TimeSeriesPoint,
    TransactionCreate,
    TransactionRead,
)


@dataclass
class PortfolioData:
    id: int
    base_currency: str


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


class PortfolioRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def create_asset(self, payload: AssetCreate) -> AssetRead:
        symbol = payload.symbol.strip().upper()
        quote_currency = payload.quote_currency.strip().upper()
        exchange_code = payload.exchange_code.strip().upper() if payload.exchange_code else None
        isin = payload.isin.strip().upper() if payload.isin else None

        with self.engine.begin() as conn:
            try:
                row = conn.execute(
                    text(
                        """
                        insert into assets (symbol, name, asset_type, exchange_code, exchange_name, quote_currency, isin, active)
                        values (:symbol, :name, :asset_type, :exchange_code, :exchange_name, :quote_currency, :isin, :active)
                        returning id
                        """
                    ),
                    {
                        "symbol": symbol,
                        "name": payload.name,
                        "asset_type": payload.asset_type,
                        "exchange_code": exchange_code,
                        "exchange_name": payload.exchange_name,
                        "quote_currency": quote_currency,
                        "isin": isin,
                        "active": payload.active,
                    },
                ).fetchone()
            except Exception as exc:
                raise ValueError("Asset gia esistente o vincolo violato") from exc

        if row is None:
            raise ValueError("Impossibile creare asset")
        return self.get_asset(int(row.id))

    def get_asset(self, asset_id: int) -> AssetRead:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select id, symbol, name, asset_type, exchange_code, exchange_name, quote_currency, isin, active
                    from assets
                    where id = :id
                    """
                ),
                {"id": asset_id},
            ).mappings().fetchone()
        if row is None:
            raise ValueError("Asset non trovato")
        return AssetRead(
            id=int(row["id"]),
            symbol=str(row["symbol"]),
            name=row["name"],
            asset_type=str(row["asset_type"]),
            exchange_code=row["exchange_code"],
            exchange_name=row["exchange_name"],
            quote_currency=str(row["quote_currency"]),
            isin=row["isin"],
            active=bool(row["active"]),
        )

    def create_asset_provider_symbol(self, payload: AssetProviderSymbolCreate) -> AssetProviderSymbolRead:
        provider = payload.provider.strip().lower()
        provider_symbol = payload.provider_symbol.strip().upper()
        with self.engine.begin() as conn:
            if not self._asset_exists(conn, payload.asset_id):
                raise ValueError("Asset non trovato")
            try:
                conn.execute(
                    text(
                        """
                        insert into asset_provider_symbols (asset_id, provider, provider_symbol)
                        values (:asset_id, :provider, :provider_symbol)
                        """
                    ),
                    {
                        "asset_id": payload.asset_id,
                        "provider": provider,
                        "provider_symbol": provider_symbol,
                    },
                )
            except Exception as exc:
                raise ValueError("Mapping provider gia esistente o vincolo violato") from exc
        return AssetProviderSymbolRead(
            asset_id=payload.asset_id,
            provider=provider,
            provider_symbol=provider_symbol,
        )

    def create_transaction(self, payload: TransactionCreate) -> TransactionRead:
        side = payload.side.lower().strip()
        currency = payload.trade_currency.upper().strip()
        if side not in {"buy", "sell"}:
            raise ValueError("side deve essere buy o sell")

        with self.engine.begin() as conn:
            portfolio = self._get_portfolio(conn, payload.portfolio_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")
            if not self._asset_exists(conn, payload.asset_id):
                raise ValueError("Asset non trovato")

            if side == "sell":
                qty = self._current_quantity(conn, payload.portfolio_id, payload.asset_id)
                if float(payload.quantity) > qty:
                    raise ValueError("Quantita insufficiente per sell")

            row = conn.execute(
                text(
                    """
                    insert into transactions (
                        portfolio_id, asset_id, side, trade_at, quantity, price, fees, taxes, trade_currency, notes
                    ) values (
                        :portfolio_id, :asset_id, :side, :trade_at, :quantity, :price, :fees, :taxes, :trade_currency, :notes
                    )
                    returning id
                    """
                ),
                {
                    "portfolio_id": payload.portfolio_id,
                    "asset_id": payload.asset_id,
                    "side": side,
                    "trade_at": payload.trade_at,
                    "quantity": payload.quantity,
                    "price": payload.price,
                    "fees": payload.fees,
                    "taxes": payload.taxes,
                    "trade_currency": currency,
                    "notes": payload.notes,
                },
            ).fetchone()

        if row is None:
            raise ValueError("Impossibile creare la transazione")

        return TransactionRead(
            id=int(row.id),
            portfolio_id=payload.portfolio_id,
            asset_id=payload.asset_id,
            side=side,
            trade_at=payload.trade_at,
            quantity=payload.quantity,
            price=payload.price,
            fees=payload.fees,
            taxes=payload.taxes,
            trade_currency=currency,
            notes=payload.notes,
        )

    def get_positions(self, portfolio_id: int) -> list[Position]:
        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")

            tx_rows = conn.execute(
                text(
                    """
                    select asset_id, side, quantity::float8 as quantity, price::float8 as price,
                           fees::float8 as fees, taxes::float8 as taxes
                    from transactions
                    where portfolio_id = :portfolio_id
                    order by trade_at asc, id asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            if not tx_rows:
                return []

            asset_ids = sorted({int(r["asset_id"]) for r in tx_rows})
            assets = self._get_assets(conn, asset_ids)
            prices = self._get_latest_prices(conn, asset_ids)

            grouped: dict[int, dict[str, float]] = defaultdict(lambda: {"quantity": 0.0, "cost": 0.0})
            for tx in tx_rows:
                aid = int(tx["asset_id"])
                lot = grouped[aid]
                qty = float(tx["quantity"])
                price = float(tx["price"])
                fees = float(tx["fees"])
                taxes = float(tx["taxes"])

                if tx["side"] == "buy":
                    lot["quantity"] += qty
                    lot["cost"] += qty * price + fees + taxes
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
                market_price = prices.get(aid, avg_cost)
                market_value = qty * market_price
                cost_basis = qty * avg_cost
                pl = market_value - cost_basis
                pl_pct = (pl / cost_basis * 100.0) if cost_basis else 0.0
                symbol = assets.get(aid, {}).get("symbol", f"ASSET-{aid}")
                positions.append(
                    Position(
                        asset_id=aid,
                        symbol=symbol,
                        quantity=round(qty, 8),
                        avg_cost=round(avg_cost, 4),
                        market_price=round(market_price, 4),
                        market_value=round(market_value, 2),
                        unrealized_pl=round(pl, 2),
                        unrealized_pl_pct=round(pl_pct, 2),
                    )
                )

            positions.sort(key=lambda p: p.market_value, reverse=True)
            return positions

    def get_summary(self, portfolio_id: int) -> PortfolioSummary:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio(conn, portfolio_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")

        positions = self.get_positions(portfolio_id)
        market_value = sum(p.market_value for p in positions)
        cost_basis = sum(p.quantity * p.avg_cost for p in positions)
        pl = market_value - cost_basis
        pl_pct = (pl / cost_basis * 100.0) if cost_basis else 0.0

        return PortfolioSummary(
            portfolio_id=portfolio_id,
            base_currency=portfolio.base_currency,
            market_value=round(market_value, 2),
            cost_basis=round(cost_basis, 2),
            unrealized_pl=round(pl, 2),
            unrealized_pl_pct=round(pl_pct, 2),
        )

    def get_timeseries(self, portfolio_id: int, range_value: str, interval: str) -> list[TimeSeriesPoint]:
        if range_value != "1y" or interval != "1d":
            raise ValueError("Solo range=1y e interval=1d supportati in V1")

        end_date = date.today()
        start_date = end_date - timedelta(days=364)

        with self.engine.begin() as conn:
            portfolio = self._get_portfolio(conn, portfolio_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")
            base_ccy = portfolio.base_currency

            tx_rows = conn.execute(
                text(
                    """
                    select trade_at::date as trade_date, asset_id, side, quantity::float8 as quantity
                    from transactions
                    where portfolio_id = :portfolio_id and trade_at::date <= :end_date
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

    def get_allocation(self, portfolio_id: int) -> list[AllocationItem]:
        positions = self.get_positions(portfolio_id)
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

    def search_assets(self, query: str) -> list[dict[str, str]]:
        q = f"%{query.lower().strip()}%"
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select id, symbol, coalesce(name, '') as name
                    from assets
                    where lower(symbol) like :q or lower(coalesce(name, '')) like :q
                    order by symbol asc
                    limit 25
                    """
                ),
                {"q": q},
            ).mappings().all()

        return [{"id": str(r["id"]), "symbol": r["symbol"], "name": r["name"]} for r in rows]

    def get_assets_for_price_refresh(self, provider: str, portfolio_id: int | None = None) -> list[PricingAsset]:
        provider_value = provider.strip().lower()
        with self.engine.begin() as conn:
            if portfolio_id is None:
                rows = conn.execute(
                    text(
                        """
                        select a.id as asset_id,
                               a.symbol,
                               coalesce(aps.provider_symbol, a.symbol) as provider_symbol
                        from assets a
                        left join asset_provider_symbols aps
                          on aps.asset_id = a.id and aps.provider = :provider
                        where a.active = true
                        order by a.symbol asc
                        """
                    ),
                    {"provider": provider_value},
                ).mappings().all()
            else:
                if self._get_portfolio(conn, portfolio_id) is None:
                    raise ValueError("Portfolio non trovato")

                rows = conn.execute(
                    text(
                        """
                        select distinct a.id as asset_id,
                               a.symbol,
                               coalesce(aps.provider_symbol, a.symbol) as provider_symbol
                        from transactions t
                        join assets a on a.id = t.asset_id
                        left join asset_provider_symbols aps
                          on aps.asset_id = a.id and aps.provider = :provider
                        where t.portfolio_id = :portfolio_id
                        order by a.symbol asc
                        """
                    ),
                    {"provider": provider_value, "portfolio_id": portfolio_id},
                ).mappings().all()

        return [
            PricingAsset(
                asset_id=int(r["asset_id"]),
                symbol=str(r["symbol"]),
                provider_symbol=str(r["provider_symbol"]),
            )
            for r in rows
        ]

    def save_price_tick(
        self,
        *,
        asset_id: int,
        provider: str,
        ts,
        last: float,
        bid: float | None,
        ask: float | None,
        volume: float | None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into price_ticks (asset_id, provider, ts, last, bid, ask, volume)
                    values (:asset_id, :provider, :ts, :last, :bid, :ask, :volume)
                    """
                ),
                {
                    "asset_id": asset_id,
                    "provider": provider.strip().lower(),
                    "ts": ts,
                    "last": last,
                    "bid": bid,
                    "ask": ask,
                    "volume": volume,
                },
            )

    def batch_upsert_price_bars_1d(
        self,
        *,
        asset_id: int,
        provider: str,
        rows: list[dict],
    ) -> None:
        if not rows:
            return
        provider_value = provider.strip().lower()
        payload = [
            {
                "asset_id": asset_id,
                "provider": provider_value,
                "price_date": row["price_date"],
                "open": row["open"],
                "high": row["high"],
                "low": row["low"],
                "close": row["close"],
                "volume": row["volume"],
            }
            for row in rows
        ]
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into price_bars_1d (asset_id, provider, price_date, open, high, low, close, volume)
                    values (:asset_id, :provider, :price_date, :open, :high, :low, :close, :volume)
                    on conflict (asset_id, provider, price_date)
                    do update set
                      open = excluded.open,
                      high = excluded.high,
                      low = excluded.low,
                      close = excluded.close,
                      volume = excluded.volume
                    """
                ),
                payload,
            )

    def upsert_price_bar_1d(
        self,
        *,
        asset_id: int,
        provider: str,
        price_date: date,
        open_value: float,
        high_value: float,
        low_value: float,
        close_value: float,
        volume: float | None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into price_bars_1d (asset_id, provider, price_date, open, high, low, close, volume)
                    values (:asset_id, :provider, :price_date, :open, :high, :low, :close, :volume)
                    on conflict (asset_id, provider, price_date)
                    do update set
                      open = excluded.open,
                      high = excluded.high,
                      low = excluded.low,
                      close = excluded.close,
                      volume = excluded.volume
                    """
                ),
                {
                    "asset_id": asset_id,
                    "provider": provider.strip().lower(),
                    "price_date": price_date,
                    "open": open_value,
                    "high": high_value,
                    "low": low_value,
                    "close": close_value,
                    "volume": volume,
                },
            )

    def upsert_fx_rate_1d(
        self,
        *,
        from_ccy: str,
        to_ccy: str,
        provider: str,
        price_date: date,
        rate: float,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into fx_rates_1d (from_ccy, to_ccy, provider, price_date, rate)
                    values (:from_ccy, :to_ccy, :provider, :price_date, :rate)
                    on conflict (from_ccy, to_ccy, provider, price_date)
                    do update set rate = excluded.rate
                    """
                ),
                {
                    "from_ccy": from_ccy.upper(),
                    "to_ccy": to_ccy.upper(),
                    "provider": provider.strip().lower(),
                    "price_date": price_date,
                    "rate": rate,
                },
            )

    def batch_upsert_fx_rates_1d(
        self,
        *,
        from_ccy: str,
        to_ccy: str,
        provider: str,
        rows: list[dict],
    ) -> None:
        if not rows:
            return
        provider_value = provider.strip().lower()
        payload = [
            {
                "from_ccy": from_ccy.upper(),
                "to_ccy": to_ccy.upper(),
                "provider": provider_value,
                "price_date": row["price_date"],
                "rate": row["rate"],
            }
            for row in rows
        ]
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into fx_rates_1d (from_ccy, to_ccy, provider, price_date, rate)
                    values (:from_ccy, :to_ccy, :provider, :price_date, :rate)
                    on conflict (from_ccy, to_ccy, provider, price_date)
                    do update set rate = excluded.rate
                    """
                ),
                payload,
            )

    def get_idempotency_response(self, *, idempotency_key: str, endpoint: str) -> dict | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select response_json
                    from api_idempotency_keys
                    where idempotency_key = :idempotency_key and endpoint = :endpoint
                    """
                ),
                {"idempotency_key": idempotency_key, "endpoint": endpoint},
            ).mappings().fetchone()
        if row is None:
            return None
        return row["response_json"]

    def save_idempotency_response(self, *, idempotency_key: str, endpoint: str, response_payload: dict) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into api_idempotency_keys (idempotency_key, endpoint, response_json)
                    values (:idempotency_key, :endpoint, cast(:response_json as jsonb))
                    on conflict (idempotency_key, endpoint)
                    do update set response_json = excluded.response_json
                    """
                ),
                {
                    "idempotency_key": idempotency_key,
                    "endpoint": endpoint,
                    "response_json": json.dumps(response_payload),
                },
            )

    def get_portfolio_base_currency(self, portfolio_id: int) -> str:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio(conn, portfolio_id)
            if portfolio is None:
                raise ValueError("Portfolio non trovato")
            return portfolio.base_currency

    def get_quote_currencies_for_assets(self, asset_ids: list[int]) -> dict[int, str]:
        if not asset_ids:
            return {}
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select id, quote_currency
                    from assets
                    where id = any(:asset_ids)
                    """
                ),
                {"asset_ids": asset_ids},
            ).mappings().all()
        return {int(r["id"]): str(r["quote_currency"]) for r in rows}

    def _get_portfolio(self, conn, portfolio_id: int) -> PortfolioData | None:
        row = conn.execute(
            text("select id, base_currency from portfolios where id = :id"),
            {"id": portfolio_id},
        ).mappings().fetchone()
        if row is None:
            return None
        return PortfolioData(id=int(row["id"]), base_currency=str(row["base_currency"]))

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

    def _get_assets(self, conn, asset_ids: list[int]) -> dict[int, dict[str, str]]:
        rows = conn.execute(
            text(
                """
                select id, symbol
                from assets
                where id = any(:asset_ids)
                """
            ),
            {"asset_ids": asset_ids},
        ).mappings().all()
        return {int(r["id"]): {"symbol": str(r["symbol"])} for r in rows}

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
