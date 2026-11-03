"""Stato persistente della sincronizzazione dei dati di mercato (TASK-54).

Tabelle market_data_sync_runs e market_data_asset_sync
(database/migrations/20261103_01_market_data_sync.sql). Ogni metodo apre una
connessione breve: nessuna connessione resta aperta durante le chiamate al
provider (l'unica tenuta per tutta la run è quella del lock, vedi
services/market_data_sync.PgAdvisoryLock).
"""

import json
from datetime import datetime
from typing import Any

from sqlalchemy import text

_RUN_COLUMNS = (
    "id, trigger, status, started_at, finished_at, steps, "
    "assets_requested, assets_updated, assets_failed, error"
)
MAX_ERROR_CHARS = 500


def _run_row(row) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    steps = out.get("steps")
    if isinstance(steps, str):
        try:
            out["steps"] = json.loads(steps)
        except ValueError:
            out["steps"] = []
    out["steps"] = out.get("steps") or []
    return out


def _short(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value)
    return value if len(value) <= MAX_ERROR_CHARS else value[:MAX_ERROR_CHARS] + "…"


class MarketDataSyncMixin:
    # --- runs -------------------------------------------------------------

    def create_market_data_sync_run(self, trigger: str) -> int:
        """New 'running' run; any other 'running' row is closed as failed (interrupted).

        Called only while holding the sync lock, so another 'running' row can
        only be a run whose process died (restart, OOM) before finishing.
        """
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    update market_data_sync_runs
                       set status = 'failed',
                           finished_at = now(),
                           error = coalesce(error, 'interrotta: processo terminato prima della fine')
                     where status = 'running'
                    """
                )
            )
            run_id = conn.execute(
                text("insert into market_data_sync_runs (trigger) values (:trigger) returning id"),
                {"trigger": trigger},
            ).scalar_one()
        return int(run_id)

    def update_market_data_sync_run(
        self,
        run_id: int,
        *,
        steps: list[dict],
        status: str | None = None,
        assets_requested: int | None = None,
        assets_updated: int | None = None,
        assets_failed: int | None = None,
        error: str | None = None,
        finished_at: datetime | None = None,
    ) -> None:
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    update market_data_sync_runs
                       set steps = cast(:steps as jsonb),
                           status = coalesce(:status, status),
                           assets_requested = coalesce(:assets_requested, assets_requested),
                           assets_updated = coalesce(:assets_updated, assets_updated),
                           assets_failed = coalesce(:assets_failed, assets_failed),
                           error = coalesce(:error, error),
                           finished_at = coalesce(:finished_at, finished_at)
                     where id = :run_id
                    """
                ),
                {
                    "run_id": run_id,
                    "steps": json.dumps(steps, default=str),
                    "status": status,
                    "assets_requested": assets_requested,
                    "assets_updated": assets_updated,
                    "assets_failed": assets_failed,
                    "error": _short(error),
                    "finished_at": finished_at,
                },
            )

    def get_market_data_sync_overview(self) -> dict[str, Any]:
        """{'last_run', 'last_success', 'last_finished', 'running'}: rows as dicts or None (short reads)."""
        with self.engine.begin() as conn:
            last_run = conn.execute(
                text(f"select {_RUN_COLUMNS} from market_data_sync_runs order by started_at desc, id desc limit 1")
            ).mappings().first()
            last_success = conn.execute(
                text(
                    f"select {_RUN_COLUMNS} from market_data_sync_runs where status = 'success' "
                    "order by finished_at desc limit 1"
                )
            ).mappings().first()
            last_finished = conn.execute(
                text(
                    f"select {_RUN_COLUMNS} from market_data_sync_runs where status <> 'running' "
                    "and finished_at is not null order by finished_at desc limit 1"
                )
            ).mappings().first()
            running = conn.execute(
                text(
                    f"select {_RUN_COLUMNS} from market_data_sync_runs where status = 'running' "
                    "order by started_at desc limit 1"
                )
            ).mappings().first()
        return {
            "last_run": _run_row(last_run),
            "last_success": _run_row(last_success),
            "last_finished": _run_row(last_finished),
            "running": _run_row(running),
        }

    def get_market_data_sync_run(self, run_id: int) -> dict[str, Any] | None:
        with self.engine.begin() as conn:
            row = conn.execute(
                text(f"select {_RUN_COLUMNS} from market_data_sync_runs where id = :id"), {"id": run_id}
            ).mappings().first()
        return _run_row(row)

    # --- per-asset state -------------------------------------------------

    def upsert_market_data_asset_sync(self, rows: list[dict]) -> None:
        """Merge per-asset state; omitted (None) fields keep the stored value.

        A row with last_success_at and no last_error clears the stored error.
        """
        if not rows:
            return
        payload = [
            {
                "asset_id": int(r["asset_id"]),
                "last_success_at": r.get("last_success_at"),
                "last_bar_date": r.get("last_bar_date"),
                "last_tick_at": r.get("last_tick_at"),
                "last_error": _short(r.get("last_error")),
                "last_error_at": r.get("last_error_at"),
            }
            for r in rows
        ]
        with self.engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into market_data_asset_sync
                        (asset_id, last_success_at, last_bar_date, last_tick_at, last_error, last_error_at)
                    values (:asset_id, :last_success_at, :last_bar_date, :last_tick_at, :last_error, :last_error_at)
                    on conflict (asset_id) do update set
                        last_success_at = coalesce(excluded.last_success_at, market_data_asset_sync.last_success_at),
                        last_bar_date = coalesce(excluded.last_bar_date, market_data_asset_sync.last_bar_date),
                        last_tick_at = coalesce(excluded.last_tick_at, market_data_asset_sync.last_tick_at),
                        last_error = case
                            when excluded.last_error is not null then excluded.last_error
                            when excluded.last_success_at is not null then null
                            else market_data_asset_sync.last_error end,
                        last_error_at = case
                            when excluded.last_error is not null then excluded.last_error_at
                            when excluded.last_success_at is not null then null
                            else market_data_asset_sync.last_error_at end
                    """
                ),
                payload,
            )

    def get_market_data_asset_sync(self, asset_ids: list[int]) -> dict[int, dict[str, Any]]:
        if not asset_ids:
            return {}
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select asset_id, last_success_at, last_bar_date, last_tick_at, last_error, last_error_at
                    from market_data_asset_sync
                    where asset_id = any(:asset_ids)
                    """
                ),
                {"asset_ids": list(asset_ids)},
            ).mappings().all()
        return {int(r["asset_id"]): dict(r) for r in rows}

    # --- currencies in use --------------------------------------------------

    def get_fx_pairs_in_use(self) -> list[tuple[str, str]]:
        """(from, to) pairs needed by the portfolios: trade or quote currency -> base currency."""
        with self.engine.begin() as conn:
            rows = conn.execute(
                text(
                    """
                    select distinct upper(x.ccy) as from_ccy, upper(p.base_currency) as to_ccy
                    from (
                        select t.portfolio_id, t.trade_currency as ccy
                        from transactions t
                        where t.trade_currency is not null
                        union
                        select t.portfolio_id, a.quote_currency
                        from transactions t join assets a on a.id = t.asset_id
                        union
                        select pta.portfolio_id, a.quote_currency
                        from portfolio_target_allocations pta join assets a on a.id = pta.asset_id
                    ) x
                    join portfolios p on p.id = x.portfolio_id
                    where x.ccy is not null and x.ccy <> ''
                      and upper(x.ccy) <> upper(p.base_currency)
                    order by 1, 2
                    """
                )
            ).mappings().all()
        return [(str(r["from_ccy"]), str(r["to_ccy"])) for r in rows]

