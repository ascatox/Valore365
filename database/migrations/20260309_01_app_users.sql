create table if not exists app_users (
    user_id varchar(255) primary key,
      email varchar(320),
        last_sign_in_at timestamptz,
          last_seen_at timestamptz not null default now(),
            created_at timestamptz not null default now(),
              updated_at timestamptz not null default now()
              );

              create index if not exists idx_app_users_email on app_users(email);
              create index if not exists idx_app_users_last_seen_at on app_users(last_seen_at desc);
              
)