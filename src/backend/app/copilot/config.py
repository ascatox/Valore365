"""Copilot configuration: resolve provider, encrypt/decrypt keys, defaults."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ..config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default models per provider
# ---------------------------------------------------------------------------

_DEFAULT_MODELS: dict[str, str] = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-20250514",
    "gemini": "gemini-2.0-flash",
    "openrouter": "mistralai/mistral-large-2512",
    "local": "llama3.2:3b",
}


# ---------------------------------------------------------------------------
# Config dataclass
# ---------------------------------------------------------------------------

@dataclass
class CopilotConfig:
    """Resolved copilot configuration (user-level or server-level)."""
    provider: str
    model: str
    api_key: str
    local_url: str = ""


# ---------------------------------------------------------------------------
# Encryption helpers
# ---------------------------------------------------------------------------

def _decrypt_api_key(encrypted: str, settings: Settings) -> str:
    """Decrypt a Fernet-encrypted API key. Returns empty string on failure."""
    if not encrypted or not settings.copilot_encryption_key:
        return ""
    try:
        from cryptography.fernet import Fernet
        f = Fernet(settings.copilot_encryption_key.encode())
        return f.decrypt(encrypted.encode()).decode()
    except Exception:
        logger.warning("Failed to decrypt user API key")
        return ""


def encrypt_api_key(plaintext: str, settings: Settings) -> str:
    """Encrypt an API key with Fernet. Returns empty string if no encryption key."""
    if not plaintext or not settings.copilot_encryption_key:
        return ""
    from cryptography.fernet import Fernet
    f = Fernet(settings.copilot_encryption_key.encode())
    return f.encrypt(plaintext.encode()).decode()


# ---------------------------------------------------------------------------
# Config resolution
# ---------------------------------------------------------------------------

def resolve_copilot_config(
    settings: Settings,
    user_provider: str = "",
    user_model: str = "",
    user_api_key_enc: str = "",
) -> CopilotConfig | None:
    """Resolve copilot config: user key first, then server fallback.

    Returns None if no valid configuration is available.
    """
    # 1. Try user-level config
    if user_provider and user_api_key_enc:
        decrypted = _decrypt_api_key(user_api_key_enc, settings)
        if decrypted:
            model = user_model or _DEFAULT_MODELS.get(user_provider, "gpt-4o-mini")
            return CopilotConfig(
                provider=user_provider,
                model=model,
                api_key=decrypted,
                local_url=settings.copilot_local_url if user_provider == "local" else "",
            )

    # 2. Fallback to server-level config
    provider = settings.copilot_provider
    if not provider:
        return None
    api_key = _get_server_api_key(settings)
    if not api_key:
        return None
    model = settings.copilot_model or _DEFAULT_MODELS.get(provider, "gpt-4o-mini")
    return CopilotConfig(
        provider=provider,
        model=model,
        api_key=api_key,
        local_url=settings.copilot_local_url if provider == "local" else "",
    )


def _get_server_api_key(settings: Settings) -> str:
    """Return the server-level API key for the configured provider."""
    provider = settings.copilot_provider
    if provider == "openai":
        return settings.openai_api_key
    elif provider == "anthropic":
        return settings.anthropic_api_key
    elif provider == "gemini":
        return settings.gemini_api_key
    elif provider == "openrouter":
        return settings.openrouter_api_key
    elif provider == "local":
        return settings.copilot_local_api_key or "not-needed"
    return ""


def _get_model(settings: Settings) -> str:
    """Return the model name, falling back to provider default (for status endpoint)."""
    if settings.copilot_model:
        return settings.copilot_model
    return _DEFAULT_MODELS.get(settings.copilot_provider, "gpt-4o-mini")


def is_copilot_available(settings: Settings, user_provider: str = "", user_api_key_enc: str = "") -> bool:
    """Check if the copilot is available (user key or server key)."""
    return resolve_copilot_config(settings, user_provider=user_provider, user_api_key_enc=user_api_key_enc) is not None
