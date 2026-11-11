-- TASK-80: storico degli esiti della corsa notturna dell'Auditor dei calcoli
-- (docs/auditor/architecture.md §6.1, §7.2).
-- Additiva e idempotente: nessuna tabella esistente viene modificata.
--   auditor_runs    : una riga per corsa (stato, date, versione, trigger, conteggi;
--                     per una corsa 'failed' solo il NOME dell'eccezione).
--   auditor_results : esito peggiore per (corsa, portafoglio, regola, tipo di scope),
--                     da report.privacy_rows: solo id regola, esito, severità e data.
-- Nessun importo, nome di strumento, simbolo, nome di portafoglio, testo di
-- evidenza o messaggio d'errore: la privacy è garantita anche dai vincoli
-- (colonne chiuse, check sui valori ammessi).
-- Lock della corsa: pg_try_advisory_xact_lock(AUDITOR_LOCK_KEY) (services/auditor/store.py);
-- una riga 'running' trovata all'avvio dell'app diventa 'interrupted'.
-- Tabelle solo backend: RLS attiva senza policy, quindi nessun accesso dalle API
-- Supabase (anon/authenticated); il backend usa il ruolo proprietario, che la
-- RLS non limita (come in 20260302_01_enable_rls.sql).
-- Copia identica in src/backend/app/sql/migrations/create_auditor.sql,
-- applicata anche all'avvio del backend.

create table if not exists auditor_runs (
  id bigserial primary key,
  run_uuid text not null unique check (run_uuid ~ '^[0-9a-f]{32}$'),
  status text not null default 'running'
    check (status in ('running', 'success', 'completed_with_failures', 'failed', 'interrupted')),
  trigger text not null check (trigger in ('external', 'manual')),
  app_version text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  users_total integer not null default 0,
  users_failed integer not null default 0,
  portfolios_total integer not null default 0,
  rules_total integer not null default 0,
  pass_count integer not null default 0,
  fail_count integer not null default 0,
  skip_count integer not null default 0,
  error_count integer not null default 0,
  deadline_exceeded boolean not null default false,
  error_type text check (error_type is null or error_type ~ '^[A-Za-z_][A-Za-z0-9_]{0,99}$')
);

create index if not exists idx_auditor_runs_status_started
  on auditor_runs (status, started_at desc);

create table if not exists auditor_results (
  run_id bigint not null references auditor_runs(id) on delete cascade,
  portfolio_id bigint not null references portfolios(id) on delete cascade,
  rule_id text not null check (rule_id ~ '^[ABCD]-[A-Z0-9]+(-[A-Z0-9]+)*$'),
  scope_kind text not null check (scope_kind in ('portfolio', 'aggregate', 'instrument', 'user')),
  status text not null check (status in ('pass', 'fail', 'skip', 'error')),
  severity text not null check (severity in ('P0', 'P1', 'P2')),
  created_at timestamptz not null default now(),
  primary key (run_id, portfolio_id, rule_id, scope_kind)
);

create index if not exists idx_auditor_results_portfolio_run
  on auditor_results (portfolio_id, run_id desc);
create index if not exists idx_auditor_results_run_status
  on auditor_results (run_id, status);

alter table auditor_runs enable row level security;
alter table auditor_results enable row level security;
