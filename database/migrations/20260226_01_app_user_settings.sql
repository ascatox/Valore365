create table if not exists app_user_settings (
  user_id varchar(255) primary key,
  broker_default_fee numeric(28,10) not null default 0,
  updated_at timestamptz not null default now()
);
