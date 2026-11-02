"""Verify Clerk OAuth access tokens presented to the MCP endpoint.

Clerk issues OAuth access tokens in one of two formats, chosen per instance
in the dashboard:

- JWT: header ``typ`` is ``at+jwt`` (RFC 9068), signed RS256 with the
  instance keys. Verified locally against the JWKS: signature, exp/iat/sub,
  ``iss`` == CLERK_ISSUER, ``client_id`` present. The ``typ`` check is what
  rejects Clerk *session* tokens (``typ: JWT``) of the web app, which are
  signed by the same keys.
- Opaque: prefixed ``oat_``. Verified with Clerk's Backend API
  (``POST /oauth_applications/access_tokens/verify`` with the secret key);
  positive results are cached briefly, keyed by the SHA-256 of the token.

This mirrors what Clerk's own SDKs do (@clerk/backend ``verifyOAuthJwt`` /
``IdPOAuthAccessTokenApi.verify``, clerk-backend-api ``verify_token``).

The token is never logged and never forwarded anywhere but to Clerk's
verification endpoint. The resolved ``sub`` (a Clerk user id) is the only
identity used for data access.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from .. import auth as app_auth
from ..errors import AppError
from .config import McpConfig

logger = logging.getLogger("valore365.mcp.auth")

OAUTH_JWT_TYPES = frozenset({"at+jwt", "application/at+jwt"})
OPAQUE_TOKEN_PREFIX = "oat_"
CLERK_USER_ID_PREFIX = "user_"
_CLOCK_SKEW_SECONDS = 5
_MAX_TOKEN_LENGTH = 8192
_CACHE_MAX_ENTRIES = 2048

_cache: dict[str, tuple[float, "McpPrincipal"]] = {}
_cache_lock = threading.Lock()


@dataclass(frozen=True)
class McpPrincipal:
    user_id: str
    client_id: str
    scopes: tuple[str, ...]
    token_format: str  # "jwt" | "opaque"


class McpAuthError(Exception):
    """Authentication/authorization failure, mapped to an RFC 6750 response."""

    def __init__(self, error: str, description: str, status_code: int = 401) -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def clear_token_cache() -> None:
    with _cache_lock:
        _cache.clear()


def _cache_get(key: str) -> McpPrincipal | None:
    now = time.monotonic()
    with _cache_lock:
        entry = _cache.get(key)
        if entry is None:
            return None
        if entry[0] <= now:
            _cache.pop(key, None)
            return None
        return entry[1]


def _cache_put(key: str, principal: McpPrincipal, ttl: float) -> None:
    if ttl <= 0:
        return
    now = time.monotonic()
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX_ENTRIES:
            for stale in [k for k, (exp, _) in _cache.items() if exp <= now]:
                _cache.pop(stale, None)
            while len(_cache) >= _CACHE_MAX_ENTRIES:
                _cache.pop(next(iter(_cache)))
        _cache[key] = (now + ttl, principal)


def _normalize_aud(value: Any) -> list[str] | None:
    if value is None:
        return None
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise McpAuthError("invalid_token", "Invalid audience claim")
    return [v.rstrip("/") for v in values]


def _normalize_scopes(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(s for s in value.split() if s)
    if isinstance(value, list):
        return tuple(s for s in value if isinstance(s, str) and s)
    return ()


def _build_principal(
    *,
    sub: Any,
    client_id: Any,
    scopes: tuple[str, ...],
    aud: Any,
    token_format: str,
    settings,
    config: McpConfig,
) -> McpPrincipal:
    if not isinstance(sub, str) or not sub.startswith(CLERK_USER_ID_PREFIX):
        raise McpAuthError("invalid_token", "Token subject is not a user")
    if not isinstance(client_id, str) or not client_id:
        raise McpAuthError("invalid_token", "Token has no OAuth client")

    allowed_clients = settings.mcp_allowed_client_ids_list
    if allowed_clients and client_id not in allowed_clients:
        logger.warning("MCP token rejected: client not allowed (client_id=%s)", client_id)
        raise McpAuthError("invalid_token", "OAuth client not allowed")

    audiences = _normalize_aud(aud)
    if audiences is None:
        if settings.mcp_require_audience:
            raise McpAuthError("invalid_token", "Token has no audience")
    elif config.resource_url not in audiences:
        raise McpAuthError("invalid_token", "Token audience does not match this resource")

    missing = [s for s in settings.mcp_required_scopes_list if s not in scopes]
    if missing:
        raise McpAuthError("insufficient_scope", f"Missing scope: {' '.join(missing)}", status_code=403)

    return McpPrincipal(user_id=sub, client_id=client_id, scopes=scopes, token_format=token_format)


def _verify_jwt(token: str, settings, config: McpConfig) -> McpPrincipal:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise McpAuthError("invalid_token", "Malformed token") from exc

    typ = str(header.get("typ") or "").lower()
    if typ not in OAUTH_JWT_TYPES:
        # Clerk session tokens of the web app (typ "JWT") land here.
        raise McpAuthError("invalid_token", "Not an OAuth access token")
    if header.get("alg") != "RS256":
        raise McpAuthError("invalid_token", "Unsupported token algorithm")

    try:
        signing_key = app_auth._get_signing_key(token, config.jwks_url)
    except (AppError, jwt.PyJWTError) as exc:
        raise McpAuthError("invalid_token", "Unknown signing key") from exc
    except (httpx.HTTPError, ValueError) as exc:
        logger.error("MCP auth: JWKS unavailable (%s)", type(exc).__name__)
        raise McpAuthError("temporarily_unavailable", "Unable to verify token", status_code=503) from exc

    try:
        claims = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            issuer=config.issuer,
            leeway=_CLOCK_SKEW_SECONDS,
            options={"require": ["exp", "iat", "sub", "iss"], "verify_aud": False},
        )
    except jwt.ExpiredSignatureError as exc:
        raise McpAuthError("invalid_token", "Token expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise McpAuthError("invalid_token", "Invalid token issuer") from exc
    except jwt.InvalidTokenError as exc:
        raise McpAuthError("invalid_token", "Invalid token") from exc

    scopes = _normalize_scopes(claims.get("scp")) or _normalize_scopes(claims.get("scope"))
    return _build_principal(
        sub=claims.get("sub"),
        client_id=claims.get("client_id"),
        scopes=scopes,
        aud=claims.get("aud"),
        token_format="jwt",
        settings=settings,
        config=config,
    )


def _verify_opaque(token: str, settings, config: McpConfig) -> McpPrincipal:
    secret_key = (settings.clerk_secret_key or "").strip()
    if not secret_key:
        logger.error("MCP auth: opaque OAuth token received but CLERK_SECRET_KEY is not set")
        raise McpAuthError("invalid_token", "Opaque tokens are not accepted by this server")

    cache_key = token_fingerprint(token)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    url = f"{settings.clerk_api_url.rstrip('/')}/oauth_applications/access_tokens/verify"
    try:
        response = httpx.post(
            url,
            json={"access_token": token},
            headers={"Authorization": f"Bearer {secret_key}"},
            timeout=10,
        )
    except httpx.HTTPError as exc:
        logger.error("MCP auth: Clerk token verification unreachable (%s)", type(exc).__name__)
        raise McpAuthError("temporarily_unavailable", "Unable to verify token", status_code=503) from exc

    if response.status_code >= 500:
        logger.error("MCP auth: Clerk token verification failed with HTTP %s", response.status_code)
        raise McpAuthError("temporarily_unavailable", "Unable to verify token", status_code=503)
    if response.status_code != 200:
        raise McpAuthError("invalid_token", "Invalid token")

    try:
        data = response.json()
    except ValueError as exc:
        raise McpAuthError("invalid_token", "Invalid token") from exc
    if not isinstance(data, dict) or data.get("active") is False:
        raise McpAuthError("invalid_token", "Invalid token")
    if data.get("revoked") is not False or data.get("expired") is not False:
        raise McpAuthError("invalid_token", "Token revoked or expired")

    now_ms = time.time() * 1000
    expiration = data.get("expiration")
    if expiration is not None:
        try:
            expiration_ms = float(expiration)
        except (TypeError, ValueError) as exc:
            raise McpAuthError("invalid_token", "Invalid token") from exc
        if expiration_ms <= now_ms:
            raise McpAuthError("invalid_token", "Token expired")
        remaining = (expiration_ms - now_ms) / 1000
    else:
        remaining = float("inf")

    principal = _build_principal(
        sub=data.get("subject"),
        client_id=data.get("client_id"),
        scopes=_normalize_scopes(data.get("scopes")),
        aud=data.get("aud"),
        token_format="opaque",
        settings=settings,
        config=config,
    )
    _cache_put(cache_key, principal, min(float(settings.mcp_token_cache_seconds), remaining))
    return principal


def verify_access_token(token: str, settings, config: McpConfig) -> McpPrincipal:
    """Verify a Clerk OAuth access token. Blocking: may call Clerk over HTTP."""
    if not token or len(token) > _MAX_TOKEN_LENGTH:
        raise McpAuthError("invalid_token", "Invalid token")
    if token.startswith(OPAQUE_TOKEN_PREFIX):
        return _verify_opaque(token, settings, config)
    if token.count(".") == 2:
        return _verify_jwt(token, settings, config)
    raise McpAuthError("invalid_token", "Unsupported token type")
