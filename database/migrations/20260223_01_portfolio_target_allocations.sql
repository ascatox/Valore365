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
