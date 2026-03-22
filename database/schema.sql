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
  supports_fractions boolean not null default true,
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

create table asset_metadata (
  asset_id bigint primary key references assets(id) on delete cascade,
  expense_ratio numeric,
  fund_family text,
  total_assets numeric,
  category text,
  sector text,
  industry text,
  country text,
  market_cap numeric,
  trailing_pe numeric,
  forward_pe numeric,
  dividend_yield numeric,
  dividend_rate numeric,
  beta numeric,
  fifty_two_week_high numeric,
  fifty_two_week_low numeric,
  avg_volume numeric,
  profit_margins numeric,
  return_on_equity numeric,
  revenue_growth numeric,
  earnings_growth numeric,
  description text,
  website text,
  logo_url text,
  raw_info jsonb,
  updated_at timestamptz not null default now()
);

create table etf_enrichment (
  asset_id bigint primary key references assets(id) on delete cascade,
  isin text not null,
  name text,
  description text,
  index_tracked text,
  investment_focus text,
  country_weights jsonb,
  sector_weights jsonb,
  top_holdings jsonb,
  holdings_date text,
  replication_method text,
  distribution_policy text,
  distribution_frequency text,
  fund_currency text,
  currency_hedged boolean,
  domicile text,
  fund_provider text,
  fund_size_eur numeric,
  ter numeric,
  volatility_1y numeric,
  sustainability boolean,
  inception_date text,
  source text default 'justetf',
  fetched_at timestamptz not null default now()
);
create index idx_etf_enrichment_isin on etf_enrichment(isin);

create table transactions (
  id bigserial primary key,
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  asset_id bigint references assets(id),
  side text not null check (side in ('buy','sell','deposit','withdrawal','dividend','fee','interest')),
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
create index idx_tx_cash_movements on transactions(portfolio_id, trade_at) where asset_id is null;

create table price_ticks (
  asset_id bigint not null references assets(id) on delete cascade,
  provider text not null,
  ts timestamptz not null,
  last numeric(28,10) not null,
  bid numeric(28,10),
  ask numeric(28,10),
  volume numeric(28,10),
  previous_close numeric(28,10),
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
  copilot_provider varchar(32) not null default '',
  copilot_model varchar(128) not null default '',
  copilot_api_key_enc text not null default '',
  fire_annual_expenses numeric(28,10) not null default 0,
  fire_annual_contribution numeric(28,10) not null default 0,
  fire_expected_return_pct numeric(10,4) not null default 5 check (fire_expected_return_pct > 0 and fire_expected_return_pct <= 20),
  fire_safe_withdrawal_rate numeric(10,4) not null default 4 check (fire_safe_withdrawal_rate > 0 and fire_safe_withdrawal_rate <= 20),
  fire_capital_gains_tax_rate numeric(10,4) not null default 26 check (fire_capital_gains_tax_rate >= 0 and fire_capital_gains_tax_rate <= 100),
  fire_current_age int check (fire_current_age is null or (fire_current_age >= 18 and fire_current_age <= 100)),
  fire_target_age int check (fire_target_age is null or (fire_target_age >= 18 and fire_target_age <= 100)),
  updated_at timestamptz not null default now()
);

create table app_users (
  user_id varchar(255) primary key,
  email varchar(320),
  last_sign_in_at timestamptz,
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index idx_app_users_email on app_users(email);
create index idx_app_users_last_seen_at on app_users(last_seen_at desc);

create table public_instant_analyzer_events (
  id bigserial primary key,
  client_ip_hash varchar(64),
  input_mode varchar(32) not null,
  positions_count int not null default 0,
  success boolean not null default false,
  created_at timestamptz not null default now()
);

create index idx_public_instant_analyzer_events_created_at
  on public_instant_analyzer_events(created_at desc);
create index idx_public_instant_analyzer_events_client_ip_hash
  on public_instant_analyzer_events(client_ip_hash);

create table portfolio_target_allocations (
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  asset_id bigint not null references assets(id),
  weight_pct numeric(9,4) not null check (weight_pct >= 0 and weight_pct <= 100),
  owner_user_id varchar(255) not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary key (portfolio_id, asset_id)
);

create table csv_import_batches (
  id bigserial primary key,
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  owner_user_id varchar(255) not null,
  status text not null check (status in ('pending','committed','cancelled')) default 'pending',
  original_filename text,
  total_rows int not null default 0,
  valid_rows int not null default 0,
  error_rows int not null default 0,
  preview_data jsonb not null default '[]',
  created_at timestamptz not null default now(),
  committed_at timestamptz
);

create table pac_rules (
  id bigserial primary key,
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  asset_id bigint not null references assets(id),
  mode text not null check (mode in ('amount','quantity')) default 'amount',
  amount numeric(28,10),
  quantity numeric(28,10),
  frequency text not null check (frequency in ('weekly','biweekly','monthly')),
  day_of_month int check (day_of_month >= 1 and day_of_month <= 28),
  day_of_week int check (day_of_week >= 0 and day_of_week <= 6),
  start_date date not null,
  end_date date,
  auto_execute boolean not null default false,
  active boolean not null default true,
  owner_user_id varchar(255) not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create table pac_executions (
  id bigserial primary key,
  pac_rule_id bigint not null references pac_rules(id) on delete cascade,
  scheduled_date date not null,
  status text not null check (status in ('pending','executed','skipped','failed')) default 'pending',
  transaction_id bigint references transactions(id) on delete set null,
  executed_price numeric(28,10),
  executed_quantity numeric(28,10),
  error_message text,
  created_at timestamptz not null default now(),
  executed_at timestamptz,
  unique (pac_rule_id, scheduled_date)
);
