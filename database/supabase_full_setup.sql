-- ============================================================
-- Valore365 - Full DB Setup per Supabase SQL Editor
-- Incolla tutto nel SQL Editor ed esegui in un colpo solo.
-- ============================================================

-- ============================================================
-- 1. SCHEMA
-- ============================================================

create table portfolios (
  id bigserial primary key,
  name text not null default 'Valore365 Portfolio',
  base_currency char(3) not null,
  timezone text not null default 'Europe/Rome',
  target_notional numeric(28,10),
  owner_user_id varchar(255) not null default 'dev-user',
  created_at timestamptz not null default now()
);

create index idx_portfolios_owner_user_id on portfolios(owner_user_id);

create table assets (
  id bigserial primary key,
  symbol text not null,
  name text,
  asset_type text not null check (asset_type in ('stock','etf','crypto','bond','cash','fund')),
  exchange_code varchar(16),
  exchange_name text,
  quote_currency char(3) not null,
  isin varchar(12),
  active boolean not null default true,
  unique (symbol, exchange_code)
);

create unique index uq_assets_isin
  on assets(isin)
  where isin is not null;

create table asset_provider_symbols (
  asset_id bigint not null references assets(id) on delete cascade,
  provider text not null,
  provider_symbol text not null,
  primary key (asset_id, provider),
  unique (provider, provider_symbol)
);

create table transactions (
  id bigserial primary key,
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  asset_id bigint not null references assets(id),
  side text not null check (side in ('buy','sell')),
  trade_at timestamptz not null,
  quantity numeric(28,10) not null check (quantity > 0),
  price numeric(28,10) not null check (price >= 0),
  fees numeric(28,10) not null default 0,
  taxes numeric(28,10) not null default 0,
  trade_currency char(3) not null,
  notes text,
  owner_user_id varchar(255) not null default 'dev-user'
);

create index idx_tx_portfolio_time on transactions(portfolio_id, trade_at);
create index idx_tx_asset_time on transactions(asset_id, trade_at);
create index idx_tx_portfolio_asset_trade on transactions(portfolio_id, asset_id, trade_at);
create index idx_transactions_owner_portfolio_trade on transactions(owner_user_id, portfolio_id, trade_at);

create table price_ticks (
  asset_id bigint not null references assets(id) on delete cascade,
  provider text not null,
  ts timestamptz not null,
  last numeric(28,10) not null,
  bid numeric(28,10),
  ask numeric(28,10),
  volume numeric(28,10),
  primary key (asset_id, provider, ts)
);

create index idx_ticks_ts on price_ticks(ts desc);

create table price_bars_1m (
  asset_id bigint not null references assets(id) on delete cascade,
  provider text not null,
  bar_time timestamptz not null,
  open numeric(28,10) not null,
  high numeric(28,10) not null,
  low numeric(28,10) not null,
  close numeric(28,10) not null,
  volume numeric(28,10),
  primary key (asset_id, provider, bar_time)
);

create table price_bars_1d (
  asset_id bigint not null references assets(id) on delete cascade,
  provider text not null,
  price_date date not null,
  open numeric(28,10) not null,
  high numeric(28,10) not null,
  low numeric(28,10) not null,
  close numeric(28,10) not null,
  adj_close numeric(28,10),
  volume numeric(28,10),
  primary key (asset_id, provider, price_date)
);
create index idx_price_bars_1d_asset_date_desc on price_bars_1d(asset_id, price_date desc);

create table fx_rates_1d (
  from_ccy char(3) not null,
  to_ccy char(3) not null,
  price_date date not null,
  rate numeric(28,10) not null check (rate > 0),
  provider text not null,
  primary key (from_ccy, to_ccy, provider, price_date)
);
create index idx_fx_rates_1d_pair_date_desc on fx_rates_1d(from_ccy, to_ccy, price_date desc);

create table api_idempotency_keys (
  idempotency_key varchar(128) not null,
  endpoint text not null,
  response_json jsonb not null,
  owner_user_id varchar(255) not null default 'dev-user',
  created_at timestamptz not null default now(),
  primary key (idempotency_key, endpoint, owner_user_id)
);

create index idx_api_idempotency_keys_owner on api_idempotency_keys(owner_user_id);

create table app_user_settings (
  user_id varchar(255) primary key,
  broker_default_fee numeric(28,10) not null default 0,
  updated_at timestamptz not null default now()
);

-- ============================================================
-- 2. SEED (dati iniziali)
-- ============================================================

insert into portfolios (name, base_currency, timezone, owner_user_id)
values ('Valore365 Portfolio', 'EUR', 'Europe/Rome', 'dev-user')
on conflict do nothing;

