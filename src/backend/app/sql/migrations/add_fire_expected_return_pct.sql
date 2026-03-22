ALTER TABLE app_user_settings
  ADD COLUMN IF NOT EXISTS fire_expected_return_pct numeric(10,4) NOT NULL DEFAULT 5;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_expected_return_pct_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_expected_return_pct_check
      CHECK (fire_expected_return_pct > 0 AND fire_expected_return_pct <= 20);
  END IF;
END $$;
