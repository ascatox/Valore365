create table if not exists public_instant_analyzer_events (
  id bigserial primary key,
  client_ip_hash varchar(64),
  input_mode varchar(32) not null,
  positions_count int not null default 0,
  success boolean not null default false,
  created_at timestamptz not null default now()
);

create index if not exists idx_public_instant_analyzer_events_created_at
  on public_instant_analyzer_events(created_at desc);

create index if not exists idx_public_instant_analyzer_events_client_ip_hash
  on public_instant_analyzer_events(client_ip_hash);
