from collections import defaultdict
from datetime import date, datetime, time, timedelta

from sqlalchemy import text

from ..models import (
    PortfolioTargetAllocationItem,
    PortfolioTargetAllocationUpsert,
    PortfolioTargetAssetIntradayPerformancePoint,
    PortfolioTargetAssetIntradayPerformanceResponse,
    PortfolioTargetAssetIntradayPerformanceSeries,
    PortfolioTargetAssetPerformancePoint,
    PortfolioTargetAssetPerformanceResponse,
    PortfolioTargetAssetPerformanceSeries,
    PortfolioTargetIntradayPoint,
    PortfolioTargetIntradayResponse,
    PortfolioTargetPerformancePoint,
    PortfolioTargetPerformanceResponse,
    PortfolioTargetPerformer,
)


class TargetAllocationMixin:
    def list_portfolio_target_allocations(self, portfolio_id: int, user_id: str) -> list[PortfolioTargetAllocationItem]:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
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
        self, portfolio_id: int, payload: PortfolioTargetAllocationUpsert, user_id: str
    ) -> PortfolioTargetAllocationItem:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")
            if not self._asset_exists(conn, payload.asset_id):
                raise ValueError("Asset non trovato")

            conn.execute(
                text(
                    """
                    insert into portfolio_target_allocations (portfolio_id, asset_id, weight_pct, owner_user_id)
                    values (:portfolio_id, :asset_id, :weight_pct, :owner_user_id)
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
                    "owner_user_id": user_id,
                },
            )

        items = self.list_portfolio_target_allocations(portfolio_id, user_id)
        for item in items:
            if item.asset_id == payload.asset_id:
                return item
        raise ValueError("Impossibile salvare allocazione target")

    def delete_portfolio_target_allocation(self, portfolio_id: int, asset_id: int, user_id: str) -> None:
        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
                raise ValueError("Portfolio non trovato")
            conn.execute(
                text(
                    """
                    delete from portfolio_target_allocations
                    where portfolio_id = :portfolio_id and asset_id = :asset_id and owner_user_id = :owner_user_id
                    """
                ),
                {"portfolio_id": portfolio_id, "asset_id": asset_id, "owner_user_id": user_id},
            )

    def get_portfolio_target_performance(self, portfolio_id: int, user_id: str) -> PortfolioTargetPerformanceResponse:
        end_date = date.today()
        start_date = end_date - timedelta(days=364)

        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
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

    def get_portfolio_target_intraday_performance(self, portfolio_id: int, day: date, user_id: str) -> PortfolioTargetIntradayResponse:
        day_start = datetime.combine(day, time.min)
        day_end = day_start + timedelta(days=1)

        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
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

    def get_portfolio_target_asset_performance(self, portfolio_id: int, user_id: str) -> PortfolioTargetAssetPerformanceResponse:
        end_date = date.today()
        start_date = end_date - timedelta(days=364)

        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
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
        self, portfolio_id: int, day: date, user_id: str
    ) -> PortfolioTargetAssetIntradayPerformanceResponse:
        day_start = datetime.combine(day, time.min)
        day_end = day_start + timedelta(days=1)

        with self.engine.begin() as conn:
            if self._get_portfolio_for_user(conn, portfolio_id, user_id) is None:
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
