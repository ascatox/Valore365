-- Step 1: Add owner_user_id nullable column to user-scoped tables
alter table portfolios
  add column if not exists owner_user_id varchar(255);

alter table transactions
  add column if not exists owner_user_id varchar(255);

alter table portfolio_target_allocations
  add column if not exists owner_user_id varchar(255);

alter table api_idempotency_keys
  add column if not exists owner_user_id varchar(255);
