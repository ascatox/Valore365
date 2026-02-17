from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_env: str = 'dev'
    database_url: str = 'postgresql+psycopg://postgres:postgres@localhost:5432/valore365'

    finance_provider: str = 'twelvedata'
    finance_api_base_url: str = 'https://api.twelvedata.com'
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

    @property
    def clerk_authorized_parties_list(self) -> list[str]:
        return [value.strip() for value in self.clerk_authorized_parties.split(",") if value.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
