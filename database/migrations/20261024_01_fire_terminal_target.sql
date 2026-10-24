ALTER TABLE app_user_settings
  ADD COLUMN IF NOT EXISTS fire_terminal_target_min numeric(28,10) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS fire_terminal_target_max numeric(28,10) NOT NULL DEFAULT 0;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_terminal_target_min_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_terminal_target_min_check
      CHECK (fire_terminal_target_min >= 0);
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'app_user_settings_fire_terminal_target_max_check'
  ) THEN
    ALTER TABLE app_user_settings
      ADD CONSTRAINT app_user_settings_fire_terminal_target_max_check
      CHECK (fire_terminal_target_max >= 0);
  END IF;
END $$;
