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
