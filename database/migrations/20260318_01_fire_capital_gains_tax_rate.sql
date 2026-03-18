ALTER TABLE app_user_settings
  ADD COLUMN IF NOT EXISTS fire_capital_gains_tax_rate numeric(10,4) NOT NULL DEFAULT 26;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_capital_gains_tax_rate_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_capital_gains_tax_rate_check
      CHECK (fire_capital_gains_tax_rate >= 0 AND fire_capital_gains_tax_rate <= 100);
  END IF;
END $$;
