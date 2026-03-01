-- Feature 4: Piani di Accumulo (PAC)
CREATE TABLE IF NOT EXISTS pac_rules (
  id bigserial PRIMARY KEY,
  portfolio_id bigint NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
  asset_id bigint NOT NULL REFERENCES assets(id),
  mode text NOT NULL CHECK (mode IN ('amount','quantity')) DEFAULT 'amount',
  amount numeric(28,10),
  quantity numeric(28,10),
  frequency text NOT NULL CHECK (frequency IN ('weekly','biweekly','monthly')),
  day_of_month int CHECK (day_of_month >= 1 AND day_of_month <= 28),
  day_of_week int CHECK (day_of_week >= 0 AND day_of_week <= 6),
  start_date date NOT NULL,
  end_date date,
  auto_execute boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  owner_user_id varchar(255) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
