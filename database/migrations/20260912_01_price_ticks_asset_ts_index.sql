-- price_ticks is read with "distinct on (asset_id) ... order by asset_id, ts desc"
-- by /positions, /summary and /target-performance, but the only index on the
-- table is idx_ticks_ts(ts desc). Without a leading asset_id every one of those
-- reads has to sort, and the table grows by one row per tracked asset per
-- scheduler run, so the sort gets steadily more expensive.
--
-- CONCURRENTLY keeps writes going while the index builds, which means this
-- statement cannot run inside a transaction block. Run it on its own:
--   psql "$DATABASE_URL" -f database/migrations/20260912_01_price_ticks_asset_ts_index.sql
-- If it is interrupted it leaves an INVALID index behind; drop it and re-run.

create index concurrently if not exists idx_price_ticks_asset_ts
  on price_ticks (asset_id, ts desc);
