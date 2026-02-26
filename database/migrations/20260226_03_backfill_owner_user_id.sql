-- Step 2: Backfill existing rows with 'dev-user' and create indices
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
