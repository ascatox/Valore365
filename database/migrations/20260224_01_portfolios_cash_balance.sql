alter table portfolios
  add column if not exists cash_balance numeric(28,10) not null default 0
  check (cash_balance >= 0);
