ALTER TABLE app_user_settings
  ADD COLUMN IF NOT EXISTS fire_capital_floor numeric(28,10) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fire_contribution_growth_pct numeric(10,4) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fire_pension_annual numeric(28,10) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fire_pension_start_age int,
  ADD COLUMN IF NOT EXISTS fire_one_off_expenses jsonb NOT NULL DEFAULT '[]'::jsonb;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_capital_floor_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_capital_floor_check
      CHECK (fire_capital_floor >= 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_contribution_growth_pct_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_contribution_growth_pct_check
      CHECK (fire_contribution_growth_pct >= 0 AND fire_contribution_growth_pct <= 20);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_pension_annual_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_pension_annual_check
      CHECK (fire_pension_annual >= 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_pension_start_age_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_pension_start_age_check
      CHECK (fire_pension_start_age IS NULL OR (fire_pension_start_age >= 18 AND fire_pension_start_age <= 100));
  END IF;
END $$;
