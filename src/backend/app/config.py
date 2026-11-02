from functools import lru_cache
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_env: str = 'dev'
    database_url: str = 'postgresql+psycopg://postgres:postgres@localhost:5432/valore365'

    # Connection pool. The app runs as a single uvicorn process (see render.yaml),
    # so pool_size + max_overflow is the whole application's connection budget and
    # must stay within the limit of the Postgres pooler in front of it.
    db_pool_size: int = 10
    db_max_overflow: int = 20
    db_pool_timeout: int = 30
    # Recycle before the pooler reaps idle server-side connections, so a stale
    # connection is replaced on a schedule rather than discovered by pool_pre_ping.
    db_pool_recycle: int = 1800
    # Caps the threads that can contend for a connection. Route handlers are sync
    # 'def', so they run in Starlette's threadpool (40 by default): without a cap,
    # threads beyond the pool size just queue on db_pool_timeout and then fail.
    request_threadpool_size: int = 24

    # The performance screen is backed by eight endpoints that all resolve the
    # same window, so their lookups are shared per (user, portfolio) for this
    # long. Prices refresh on price_scheduler_interval_seconds, so keep this
    # well under it. Set to 0 to recompute on every request.
    performance_cache_ttl_seconds: float = 30.0

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
    # Quotazioni scaricate in parallelo da un refresh prezzi (sequenziale se
    # finance_symbol_request_delay_seconds > 0).
    finance_quote_concurrency: int = 4
    justetf_enabled: bool = True
    justetf_blocked_cooldown_seconds: float = 900.0
    fmt_api_key: str = ""
    fmt_api_base_url: str = "https://financialmodelingprep.com/stable"
    fmt_timeout_seconds: float = 10.0

    price_scheduler_enabled: bool = False
    price_scheduler_interval_seconds: int = 60
    price_scheduler_portfolio_id: int | None = None
    # Lo scheduler salta gli asset la cui borsa è chiusa (orari dal suffisso del
    # simbolo Yahoo, vedi services/market_hours.py); i refresh manuali no.
    price_scheduler_market_hours_only: bool = True
    # Minuti dopo la chiusura in cui l'asset si aggiorna ancora (prezzo d'asta).
    price_scheduler_after_close_grace_minutes: int = 30

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
    # provider: "openai" | "anthropic" | "gemini" | "openrouter" | "local"
    copilot_provider: str = ""
    copilot_model: str = ""  # empty = auto-default per provider
    openai_api_key: str = ""
    anthropic_api_key: str = ""
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    # Local LLM (Ollama, LM Studio, llama.cpp, vLLM) — OpenAI-compatible API
    copilot_local_url: str = "http://localhost:11434/v1"
    copilot_local_api_key: str = "not-needed"
    # Fernet key for encrypting user API keys (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
    copilot_encryption_key: str = ""

    # Price validation thresholds
    price_validation_min_price: float = 0.0001
    price_validation_max_daily_change_pct: float = 50.0
    price_validation_max_ohlc_spread_pct: float = 100.0
    price_validation_ohlc_range_tolerance_pct: float = 2.0
    price_validation_stale_days: int = 5
    price_validation_fx_min_rate: float = 0.0001
    price_validation_fx_max_rate: float = 10000.0
    # Concurrent provider requests during a daily backfill
    price_backfill_max_workers: int = 4

    cors_allowed_origins: str = "http://localhost:5173"
    cors_allowed_origin_regex: str = ""
    public_instant_analyzer_rate_limit_requests: int = 10
    public_instant_analyzer_rate_limit_window_seconds: int = 60
    public_instant_analyzer_max_positions: int = 500
    public_instant_analyzer_max_raw_text_chars: int = 50000
    public_instant_analyzer_max_line_length: int = 128
    csv_import_max_upload_bytes: int = 5 * 1024 * 1024
    justetf_xray_auto_enrich_enabled: bool | None = None

    # Per-user rate limiting for authenticated endpoints
    authenticated_rate_limit_requests: int = 120
    authenticated_rate_limit_window_seconds: int = 60

    # --- Remote MCP server (read-only, see docs/mcp.md) ---
    # Served at /mcp only when mcp_enabled is True AND Clerk auth is enabled
    # AND clerk_issuer / mcp_resource_url are set: otherwise it fails closed.
    mcp_enabled: bool = False
    # Public URL of the /mcp endpoint (e.g. https://api.example.com/mcp): the
    # OAuth resource identifier, checked against the token audience.
    mcp_resource_url: str = ""
    # Clerk Frontend API URL (e.g. https://clerk.example.com): the OAuth
    # authorization server and the expected `iss` of JWT access tokens.
    clerk_issuer: str = ""
    # Clerk secret key (sk_...): only needed to verify opaque OAuth access
    # tokens (oat_...) with Clerk's Backend API. JWT access tokens are
    # verified locally against the JWKS.
    clerk_secret_key: str = ""
    clerk_api_url: str = "https://api.clerk.com/v1"
    # Comma-separated OAuth client ids allowed to call the MCP server
    # (empty = any client registered on the Clerk instance, e.g. via DCR).
    mcp_allowed_client_ids: str = ""
    # Scopes advertised in the protected resource metadata, and the ones a
    # token must carry (empty = no scope required).
    mcp_scopes_supported: str = "profile email"
    mcp_required_scopes: str = ""
    # When True, tokens without an `aud` claim are rejected. A token that has
    # `aud` must always include mcp_resource_url.
    mcp_require_audience: bool = False
    # Browser origins allowed to call /mcp (DNS-rebinding protection). Server
    # to server clients (Claude, ChatGPT) send no Origin and need nothing here.
    mcp_allowed_origins: str = ""
    mcp_rate_limit_requests: int = 60
    mcp_rate_limit_window_seconds: int = 60
    # How long a positively verified opaque token is cached (keyed by SHA-256).
    mcp_token_cache_seconds: int = 60
    # Hardening (see docs/mcp.md, "Hardening"). All limits are in-memory, per
    # process: with N instances the effective limits are N times larger.
    # Failed authentications per client IP before /mcp answers 429 without
    # contacting Clerk.
    mcp_auth_failure_limit: int = 20
    mcp_auth_failure_window_seconds: int = 300
    # How long an opaque token rejected by Clerk is remembered (SHA-256 key).
    mcp_negative_token_cache_seconds: int = 60
    # Max accepted JWT lifetime (exp - iat); 0 disables the check.
    mcp_max_token_lifetime_seconds: int = 86400
    # Per-call limits for MCP tools.
    mcp_tool_timeout_seconds: float = 20.0
    mcp_max_concurrent_calls_per_user: int = 4
    mcp_heavy_tool_rate_limit_requests: int = 10
    mcp_heavy_tool_rate_limit_window_seconds: int = 60
    # Gradual rollout / kill switch: Clerk user ids (user_...), comma separated.
    # Allowed empty = every user; blocked users always get 403.
    mcp_allowed_user_ids: str = ""
    mcp_blocked_user_ids: str = ""

    @property
    def clerk_authorized_parties_list(self) -> list[str]:
        return [value.strip() for value in self.clerk_authorized_parties.split(",") if value.strip()]

    @property
    def mcp_allowed_client_ids_list(self) -> list[str]:
        return [v.strip() for v in self.mcp_allowed_client_ids.split(",") if v.strip()]

    @property
    def mcp_scopes_supported_list(self) -> list[str]:
        return [v for v in self.mcp_scopes_supported.replace(",", " ").split() if v]

    @property
    def mcp_required_scopes_list(self) -> list[str]:
        return [v for v in self.mcp_required_scopes.replace(",", " ").split() if v]

    @property
    def mcp_allowed_user_ids_set(self) -> frozenset[str]:
        return frozenset(v.strip() for v in self.mcp_allowed_user_ids.split(",") if v.strip())

    @property
    def mcp_blocked_user_ids_set(self) -> frozenset[str]:
        return frozenset(v.strip() for v in self.mcp_blocked_user_ids.split(",") if v.strip())

    @property
    def mcp_allowed_origins_list(self) -> list[str]:
        return [v.strip() for v in self.mcp_allowed_origins.split(",") if v.strip()]

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

    @property
    def justetf_xray_auto_enrich_enabled_resolved(self) -> bool:
        if self.justetf_xray_auto_enrich_enabled is not None:
            return self.justetf_xray_auto_enrich_enabled
        return self.app_env.strip().lower() == "dev"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
