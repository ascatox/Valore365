-- Step 4: Make idempotency uniqueness user-scoped
alter table api_idempotency_keys
  drop constraint if exists api_idempotency_keys_pkey;

alter table api_idempotency_keys
  add primary key (idempotency_key, endpoint, owner_user_id);
