-- One-off migration: reassign user-scoped rows from a legacy user (e.g. dev-user)
-- to a real authenticated user after enabling multi-user scoping.
--
-- Usage (psql):
--   psql "$DATABASE_URL" \
--     -v old_user_id='dev-user' \
--     -v new_user_id='YOUR_REAL_USER_ID' \
--     -f database/migrations/20260226_06_reassign_user_owned_data.sql
--
-- IMPORTANT:
-- - Run only after owner_user_id migrations (20260226_02/03/04)
-- - Ensure old_user_id != new_user_id
-- - This script moves ownership of portfolios and related rows

begin;

-- Portfolios
update portfolios
set owner_user_id = :'new_user_id'
where owner_user_id = :'old_user_id';

-- Transactions
update transactions
set owner_user_id = :'new_user_id'
where owner_user_id = :'old_user_id';

-- Target allocations
update portfolio_target_allocations
set owner_user_id = :'new_user_id'
where owner_user_id = :'old_user_id';

-- Idempotency cache: merge rows without depending on a specific PK shape
-- (works both before and after migration 20260226_05)
update api_idempotency_keys dest
set response_json = src.response_json
from api_idempotency_keys src
where src.owner_user_id = :'old_user_id'
  and dest.owner_user_id = :'new_user_id'
  and dest.idempotency_key = src.idempotency_key
  and dest.endpoint = src.endpoint;

insert into api_idempotency_keys (idempotency_key, endpoint, response_json, owner_user_id, created_at)
select src.idempotency_key, src.endpoint, src.response_json, :'new_user_id', src.created_at
from api_idempotency_keys src
where src.owner_user_id = :'old_user_id'
  and not exists (
    select 1
    from api_idempotency_keys dest
    where dest.owner_user_id = :'new_user_id'
      and dest.idempotency_key = src.idempotency_key
      and dest.endpoint = src.endpoint
  );

delete from api_idempotency_keys
where owner_user_id = :'old_user_id';

-- User settings: merge broker setting if present
insert into app_user_settings (user_id, broker_default_fee, updated_at)
select :'new_user_id', broker_default_fee, updated_at
from app_user_settings
where user_id = :'old_user_id'
on conflict (user_id)
do update set
  broker_default_fee = excluded.broker_default_fee,
  updated_at = greatest(app_user_settings.updated_at, excluded.updated_at);

delete from app_user_settings
where user_id = :'old_user_id';

commit;