insert into assets (symbol, name, asset_type, exchange_code, exchange_name, quote_currency, isin, active)
values
  ('AAPL', 'Apple Inc.', 'stock', 'XNAS', 'NASDAQ', 'USD', 'US0378331005', true),
  ('MSFT', 'Microsoft Corporation', 'stock', 'XNAS', 'NASDAQ', 'USD', 'US5949181045', true),
  ('VWCE', 'Vanguard FTSE All-World UCITS ETF', 'etf', 'XMIL', 'Borsa Italiana', 'EUR', 'IE00BK5BQT80', true)
on conflict (symbol, exchange_code) do update
set
  name = excluded.name,
  asset_type = excluded.asset_type,
  exchange_name = excluded.exchange_name,
  quote_currency = excluded.quote_currency,
  isin = excluded.isin,
  active = excluded.active;

insert into asset_provider_symbols (asset_id, provider, provider_symbol)
select id,
       'yfinance',
       case symbol
           when 'VWCE' then 'VWCE.MI'
           else symbol
       end
from assets
where symbol in ('AAPL', 'MSFT', 'VWCE')
on conflict (asset_id, provider) do update
set provider_symbol = excluded.provider_symbol;

-- ============================================================
-- 3. MIGRAZIONI (applicate in ordine)
-- ============================================================

-- 20260217_01_operational_updates
create index if not exists idx_tx_portfolio_asset_trade
  on transactions(portfolio_id, asset_id, trade_at);

create index if not exists idx_price_bars_1d_asset_date_desc
  on price_bars_1d(asset_id, price_date desc);

create index if not exists idx_fx_rates_1d_pair_date_desc
  on fx_rates_1d(from_ccy, to_ccy, price_date desc);

-- 20260223_01_portfolio_target_allocations
create table if not exists portfolio_target_allocations (
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  asset_id bigint not null references assets(id) on delete cascade,
  weight_pct numeric(9,4) not null check (weight_pct >= 0 and weight_pct <= 100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (portfolio_id, asset_id)
);

create index if not exists idx_portfolio_target_allocations_portfolio
  on portfolio_target_allocations(portfolio_id);

-- 20260223_02_portfolios_target_notional
alter table portfolios
add column if not exists target_notional numeric(28,10);

-- 20260224_01_portfolios_cash_balance
-- (cash_balance gia presente nello schema, ma assicuriamoci)
alter table portfolios
  add column if not exists cash_balance numeric(28,10) not null default 0;

-- 20260224_02_provider_yfinance
update asset_provider_symbols
set provider = 'yfinance'
where provider = 'twelvedata';

-- 20260226_01_app_user_settings
-- (tabella gia creata nello schema, skip)

-- 20260226_02_add_owner_user_id (colonne gia nello schema, ma safe con IF NOT EXISTS)
alter table portfolios
  add column if not exists owner_user_id varchar(255);

alter table transactions
  add column if not exists owner_user_id varchar(255);

alter table portfolio_target_allocations
  add column if not exists owner_user_id varchar(255);

alter table api_idempotency_keys
  add column if not exists owner_user_id varchar(255);

-- 20260226_03_backfill_owner_user_id
update portfolios set owner_user_id = 'dev-user' where owner_user_id is null;
update transactions set owner_user_id = 'dev-user' where owner_user_id is null;
update portfolio_target_allocations set owner_user_id = 'dev-user' where owner_user_id is null;
update api_idempotency_keys set owner_user_id = 'dev-user' where owner_user_id is null;

create index if not exists idx_portfolios_owner_user_id
  on portfolios(owner_user_id);

create index if not exists idx_transactions_owner_portfolio_trade
  on transactions(owner_user_id, portfolio_id, trade_at);

create index if not exists idx_portfolio_target_allocations_owner
  on portfolio_target_allocations(owner_user_id);

create index if not exists idx_api_idempotency_keys_owner
  on api_idempotency_keys(owner_user_id);

-- 20260226_04_owner_user_id_not_null
alter table portfolios
  alter column owner_user_id set default 'dev-user',
  alter column owner_user_id set not null;

alter table transactions
  alter column owner_user_id set default 'dev-user',
  alter column owner_user_id set not null;

alter table portfolio_target_allocations
  alter column owner_user_id set default 'dev-user',
  alter column owner_user_id set not null;

alter table api_idempotency_keys
  alter column owner_user_id set default 'dev-user',
  alter column owner_user_id set not null;

-- 20260226_05_api_idempotency_keys_owner_pk
-- (PK gia definita con owner_user_id nello schema, skip)

-- 20260226_06_reassign_user_owned_data
-- SKIP: richiede variabili psql (old_user_id / new_user_id).
-- Da eseguire manualmente dopo aver attivato Clerk, se serve.

-- ============================================================
-- FATTO! Verifica con: SELECT tablename FROM pg_tables WHERE schemaname = 'public';
-- ============================================================
