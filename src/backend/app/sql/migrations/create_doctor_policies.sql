-- Portfolio Doctor 2.0: policy personali dell'utente (vincoli di portafoglio),
-- versionate, con token di conferma monouso (docs/doctor2/api-contracts.md §6).
-- Additiva e idempotente: nessuna tabella esistente viene modificata.
--   doctor_policy_sets          : una policy attiva per (utente, scope esatto);
--                                 scope = insieme di portafogli (fingerprint
--                                 "p:<id>,<id>" con id ordinati). Le policy
--                                 aggregate sono indipendenti dalle singole.
--   doctor_policy_scope_members : portafogli dello scope. Nessuna FK verso
--                                 portfolios: un portafoglio cancellato non
--                                 cancella la policy, che diventa illeggibile
--                                 (la proprieta viene verificata a ogni lettura).
--   doctor_policy_versions      : storico immutabile dei documenti (jsonb),
--                                 una riga per salvataggio/ripristino.
--   doctor_confirmation_tokens  : token monouso emessi dalla preview; si salva
--                                 solo lo sha256, mai il token in chiaro.
-- Tabelle solo backend: RLS attiva senza policy, quindi nessun accesso dalle API
-- Supabase (anon/authenticated); il backend usa il ruolo proprietario, che la
-- RLS non limita (come in 20260302_01_enable_rls.sql).
-- Copia identica in src/backend/app/sql/migrations/create_doctor_policies.sql,
-- applicata anche all'avvio del backend.

create table if not exists doctor_policy_sets (
  id bigserial primary key,
  owner_user_id text not null,
  scope_type text not null check (scope_type in ('single', 'aggregate')),
  scope_fingerprint text not null,
  name text not null,
  active boolean not null default true,
  current_version int not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  archived_at timestamptz
);

create unique index if not exists uq_doctor_policy_sets_owner_scope
  on doctor_policy_sets (owner_user_id, scope_fingerprint)
  where archived_at is null;

create table if not exists doctor_policy_scope_members (
  policy_set_id bigint not null references doctor_policy_sets(id) on delete cascade,
  portfolio_id bigint not null,
  primary key (policy_set_id, portfolio_id)
);

create index if not exists idx_doctor_policy_scope_members_portfolio
  on doctor_policy_scope_members (portfolio_id);

create table if not exists doctor_policy_versions (
  id bigserial primary key,
  policy_set_id bigint not null references doctor_policy_sets(id) on delete cascade,
  version_number int not null check (version_number >= 1),
  schema_version int not null,
  constraints jsonb not null,
  document_hash text not null,
  source text not null check (source in ('manual', 'copilot', 'template', 'restore')),
  diff jsonb not null default '[]'::jsonb,
  confirmed_at timestamptz not null default now(),
  actor_user_id text not null,
  unique (policy_set_id, version_number)
);

create table if not exists doctor_confirmation_tokens (
  token_hash text primary key,
  owner_user_id text not null,
  scope_fingerprint text not null,
  document_hash text not null,
  base_version int,
  source text not null default 'manual' check (source in ('manual', 'copilot', 'template')),
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  used_at timestamptz
);

create index if not exists idx_doctor_confirmation_tokens_expires
  on doctor_confirmation_tokens (expires_at);

alter table doctor_policy_sets enable row level security;
alter table doctor_policy_scope_members enable row level security;
alter table doctor_policy_versions enable row level security;
alter table doctor_confirmation_tokens enable row level security;
