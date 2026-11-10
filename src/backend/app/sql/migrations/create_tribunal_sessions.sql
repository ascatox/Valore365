-- Tribunale del portafoglio: ultima seduta salvata e limite giornaliero
-- (docs/tribunale/api-contracts.md §8.6, §8.7, §3.3; TASK-66).
-- Additiva e idempotente: nessuna tabella esistente viene modificata.
--   tribunal_sessions        : l'ultima seduta conclusa per (utente, scope esatto);
--                              una nuova seduta sullo stesso scope sovrascrive la
--                              riga. payload = TribunalSession (JSON) cifrata a
--                              livello di campo con la DEK dell'utente
--                              ("enc:v1:...", docs/field-encryption.md); hash del
--                              fascicolo, versioni, key_source e date in chiaro.
--   tribunal_session_members : portafogli dello scope della seduta, con FK su
--                              portfolios(id) on delete cascade. Il trigger
--                              trg_tribunal_session_members_cleanup cancella la
--                              seduta appena sparisce uno dei suoi membri: eliminare
--                              un portafoglio elimina la sua seduta singola e ogni
--                              seduta aggregata che lo include.
--   tribunal_daily_usage     : sedute dal vivo concluse e salvate con la chiave del
--                              server, per (utente, giorno di calendario Europe/Rome).
--                              Separato dalle sedute: sovrascrivere o cancellare una
--                              seduta (anche col portafoglio) non restituisce
--                              sedute al limite del giorno.
-- Tabelle solo backend: RLS attiva senza policy, quindi nessun accesso dalle API
-- Supabase (anon/authenticated); il backend usa il ruolo proprietario, che la
-- RLS non limita (come in 20260302_01_enable_rls.sql).
-- Copia identica in src/backend/app/sql/migrations/create_tribunal_sessions.sql,
-- applicata anche all'avvio del backend.

create table if not exists tribunal_sessions (
  id bigserial primary key,
  owner_user_id text not null,
  scope_fingerprint text not null,
  session_id text not null,
  case_file_hash text not null,
  contract_version text not null,
  prompt_version text not null,
  key_source text not null check (key_source in ('user', 'server')),
  payload text not null,
  created_at timestamptz not null,
  completed_at timestamptz not null,
  saved_at timestamptz not null default now(),
  unique (owner_user_id, scope_fingerprint)
);

create table if not exists tribunal_session_members (
  tribunal_session_id bigint not null references tribunal_sessions(id) on delete cascade,
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  primary key (tribunal_session_id, portfolio_id)
);

create index if not exists idx_tribunal_session_members_portfolio
  on tribunal_session_members (portfolio_id);

create table if not exists tribunal_daily_usage (
  owner_user_id text not null,
  usage_day date not null,
  sessions int not null default 0 check (sessions >= 0),
  updated_at timestamptz not null default now(),
  primary key (owner_user_id, usage_day)
);

create or replace function tribunal_session_member_removed() returns trigger
language plpgsql as $$
begin
  delete from tribunal_sessions where id = old.tribunal_session_id;
  return null;
end;
$$;

drop trigger if exists trg_tribunal_session_members_cleanup on tribunal_session_members;
create trigger trg_tribunal_session_members_cleanup
  after delete on tribunal_session_members
  for each row execute function tribunal_session_member_removed();

alter table tribunal_sessions enable row level security;
alter table tribunal_session_members enable row level security;
alter table tribunal_daily_usage enable row level security;
