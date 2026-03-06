-- Add per-user Copilot settings (BYOK - Bring Your Own Key)
ALTER TABLE app_user_settings
  ADD COLUMN IF NOT EXISTS copilot_provider varchar(32) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS copilot_model varchar(128) NOT NULL DEFAULT '',
  ADD COLUMN IF NOT EXISTS copilot_api_key_enc text NOT NULL DEFAULT '';

COMMENT ON COLUMN app_user_settings.copilot_provider IS 'User-chosen LLM provider: openai | anthropic | gemini | (empty = use server default)';
COMMENT ON COLUMN app_user_settings.copilot_model IS 'User-chosen model override (empty = provider default)';
COMMENT ON COLUMN app_user_settings.copilot_api_key_enc IS 'Fernet-encrypted API key for the chosen provider';
