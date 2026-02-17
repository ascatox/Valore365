-- Performance indexes
create index if not exists idx_tx_portfolio_asset_trade
  on transactions(portfolio_id, asset_id, trade_at);

create index if not exists idx_price_bars_1d_asset_date_desc
  on price_bars_1d(asset_id, price_date desc);

create index if not exists idx_fx_rates_1d_pair_date_desc
  on fx_rates_1d(from_ccy, to_ccy, price_date desc);

-- API idempotency storage
create table if not exists api_idempotency_keys (
  idempotency_key varchar(128) not null,
  endpoint text not null,
  response_json jsonb not null,
  created_at timestamptz not null default now(),
  primary key (idempotency_key, endpoint)
);
