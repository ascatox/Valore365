-- Step 3: Set NOT NULL constraint (deploy AFTER code writes owner_user_id)
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
