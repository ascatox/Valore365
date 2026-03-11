-- Asset metadata from yFinance (TER, sector, market cap, etc.)
create table asset_metadata (
  asset_id bigint primary key references assets(id) on delete cascade,
  -- ETF/Fund fields
  expense_ratio numeric,
  fund_family text,
  total_assets numeric,
  category text,
  -- Stock fields
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
  -- Common
  description text,
  website text,
  logo_url text,
  -- Full raw yFinance info dict
  raw_info jsonb,
  -- Freshness
  updated_at timestamptz not null default now()
);
