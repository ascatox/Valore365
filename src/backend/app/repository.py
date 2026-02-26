from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import json
from bisect import bisect_right

from sqlalchemy import text
from sqlalchemy.engine import Engine

from .models import (
    AllocationItem,
    AssetCreate,
    AssetProviderSymbolCreate,
    AssetProviderSymbolRead,
    AssetRead,
    PortfolioCreate,
    PortfolioRead,
    PortfolioUpdate,
    PortfolioSummary,
    PortfolioTargetAllocationItem,
    PortfolioTargetPerformancePoint,
    PortfolioTargetPerformanceResponse,
    PortfolioTargetPerformer,
    PortfolioTargetAssetPerformancePoint,
    PortfolioTargetAssetPerformanceResponse,
    PortfolioTargetAssetPerformanceSeries,
    PortfolioTargetAssetIntradayPerformancePoint,
    PortfolioTargetAssetIntradayPerformanceResponse,
    PortfolioTargetAssetIntradayPerformanceSeries,
    PortfolioTargetIntradayPoint,
    PortfolioTargetIntradayResponse,
    PortfolioTargetAllocationUpsert,
    Position,
    TimeSeriesPoint,
    TransactionCreate,
    TransactionListItem,
    TransactionRead,
    TransactionUpdate,
    UserSettingsRead,
    UserSettingsUpdate,
)


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


class PortfolioRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def get_user_settings(self, user_id: str) -> UserSettingsRead:
        normalized_user_id = (user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id non valido")
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select user_id, broker_default_fee::float8 as broker_default_fee
                    from app_user_settings
                    where user_id = :user_id
                    """
                ),
                {"user_id": normalized_user_id},
            ).mappings().fetchone()
        if row is None:
            return UserSettingsRead(user_id=normalized_user_id, broker_default_fee=0.0)
        return UserSettingsRead(
            user_id=str(row["user_id"]),
            broker_default_fee=float(row["broker_default_fee"] or 0.0),
        )

    def upsert_user_settings(self, user_id: str, payload: UserSettingsUpdate) -> UserSettingsRead:
        normalized_user_id = (user_id or "").strip()
        if not normalized_user_id:
            raise ValueError("user_id non valido")
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into app_user_settings (user_id, broker_default_fee, updated_at)
                    values (:user_id, :broker_default_fee, now())
                    on conflict (user_id)
                    do update set
                      broker_default_fee = excluded.broker_default_fee,
                      updated_at = now()
                    """
                ),
                {
                    "user_id": normalized_user_id,
                    "broker_default_fee": payload.broker_default_fee,
                },
            )
        return self.get_user_settings(normalized_user_id)

    def list_portfolio_target_allocations(self, portfolio_id: int) -> list[PortfolioTargetAllocationItem]:
        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")

            rows = conn.execute(
                text(
                    """
                    select pta.asset_id,
                           a.symbol,
                           coalesce(a.name, a.symbol) as name,
                           pta.weight_pct::float8 as weight_pct
                    from portfolio_target_allocations pta
                    join assets a on a.id = pta.asset_id
                    where pta.portfolio_id = :portfolio_id
                    order by pta.weight_pct desc, a.symbol asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

        return [
            PortfolioTargetAllocationItem(
                asset_id=int(row["asset_id"]),
                symbol=str(row["symbol"]),
                name=str(row["name"]),
                weight_pct=round(float(row["weight_pct"]), 4),
            )
            for row in rows
        ]

    def upsert_portfolio_target_allocation(
        self, portfolio_id: int, payload: PortfolioTargetAllocationUpsert
    ) -> PortfolioTargetAllocationItem:
        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")
            if not self._asset_exists(conn, payload.asset_id):
                raise ValueError("Asset non trovato")

            conn.execute(
                text(
                    """
                    insert into portfolio_target_allocations (portfolio_id, asset_id, weight_pct)
                    values (:portfolio_id, :asset_id, :weight_pct)
                    on conflict (portfolio_id, asset_id)
                    do update set
                      weight_pct = excluded.weight_pct,
                      updated_at = now()
                    """
                ),
                {
                    "portfolio_id": portfolio_id,
                    "asset_id": payload.asset_id,
                    "weight_pct": payload.weight_pct,
                },
            )

        items = self.list_portfolio_target_allocations(portfolio_id)
        for item in items:
            if item.asset_id == payload.asset_id:
                return item
        raise ValueError("Impossibile salvare allocazione target")

    def delete_portfolio_target_allocation(self, portfolio_id: int, asset_id: int) -> None:
        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")
            conn.execute(
                text(
                    """
                    delete from portfolio_target_allocations
                    where portfolio_id = :portfolio_id and asset_id = :asset_id
                    """
                ),
                {"portfolio_id": portfolio_id, "asset_id": asset_id},
            )

    def get_portfolio_target_performance(self, portfolio_id: int) -> PortfolioTargetPerformanceResponse:
        end_date = date.today()
        start_date = end_date - timedelta(days=364)

        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")

            alloc_rows = conn.execute(
                text(
                    """
                    select pta.asset_id,
                           pta.weight_pct::float8 as weight_pct,
                           a.symbol,
                           coalesce(a.name, a.symbol) as name
                    from portfolio_target_allocations pta
                    join assets a on a.id = pta.asset_id
                    where pta.portfolio_id = :portfolio_id
                    order by pta.weight_pct desc, a.symbol asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            if not alloc_rows:
                return PortfolioTargetPerformanceResponse(
                    portfolio_id=portfolio_id,
                    points=[],
                    last_updated_at=None,
                    best=None,
                    worst=None,
                )

            asset_ids = [int(r["asset_id"]) for r in alloc_rows]
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

            latest_tick_rows = conn.execute(
                text(
                    """
                    select distinct on (asset_id) asset_id, ts
                    from price_ticks
                    where asset_id = any(:asset_ids)
                    order by asset_id, ts desc
                    """
                ),
                {"asset_ids": asset_ids},
            ).mappings().all()

        alloc_meta = {
            int(r["asset_id"]): {
                "weight_pct": float(r["weight_pct"]),
                "symbol": str(r["symbol"]),
                "name": str(r["name"]),
            }
            for r in alloc_rows
        }

        latest_tick_ts = {
            int(r["asset_id"]): r["ts"] if isinstance(r["ts"], datetime) else None
            for r in latest_tick_rows
        }

        price_series: dict[int, list[tuple[date, float]]] = defaultdict(list)
        for row in price_rows:
            aid = int(row["asset_id"])
            px = float(row["close"])
            if px <= 0:
                continue
            price_series[aid].append((row["price_date"], px))

        baseline: dict[int, float] = {}
        for aid, series in price_series.items():
            last_before_or_on: float | None = None
            first_after_or_on: float | None = None
            for d, px in series:
                if d <= start_date:
                    last_before_or_on = px
                if d >= start_date and first_after_or_on is None:
                    first_after_or_on = px
            base_px = last_before_or_on if last_before_or_on is not None else first_after_or_on
            if base_px is not None and base_px > 0:
                baseline[aid] = base_px

        if not baseline:
            return PortfolioTargetPerformanceResponse(
                portfolio_id=portfolio_id,
                points=[],
                last_updated_at=None,
                best=None,
                worst=None,
            )

        indices: dict[int, int] = {aid: -1 for aid in baseline.keys()}
        current_px: dict[int, float | None] = {aid: None for aid in baseline.keys()}

        points: list[PortfolioTargetPerformancePoint] = []
        cursor = start_date
        while cursor <= end_date:
            weighted_sum = 0.0
            active_weight = 0.0
            for aid in baseline.keys():
                series = price_series.get(aid, [])
                idx = indices[aid]
                while idx + 1 < len(series) and series[idx + 1][0] <= cursor:
                    idx += 1
                indices[aid] = idx
                current_px[aid] = series[idx][1] if idx >= 0 else None

                px = current_px[aid]
                if px is None:
                    continue
                weight = alloc_meta[aid]["weight_pct"]
                weighted_sum += (px / baseline[aid]) * weight
                active_weight += weight

            value = (weighted_sum / active_weight * 100.0) if active_weight > 0 else 0.0
            points.append(PortfolioTargetPerformancePoint(date=cursor.isoformat(), weighted_index=round(value, 4)))
            cursor += timedelta(days=1)

        performers: list[PortfolioTargetPerformer] = []
        for aid, base_px in baseline.items():
            series = price_series.get(aid, [])
            if not series:
                continue
            latest_px = series[-1][1]
            ret = (latest_px / base_px - 1.0) * 100.0
            meta = alloc_meta[aid]
            performers.append(
                PortfolioTargetPerformer(
                    asset_id=aid,
                    symbol=str(meta["symbol"]),
                    name=str(meta["name"]),
                    return_pct=round(ret, 2),
                    as_of=latest_tick_ts.get(aid),
                )
            )

        best = max(performers, key=lambda x: x.return_pct) if performers else None
        worst = min(performers, key=lambda x: x.return_pct) if performers else None
        last_updated_at = max((ts for ts in latest_tick_ts.values() if isinstance(ts, datetime)), default=None)

        return PortfolioTargetPerformanceResponse(
            portfolio_id=portfolio_id,
            points=points,
            last_updated_at=last_updated_at,
            best=best,
            worst=worst,
        )

    def get_portfolio_target_intraday_performance(self, portfolio_id: int, day: date) -> PortfolioTargetIntradayResponse:
        day_start = datetime.combine(day, time.min)
        day_end = day_start + timedelta(days=1)

        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")

            alloc_rows = conn.execute(
                text(
                    """
                    select pta.asset_id,
                           pta.weight_pct::float8 as weight_pct
                    from portfolio_target_allocations pta
                    where pta.portfolio_id = :portfolio_id
                    order by pta.asset_id asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            if not alloc_rows:
                return PortfolioTargetIntradayResponse(portfolio_id=portfolio_id, date=day.isoformat(), points=[])

            asset_ids = [int(r["asset_id"]) for r in alloc_rows]
            tick_rows = conn.execute(
                text(
                    """
                    select asset_id, ts, last::float8 as last
                    from price_ticks
                    where asset_id = any(:asset_ids)
                      and ts >= :day_start
                      and ts < :day_end
                    order by ts asc, asset_id asc
                    """
                ),
                {"asset_ids": asset_ids, "day_start": day_start, "day_end": day_end},
            ).mappings().all()

        if not tick_rows:
            return PortfolioTargetIntradayResponse(portfolio_id=portfolio_id, date=day.isoformat(), points=[])

        weights = {int(r["asset_id"]): float(r["weight_pct"]) for r in alloc_rows}
        baseline: dict[int, float] = {}
        current_px: dict[int, float] = {}
        updates_by_ts: dict[datetime, list[tuple[int, float]]] = defaultdict(list)

        for row in tick_rows:
            aid = int(row["asset_id"])
            px = float(row["last"])
            if px <= 0:
                continue
            ts_value = row["ts"]
            if not isinstance(ts_value, datetime):
                continue
            if aid not in baseline:
                baseline[aid] = px
            updates_by_ts[ts_value].append((aid, px))

        if not updates_by_ts:
            return PortfolioTargetIntradayResponse(portfolio_id=portfolio_id, date=day.isoformat(), points=[])

        points: list[PortfolioTargetIntradayPoint] = []
        for ts_value in sorted(updates_by_ts.keys()):
            for aid, px in updates_by_ts[ts_value]:
                current_px[aid] = px

            weighted_sum = 0.0
            active_weight = 0.0
            for aid, base_px in baseline.items():
                px = current_px.get(aid)
                if px is None or base_px <= 0:
                    continue
                w = weights.get(aid, 0.0)
                if w <= 0:
                    continue
                weighted_sum += (px / base_px) * w
                active_weight += w

            if active_weight <= 0:
                continue

            points.append(
                PortfolioTargetIntradayPoint(
                    ts=ts_value.isoformat(),
                    weighted_index=round((weighted_sum / active_weight) * 100.0, 4),
                )
            )

        return PortfolioTargetIntradayResponse(portfolio_id=portfolio_id, date=day.isoformat(), points=points)

    def get_portfolio_target_asset_performance(self, portfolio_id: int) -> PortfolioTargetAssetPerformanceResponse:
        end_date = date.today()
        start_date = end_date - timedelta(days=364)

        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")

            alloc_rows = conn.execute(
                text(
                    """
                    select pta.asset_id,
                           pta.weight_pct::float8 as weight_pct,
                           a.symbol,
                           coalesce(a.name, a.symbol) as name
                    from portfolio_target_allocations pta
                    join assets a on a.id = pta.asset_id
                    where pta.portfolio_id = :portfolio_id
                    order by pta.weight_pct desc, a.symbol asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            if not alloc_rows:
                return PortfolioTargetAssetPerformanceResponse(portfolio_id=portfolio_id, points_count=0, assets=[])

            asset_ids = [int(r["asset_id"]) for r in alloc_rows]
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
            latest_tick_rows = conn.execute(
                text(
                    """
                    select distinct on (asset_id) asset_id, ts
                    from price_ticks
                    where asset_id = any(:asset_ids)
                    order by asset_id, ts desc
                    """
                ),
                {"asset_ids": asset_ids},
            ).mappings().all()

        alloc_meta = {
            int(r["asset_id"]): {
                "weight_pct": float(r["weight_pct"]),
                "symbol": str(r["symbol"]),
                "name": str(r["name"]),
            }
            for r in alloc_rows
        }
        latest_tick_ts = {
            int(r["asset_id"]): r["ts"] if isinstance(r["ts"], datetime) else None
            for r in latest_tick_rows
        }

        price_series: dict[int, list[tuple[date, float]]] = defaultdict(list)
        for row in price_rows:
            aid = int(row["asset_id"])
            px = float(row["close"])
            if px <= 0:
                continue
            price_series[aid].append((row["price_date"], px))

        baseline: dict[int, float] = {}
        for aid, series in price_series.items():
            last_before_or_on: float | None = None
            first_after_or_on: float | None = None
            for d, px in series:
                if d <= start_date:
                    last_before_or_on = px
                if d >= start_date and first_after_or_on is None:
                    first_after_or_on = px
            base_px = last_before_or_on if last_before_or_on is not None else first_after_or_on
            if base_px is not None and base_px > 0:
                baseline[aid] = base_px

        if not baseline:
            return PortfolioTargetAssetPerformanceResponse(portfolio_id=portfolio_id, points_count=0, assets=[])

        assets_out: list[PortfolioTargetAssetPerformanceSeries] = []
        point_count = (end_date - start_date).days + 1

        for row in alloc_rows:
            aid = int(row["asset_id"])
            if aid not in baseline:
                continue

            series = price_series.get(aid, [])
            idx = -1
            current_px: float | None = None
            points: list[PortfolioTargetAssetPerformancePoint] = []
            cursor = start_date
            while cursor <= end_date:
                while idx + 1 < len(series) and series[idx + 1][0] <= cursor:
                    idx += 1
                current_px = series[idx][1] if idx >= 0 else None
                value = (current_px / baseline[aid] * 100.0) if (current_px is not None and baseline[aid] > 0) else 0.0
                points.append(
                    PortfolioTargetAssetPerformancePoint(
                        date=cursor.isoformat(),
                        index_value=round(value, 4),
                    )
                )
                cursor += timedelta(days=1)

            latest_px = series[-1][1] if series else baseline[aid]
            ret = (latest_px / baseline[aid] - 1.0) * 100.0 if baseline[aid] > 0 else 0.0
            meta = alloc_meta[aid]
            assets_out.append(
                PortfolioTargetAssetPerformanceSeries(
                    asset_id=aid,
                    symbol=str(meta["symbol"]),
                    name=str(meta["name"]),
                    weight_pct=float(meta["weight_pct"]),
                    return_pct=round(ret, 2),
                    as_of=latest_tick_ts.get(aid),
                    points=points,
                )
            )

        return PortfolioTargetAssetPerformanceResponse(
            portfolio_id=portfolio_id,
            points_count=point_count,
            assets=assets_out,
        )

    def get_portfolio_target_asset_intraday_performance(
        self, portfolio_id: int, day: date
    ) -> PortfolioTargetAssetIntradayPerformanceResponse:
        day_start = datetime.combine(day, time.min)
        day_end = day_start + timedelta(days=1)

        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")

            alloc_rows = conn.execute(
                text(
                    """
                    select pta.asset_id,
                           pta.weight_pct::float8 as weight_pct,
                           a.symbol,
                           coalesce(a.name, a.symbol) as name
                    from portfolio_target_allocations pta
                    join assets a on a.id = pta.asset_id
                    where pta.portfolio_id = :portfolio_id
                    order by pta.weight_pct desc, a.symbol asc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

            if not alloc_rows:
                return PortfolioTargetAssetIntradayPerformanceResponse(
                    portfolio_id=portfolio_id, date=day.isoformat(), assets=[]
                )

            asset_ids = [int(r["asset_id"]) for r in alloc_rows]
            tick_rows = conn.execute(
                text(
                    """
                    select asset_id, ts, last::float8 as last
                    from price_ticks
                    where asset_id = any(:asset_ids)
                      and ts >= :day_start
                      and ts < :day_end
                    order by asset_id asc, ts asc
                    """
                ),
                {"asset_ids": asset_ids, "day_start": day_start, "day_end": day_end},
            ).mappings().all()

        ticks_by_asset: dict[int, list[tuple[datetime, float]]] = defaultdict(list)
        for row in tick_rows:
            aid = int(row["asset_id"])
            ts_value = row["ts"]
            px = float(row["last"])
            if not isinstance(ts_value, datetime) or px <= 0:
                continue
            ticks_by_asset[aid].append((ts_value, px))

        assets_out: list[PortfolioTargetAssetIntradayPerformanceSeries] = []
        for row in alloc_rows:
            aid = int(row["asset_id"])
            series = ticks_by_asset.get(aid, [])
            if not series:
                points: list[PortfolioTargetAssetIntradayPerformancePoint] = []
                ret = 0.0
                as_of = None
            else:
                base_px = series[0][1]
                points = [
                    PortfolioTargetAssetIntradayPerformancePoint(
                        ts=ts_value.isoformat(),
                        weighted_index=round((px / base_px) * 100.0, 4),
                    )
                    for ts_value, px in series
                    if base_px > 0
                ]
                ret = round(((series[-1][1] / base_px) - 1.0) * 100.0, 2) if base_px > 0 else 0.0
                as_of = series[-1][0]

            assets_out.append(
                PortfolioTargetAssetIntradayPerformanceSeries(
                    asset_id=aid,
                    symbol=str(row["symbol"]),
                    name=str(row["name"]),
                    weight_pct=float(row["weight_pct"]),
                    return_pct=ret,
                    as_of=as_of,
                    points=points,
                )
            )

        return PortfolioTargetAssetIntradayPerformanceResponse(
            portfolio_id=portfolio_id,
            date=day.isoformat(),
            assets=assets_out,
        )

    def list_portfolios(self) -> list[PortfolioRead]:
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select id, name, base_currency, timezone, target_notional, cash_balance, created_at
                    from portfolios
                    order by created_at desc, id desc
                    """
                )
            ).mappings().all()

        return [
            PortfolioRead(
                id=int(row["id"]),
                name=str(row["name"]),
                base_currency=str(row["base_currency"]),
                timezone=str(row["timezone"]),
                target_notional=float(row["target_notional"]) if row["target_notional"] is not None else None,
                cash_balance=float(row["cash_balance"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    def create_portfolio(self, payload: PortfolioCreate) -> PortfolioRead:
        name = payload.name.strip()
        base_currency = payload.base_currency.strip().upper()
        timezone = payload.timezone.strip()
        target_notional = float(payload.target_notional) if payload.target_notional is not None else None
        cash_balance = float(payload.cash_balance)

        if not name:
            raise ValueError("Nome portfolio obbligatorio")
        if not timezone:
            raise ValueError("Timezone obbligatoria")

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    insert into portfolios (name, base_currency, timezone, target_notional, cash_balance)
                    values (:name, :base_currency, :timezone, :target_notional, :cash_balance)
                    returning id, name, base_currency, timezone, target_notional, cash_balance, created_at
                    """
                ),
                {
                    "name": name,
                    "base_currency": base_currency,
                    "timezone": timezone,
                    "target_notional": target_notional,
                    "cash_balance": cash_balance,
                },
            ).mappings().fetchone()

        if row is None:
            raise ValueError("Impossibile creare portfolio")

        return PortfolioRead(
            id=int(row["id"]),
            name=str(row["name"]),
            base_currency=str(row["base_currency"]),
            timezone=str(row["timezone"]),
            target_notional=float(row["target_notional"]) if row["target_notional"] is not None else None,
            cash_balance=float(row["cash_balance"]),
            created_at=row["created_at"],
        )

    def update_portfolio(self, portfolio_id: int, payload: PortfolioUpdate) -> PortfolioRead:
        updates = payload.model_dump(exclude_unset=True)
        if not updates:
            raise ValueError("Nessun campo da aggiornare")

        set_clauses: list[str] = []
        params: dict[str, object] = {"id": portfolio_id}

        if "name" in updates:
            name = str(updates["name"]).strip()
            if not name:
                raise ValueError("Nome portfolio obbligatorio")
            params["name"] = name
            set_clauses.append("name = :name")

        if "base_currency" in updates:
            base_currency = str(updates["base_currency"]).strip().upper()
            if len(base_currency) != 3:
                raise ValueError("Valuta base non valida")
            params["base_currency"] = base_currency
            set_clauses.append("base_currency = :base_currency")

        if "timezone" in updates:
            timezone = str(updates["timezone"]).strip()
            if not timezone:
                raise ValueError("Timezone obbligatoria")
            params["timezone"] = timezone
            set_clauses.append("timezone = :timezone")

        if "target_notional" in updates:
            raw_target_notional = updates["target_notional"]
            params["target_notional"] = None if raw_target_notional is None else float(raw_target_notional)
            set_clauses.append("target_notional = :target_notional")

        if "cash_balance" in updates:
            raw_cash_balance = updates["cash_balance"]
            if raw_cash_balance is None or float(raw_cash_balance) < 0:
                raise ValueError("Cash balance non valido")
            params["cash_balance"] = float(raw_cash_balance)
            set_clauses.append("cash_balance = :cash_balance")

        if not set_clauses:
            raise ValueError("Nessun campo valido da aggiornare")

        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    f"""
                    update portfolios
                    set {", ".join(set_clauses)}
                    where id = :id
                    returning id, name, base_currency, timezone, target_notional, cash_balance, created_at
                    """
                )
                ,
                params,
            ).mappings().fetchone()

        if row is None:
            raise ValueError("Portfolio non trovato")

        return PortfolioRead(
            id=int(row["id"]),
            name=str(row["name"]),
            base_currency=str(row["base_currency"]),
            timezone=str(row["timezone"]),
            target_notional=float(row["target_notional"]) if row["target_notional"] is not None else None,
            cash_balance=float(row["cash_balance"]),
            created_at=row["created_at"],
        )

    def delete_portfolio(self, portfolio_id: int) -> None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text("delete from portfolios where id = :id returning id"),
                {"id": portfolio_id},
            ).fetchone()

        if row is None:
            raise ValueError("Portfolio non trovato")

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

    def get_asset_pricing_symbol(self, asset_id: int, provider: str = "yfinance") -> PricingAsset:
        provider_name = provider.strip().lower()
        with self.engine.begin() as conn:
            row = conn.execute(
                text(
                    """
                    select a.id as asset_id,
                           a.symbol,
                           coalesce(aps.provider_symbol, a.symbol) as provider_symbol
                    from assets a
                    left join asset_provider_symbols aps
                      on aps.asset_id = a.id
                     and aps.provider = :provider
                    where a.id = :asset_id
                    """
                ),
                {"asset_id": asset_id, "provider": provider_name},
            ).mappings().fetchone()
        if row is None:
            raise ValueError("Asset non trovato")
        return PricingAsset(
            asset_id=int(row["asset_id"]),
            symbol=str(row["symbol"]),
            provider_symbol=str(row["provider_symbol"]),
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
                self._assert_non_negative_inventory_timeline(
                    conn,
                    payload.portfolio_id,
                    payload.asset_id,
                    candidate={
                        "id": None,
                        "trade_at": payload.trade_at,
                        "side": side,
                        "quantity": float(payload.quantity),
                    },
                )

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

    def list_transactions(self, portfolio_id: int) -> list[TransactionListItem]:
        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")

            rows = conn.execute(
                text(
                    """
                    select t.id,
                           t.portfolio_id,
                           t.asset_id,
                           t.side,
                           t.trade_at,
                           t.quantity::float8 as quantity,
                           t.price::float8 as price,
                           t.fees::float8 as fees,
                           t.taxes::float8 as taxes,
                           t.trade_currency,
                           t.notes,
                           a.symbol,
                           a.name as asset_name
                    from transactions t
                    join assets a on a.id = t.asset_id
                    where t.portfolio_id = :portfolio_id
                    order by t.trade_at desc, t.id desc
                    """
                ),
                {"portfolio_id": portfolio_id},
            ).mappings().all()

        return [
            TransactionListItem(
                id=int(row["id"]),
                portfolio_id=int(row["portfolio_id"]),
                asset_id=int(row["asset_id"]),
                side=str(row["side"]),
                trade_at=row["trade_at"],
                quantity=float(row["quantity"]),
                price=float(row["price"]),
                fees=float(row["fees"]),
                taxes=float(row["taxes"]),
                trade_currency=str(row["trade_currency"]),
                notes=row["notes"],
                symbol=str(row["symbol"]),
                asset_name=row["asset_name"],
            )
            for row in rows
        ]

    def update_transaction(self, transaction_id: int, payload: TransactionUpdate) -> TransactionRead:
        updates = payload.model_dump(exclude_unset=True)
        with self.engine.begin() as conn:
            existing = self._get_transaction(conn, transaction_id)
            if existing is None:
                raise ValueError("Transazione non trovata")

            if "trade_at" in updates or "quantity" in updates:
                candidate_trade_at = updates.get("trade_at", existing["trade_at"])
                if candidate_trade_at is None:
                    raise ValueError("trade_at non puo essere nullo")
                self._assert_non_negative_inventory_timeline(
                    conn,
                    int(existing["portfolio_id"]),
                    int(existing["asset_id"]),
                    candidate={
                        "id": int(existing["id"]),
                        "trade_at": candidate_trade_at,
                        "side": str(existing["side"]),
                        "quantity": float(updates.get("quantity", existing["quantity"])),
                    },
                    exclude_transaction_id=transaction_id,
                )

            if updates:
                assignments = ", ".join(f"{field} = :{field}" for field in updates.keys())
                conn.execute(
                    text(f"update transactions set {assignments} where id = :transaction_id"),
                    {"transaction_id": transaction_id, **updates},
                )
                existing = self._get_transaction(conn, transaction_id)
                if existing is None:
                    raise ValueError("Transazione non trovata")

        return TransactionRead(
            id=int(existing["id"]),
            portfolio_id=int(existing["portfolio_id"]),
            asset_id=int(existing["asset_id"]),
            side=str(existing["side"]),
            trade_at=existing["trade_at"],
            quantity=float(existing["quantity"]),
            price=float(existing["price"]),
            fees=float(existing["fees"]),
            taxes=float(existing["taxes"]),
            trade_currency=str(existing["trade_currency"]),
            notes=existing["notes"],
        )

    def delete_transaction(self, transaction_id: int) -> None:
        with self.engine.begin() as conn:
            existing = self._get_transaction(conn, transaction_id)
            if existing is None:
                raise ValueError("Transazione non trovata")
            self._assert_non_negative_inventory_timeline(
                conn,
                int(existing["portfolio_id"]),
                int(existing["asset_id"]),
                exclude_transaction_id=transaction_id,
            )
            deleted = conn.execute(
                text("delete from transactions where id = :transaction_id"),
                {"transaction_id": transaction_id},
            )
            if deleted.rowcount == 0:
                raise ValueError("Transazione non trovata")

    def get_positions(self, portfolio_id: int) -> list[Position]:
        with self.engine.begin() as conn:
            portfolio = self._get_portfolio(conn, portfolio_id)
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
                if price_info and meta is not None:
                    price_day, latest_close = price_info
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

                positions.append(
                    Position(
                        asset_id=aid,
                        symbol=symbol,
                        name=name,
                        quantity=round(qty, 8),
                        avg_cost=round(avg_cost, 4),
                        market_price=round(market_price, 4),
                        market_value=round(market_value, 2),
                        unrealized_pl=round(pl, 2),
                        unrealized_pl_pct=round(pl_pct, 2),
                        weight=0,  # Placeholder, will be calculated next
                        first_trade_at=first_trade_at_by_asset.get(aid),
                    )
                )

            total_market_value = sum(p.market_value for p in positions)

            if total_market_value > 0:
                for p in positions:
                    p.weight = round((p.market_value / total_market_value) * 100, 2)

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
            cash_balance=portfolio.cash_balance,
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
                    where lower(symbol) like :q
                       or lower(coalesce(name, '')) like :q
                       or lower(coalesce(isin, '')) like :q
                    order by symbol asc
                    limit 25
                    """
                ),
                {"q": q},
            ).mappings().all()

        return [{"id": str(r["id"]), "symbol": r["symbol"], "name": r["name"]} for r in rows]

    def get_assets_for_price_refresh(
        self,
        provider: str,
        portfolio_id: int | None = None,
        asset_scope: str = "target",
    ) -> list[PricingAsset]:
        provider_value = provider.strip().lower()
        scope = (asset_scope or "target").strip().lower()
        if scope not in {"target", "transactions", "all"}:
            raise ValueError("asset_scope non supportato")
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
                if scope == "all":
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
                elif scope == "transactions":
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
                else:  # target
                    rows = conn.execute(
                        text(
                            """
                            select distinct a.id as asset_id,
                                   a.symbol,
                                   coalesce(aps.provider_symbol, a.symbol) as provider_symbol
                            from portfolio_target_allocations pta
                            join assets a on a.id = pta.asset_id
                            left join asset_provider_symbols aps
                              on aps.asset_id = a.id and aps.provider = :provider
                            where pta.portfolio_id = :portfolio_id and a.active = true
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

    def get_price_coverage(self, portfolio_id: int, days: int = 365) -> list[dict]:
        """Return price bar coverage stats for each asset in the portfolio target allocation."""
        with self.engine.begin() as conn:
            if self._get_portfolio(conn, portfolio_id) is None:
                raise ValueError("Portfolio non trovato")
            rows = conn.execute(
                text(
                    """
                    select
                        pta.asset_id,
                        a.symbol,
                        coalesce(a.name, a.symbol) as name,
                        count(pb.price_date) as bar_count,
                        min(pb.price_date) as first_bar,
                        max(pb.price_date) as last_bar
                    from portfolio_target_allocations pta
                    join assets a on a.id = pta.asset_id
                    left join price_bars_1d pb
                        on pb.asset_id = pta.asset_id
                        and pb.price_date >= current_date - :days
                    where pta.portfolio_id = :portfolio_id
                    group by pta.asset_id, a.symbol, a.name
                    order by a.symbol
                    """
                ),
                {"portfolio_id": portfolio_id, "days": days},
            ).mappings().all()

        # ~252 trading days per 365 calendar days
        expected_bars = int(days * 252 / 365)

        result = []
        for r in rows:
            bar_count = int(r["bar_count"])
            coverage_pct = round(bar_count / expected_bars * 100, 1) if expected_bars > 0 else 0.0
            result.append({
                "asset_id": int(r["asset_id"]),
                "symbol": str(r["symbol"]),
                "name": str(r["name"]),
                "bar_count": bar_count,
                "first_bar": r["first_bar"],
                "last_bar": r["last_bar"],
                "expected_bars": expected_bars,
                "coverage_pct": min(coverage_pct, 100.0),
            })
        return result

    def _get_portfolio(self, conn, portfolio_id: int) -> PortfolioData | None:
        row = conn.execute(
            text("select id, base_currency, cash_balance from portfolios where id = :id"),
            {"id": portfolio_id},
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

    def _get_transaction(self, conn, transaction_id: int):
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
                where id = :transaction_id
                """
            ),
            {"transaction_id": transaction_id},
        ).mappings().fetchone()

    def _get_assets(self, conn, asset_ids: list[int]) -> dict[int, dict[str, str]]:
        rows = conn.execute(
            text(
                """
                select id, symbol, name
                from assets
                where id = any(:asset_ids)
                """
            ),
            {"asset_ids": asset_ids},
        ).mappings().all()
        return {int(r["id"]): {"symbol": str(r["symbol"]), "name": str(r["name"])} for r in rows}

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
