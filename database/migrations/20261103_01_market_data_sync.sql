-- TASK-54: stato persistente della sincronizzazione dei dati di mercato.
-- Additiva e idempotente: nessuna tabella esistente viene modificata.
--   market_data_sync_runs  : una riga per esecuzione (startup, trigger esterno,
--                            scheduler interno, manuale), con l'esito dei passi.
--   market_data_asset_sync : ultimo stato noto per asset (ultima barra, ultimo
--                            tick, ultimo errore).
-- last_successful_price_sync = finished_at dell'ultima run con status 'success'.
-- Tabelle solo backend: RLS attiva senza policy, quindi nessun accesso dalle API
-- Supabase (anon/authenticated); il backend usa il ruolo proprietario, che la
-- RLS non limita (come in 20260302_01_enable_rls.sql).
-- Copia identica in src/backend/app/sql/migrations/create_market_data_sync.sql,
-- applicata anche all'avvio del backend.

create table if not exists market_data_sync_runs (
  id bigserial primary key,
  trigger text not null check (trigger in ('startup', 'external', 'scheduler', 'manual')),
  status text not null default 'running' check (status in ('running', 'success', 'partial', 'failed')),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  steps jsonb not null default '[]'::jsonb,
  assets_requested int not null default 0,
  assets_updated int not null default 0,
  assets_failed int not null default 0,
  error text
);

create index if not exists idx_market_data_sync_runs_status_finished
  on market_data_sync_runs (status, finished_at desc);

create table if not exists market_data_asset_sync (
  asset_id bigint primary key references assets(id) on delete cascade,
  last_success_at timestamptz,
  last_bar_date date,
  last_tick_at timestamptz,
  last_error text,
  last_error_at timestamptz
);

alter table market_data_sync_runs enable row level security;
alter table market_data_asset_sync enable row level security;
