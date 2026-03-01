-- Feature 4: Piani di Accumulo (PAC) - executions tracking
CREATE TABLE IF NOT EXISTS pac_executions (
  id bigserial PRIMARY KEY,
  pac_rule_id bigint NOT NULL REFERENCES pac_rules(id) ON DELETE CASCADE,
  scheduled_date date NOT NULL,
  status text NOT NULL CHECK (status IN ('pending','executed','skipped','failed')) DEFAULT 'pending',
  transaction_id bigint REFERENCES transactions(id) ON DELETE SET NULL,
  executed_price numeric(28,10),
  executed_quantity numeric(28,10),
  error_message text,
  created_at timestamptz NOT NULL DEFAULT now(),
  executed_at timestamptz,
  UNIQUE (pac_rule_id, scheduled_date)
);
