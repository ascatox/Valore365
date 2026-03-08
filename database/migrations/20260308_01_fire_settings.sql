ALTER TABLE app_user_settings
  ADD COLUMN IF NOT EXISTS fire_annual_expenses numeric(28,10) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fire_annual_contribution numeric(28,10) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fire_safe_withdrawal_rate numeric(10,4) NOT NULL DEFAULT 4,
  ADD COLUMN IF NOT EXISTS fire_current_age int,
  ADD COLUMN IF NOT EXISTS fire_target_age int;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_safe_withdrawal_rate_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_safe_withdrawal_rate_check
      CHECK (fire_safe_withdrawal_rate > 0 AND fire_safe_withdrawal_rate <= 20);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_current_age_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_current_age_check
      CHECK (fire_current_age IS NULL OR (fire_current_age >= 18 AND fire_current_age <= 100));
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_target_age_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_target_age_check
      CHECK (fire_target_age IS NULL OR (fire_target_age >= 18 AND fire_target_age <= 100));
  END IF;
END $$;
