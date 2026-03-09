from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_env: str = 'dev'
    database_url: str = 'postgresql+psycopg://postgres:postgres@localhost:5432/valore365'

    @property
    def database_url_resolved(self) -> str:
        """Normalize DATABASE_URL to always use the psycopg3 driver."""
        url = self.database_url
        if url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        elif url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        return url

    finance_provider: str = 'yfinance'
    finance_api_base_url: str = ''
    finance_api_key: str = ''
    finance_request_timeout_seconds: float = 10.0
    finance_max_retries: int = 3
    finance_retry_backoff_seconds: float = 0.5
    finance_symbol_request_delay_seconds: float = 0.0

    price_scheduler_enabled: bool = False
    price_scheduler_interval_seconds: int = 60
    price_scheduler_portfolio_id: int | None = None

    clerk_auth_enabled: bool = False
    clerk_jwks_url: str = ""
    clerk_authorized_parties: str = ""
    admin_emails: str = ""
    admin_user_ids: str = ""
    trusted_proxy_ips: str = ""

    pac_scheduler_enabled: bool = False
    pac_execution_hour: int = 8

    # Feature flag: disable all target-allocation-only APIs/flows when False.
    # Keep default=True for backward compatibility; disable explicitly via env.
    enable_target_allocation: bool = True

    # Copilot (AI assistant) — multi-provider
    # provider: "openai" | "anthropic" | "gemini" | "local"
    copilot_provider: str = ""
    copilot_model: str = ""  # empty = auto-default per provider
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    # Local LLM (Ollama, LM Studio, llama.cpp, vLLM) — OpenAI-compatible API
    copilot_local_url: str = "http://localhost:11434/v1"
    copilot_local_api_key: str = "not-needed"
    # Fernet key for encrypting user API keys (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    copilot_encryption_key: str = ""

    # Price validation thresholds
    price_validation_min_price: float = 0.0001
    price_validation_max_daily_change_pct: float = 50.0
    price_validation_max_ohlc_spread_pct: float = 100.0
    price_validation_stale_days: int = 5
    price_validation_fx_min_rate: float = 0.0001
    price_validation_fx_max_rate: float = 10000.0

    cors_allowed_origins: str = "http://localhost:5173"
    public_instant_analyzer_rate_limit_requests: int = 10
    public_instant_analyzer_rate_limit_window_seconds: int = 60
    public_instant_analyzer_max_positions: int = 50
    public_instant_analyzer_max_raw_text_chars: int = 5000
    public_instant_analyzer_max_line_length: int = 128
    csv_import_max_upload_bytes: int = 5 * 1024 * 1024

    @property
    def clerk_authorized_parties_list(self) -> list[str]:
        return [value.strip() for value in self.clerk_authorized_parties.split(",") if value.strip()]

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [v.strip() for v in self.cors_allowed_origins.split(",") if v.strip()]

    @property
    def trusted_proxy_ips_list(self) -> list[str]:
        return [v.strip() for v in self.trusted_proxy_ips.split(",") if v.strip()]

    @property
    def admin_emails_list(self) -> list[str]:
        return [v.strip().lower() for v in self.admin_emails.split(",") if v.strip()]

    @property
    def admin_user_ids_list(self) -> list[str]:
        return [v.strip() for v in self.admin_user_ids.split(",") if v.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
