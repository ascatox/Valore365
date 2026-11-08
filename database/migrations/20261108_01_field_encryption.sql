-- TASK-57: cifratura a livello di campo dei dati personali (docs/field-encryption.md).
-- Additiva e idempotente; va applicata PRIMA del deploy del backend che la usa.
--   user_data_keys : una DEK casuale per utente, cifrata (wrapped) con la KEK
--                    attiva di DATA_ENCRYPTION_KEYS (kek_id = kid della KEK).
--                    Cancellare la riga rende illeggibili i dati cifrati
--                    dell'utente (crypto-shredding).
--   app_users.email            -> cifrata; email_bidx = blind index HMAC-SHA256
--                                 dell'email normalizzata (trim + minuscole),
--                                 usato per le ricerche per uguaglianza.
--   csv_import_batches         -> original_filename e preview_data cifrati;
--                                 source_sha256 in colonna dedicata (in chiaro,
--                                 e' l'hash del file) e original_filename_bidx
--                                 per il rilevamento degli import duplicati.
--   portfolios.name, transactions.notes, doctor_policy_sets.name -> cifrati,
--                                 nessuna modifica di schema (gia' text).
-- I valori cifrati sono testo "enc:v1:..." (jsonb {"_enc": "enc:v1:..."} per
-- preview_data); i valori in chiaro esistenti restano leggibili finche' lo script
-- scripts/encrypt_existing_data.py non li cifra.
-- Tabella solo backend: RLS attiva senza policy, quindi nessun accesso dalle API
-- Supabase (anon/authenticated); il backend usa il ruolo proprietario, che la
-- RLS non limita (come in 20260302_01_enable_rls.sql).

create table if not exists user_data_keys (
  user_id varchar(255) primary key,
  kek_id text not null,
  wrapped_dek bytea not null,
  created_at timestamptz not null default now(),
  rotated_at timestamptz
);

create index if not exists idx_user_data_keys_kek_id on user_data_keys (kek_id);

alter table user_data_keys enable row level security;

-- app_users.email: il testo cifrato supera i 320 caratteri di un'email lunga.
alter table app_users alter column email type text;
alter table app_users add column if not exists email_bidx text;
-- L'indice sull'email in chiaro non serve piu' (le ricerche usano email_bidx).
drop index if exists idx_app_users_email;
create index if not exists idx_app_users_email_bidx on app_users (email_bidx);

alter table csv_import_batches add column if not exists original_filename_bidx text;
alter table csv_import_batches add column if not exists source_sha256 text;

-- Backfill dell'hash dal jsonb in chiaro (batch creati prima della cifratura).
update csv_import_batches
   set source_sha256 = preview_data->>'source_sha256'
 where source_sha256 is null
   and jsonb_typeof(preview_data) = 'object'
   and preview_data ? 'source_sha256'
   and preview_data->>'source_sha256' is not null;

create index if not exists idx_csv_import_batches_filename_bidx
  on csv_import_batches (portfolio_id, original_filename_bidx);
create index if not exists idx_csv_import_batches_source_sha256
  on csv_import_batches (portfolio_id, source_sha256);
