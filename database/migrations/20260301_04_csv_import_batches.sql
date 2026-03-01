-- Feature 3: Importazione Massiva CSV
CREATE TABLE IF NOT EXISTS csv_import_batches (
  id bigserial PRIMARY KEY,
  portfolio_id bigint NOT NULL REFERENCES portfolios(id) ON DELETE CASCADE,
  owner_user_id varchar(255) NOT NULL,
  status text NOT NULL CHECK (status IN ('pending','committed','cancelled')) DEFAULT 'pending',
  original_filename text,
  total_rows int NOT NULL DEFAULT 0,
  valid_rows int NOT NULL DEFAULT 0,
  error_rows int NOT NULL DEFAULT 0,
  preview_data jsonb NOT NULL DEFAULT '[]',
  created_at timestamptz NOT NULL DEFAULT now(),
  committed_at timestamptz
);
