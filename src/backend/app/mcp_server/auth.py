"""Verify Clerk OAuth access tokens presented to the MCP endpoint.

Clerk issues OAuth access tokens in one of two formats, chosen per instance
in the dashboard:

- JWT: header ``typ`` is ``at+jwt`` (RFC 9068), signed RS256 with the
  instance keys. Verified locally against the JWKS: signature (``alg``
  pinned to RS256, no ``crit``), exp/iat/sub/iss required, nbf when present,
  iat not in the future, lifetime (exp - iat) capped, ``iss`` ==
  CLERK_ISSUER, ``client_id`` present. The ``typ`` check is what rejects
  Clerk *session* tokens (``typ: JWT``) of the web app, which are signed by
  the same keys. An unknown ``kid`` refetches the JWKS at most once every
  _JWKS_REFETCH_MIN_INTERVAL seconds.
- Opaque: prefixed ``oat_``. Only well-formed tokens are sent to Clerk's
  Backend API (``POST /oauth_applications/access_tokens/verify`` with the
  secret key). Accepted and rejected results are both cached briefly, keyed
  by the SHA-256 of the token.

This mirrors what Clerk's own SDKs do (@clerk/backend ``verifyOAuthJwt`` /
``IdPOAuthAccessTokenApi.verify``, clerk-backend-api ``verify_token``).

The token is never logged and never forwarded anywhere but to Clerk's
verification endpoint. The resolved ``sub`` (a Clerk user id) is the only
identity used for data access.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt

from .. import auth as app_auth
from .config import McpConfig

logger = logging.getLogger("valore365.mcp.auth")

OAUTH_JWT_TYPES = frozenset({"at+jwt", "application/at+jwt"})
OPAQUE_TOKEN_PREFIX = "oat_"
CLERK_USER_ID_PREFIX = "user_"
_CLOCK_SKEW_SECONDS = 5
# Longer Authorization headers/tokens are rejected without being parsed.
MAX_TOKEN_LENGTH = 4096
_CACHE_MAX_ENTRIES = 2048
_JWKS_REFETCH_MIN_INTERVAL = 30.0
_OPAQUE_TOKEN_RE = re.compile(r"oat_[A-Za-z0-9_-]{8,256}")
_JWT_RE = re.compile(r"[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+")


@dataclass(frozen=True)
class McpPrincipal:
    user_id: str
    client_id: str
    scopes: tuple[str, ...]
    token_format: str  # "jwt" | "opaque"


class McpAuthError(Exception):
    """Authentication/authorization failure, mapped to an RFC 6750 response.

    ``description`` and ``reason`` (a short category) are for the logs only:
    the HTTP response carries a generic message.
    """

    def __init__(self, error: str, description: str, status_code: int = 401, *, reason: str = "invalid") -> None:
        super().__init__(description)
        self.error = error
        self.description = description
        self.status_code = status_code
        self.reason = reason


def token_fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class _ExpiringCache:
    """Small bounded TTL map, keyed by token fingerprint."""

    def __init__(self, max_entries: int = _CACHE_MAX_ENTRIES) -> None:
        self._max_entries = max_entries
        self._entries: dict[str, tuple[float, Any]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Any:
        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                return None
            if entry[0] <= now:
                self._entries.pop(key, None)
                return None
            return entry[1]

    def put(self, key: str, value: Any, ttl: float) -> None:
        if ttl <= 0:
            return
        now = time.monotonic()
        with self._lock:
            if len(self._entries) >= self._max_entries:
                for stale in [k for k, (exp, _) in self._entries.items() if exp <= now]:
                    self._entries.pop(stale, None)
                while len(self._entries) >= self._max_entries:
                    self._entries.pop(next(iter(self._entries)))
            self._entries[key] = (now + ttl, value)

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


_accepted = _ExpiringCache()
_rejected = _ExpiringCache()
_jwks_lock = threading.Lock()
_jwks_last_fetch = float("-inf")


def reset_state() -> None:
    """Forget cached verifications and the JWKS refetch throttle (tests)."""
    global _jwks_last_fetch
    _accepted.clear()
    _rejected.clear()
    with _jwks_lock:
        _jwks_last_fetch = float("-inf")


def _normalize_aud(value: Any) -> list[str] | None:
    if value is None:
        return None
    values = [value] if isinstance(value, str) else value
    if not isinstance(values, list) or not all(isinstance(v, str) and v for v in values):
        raise McpAuthError("invalid_token", "Invalid audience claim", reason="audience")
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
        raise McpAuthError("invalid_token", "Token subject is not a user", reason="subject")
    if not isinstance(client_id, str) or not client_id:
        raise McpAuthError("invalid_token", "Token has no OAuth client", reason="client")

    allowed_clients = settings.mcp_allowed_client_ids_list
    if allowed_clients and client_id not in allowed_clients:
        logger.warning("MCP token rejected: client not allowed (client_id=%s)", client_id[:100])
        raise McpAuthError("invalid_token", "OAuth client not allowed", reason="client_not_allowed")

    audiences = _normalize_aud(aud)
    if audiences is None:
        if settings.mcp_require_audience:
            raise McpAuthError("invalid_token", "Token has no audience", reason="audience")
    elif config.resource_url not in audiences:
        raise McpAuthError("invalid_token", "Token audience does not match this resource", reason="audience")

    missing = [s for s in settings.mcp_required_scopes_list if s not in scopes]
    if missing:
        raise McpAuthError(
            "insufficient_scope", f"Missing scope: {' '.join(missing)}", status_code=403, reason="scope"
        )

    return McpPrincipal(user_id=sub, client_id=client_id, scopes=scopes, token_format=token_format)


def _find_key(keys: Any, kid: str) -> jwt.PyJWK | None:
    # Keys are parsed one by one: a malformed entry must not hide the others.
    for entry in keys if isinstance(keys, list) else []:
        if isinstance(entry, dict) and entry.get("kid") == kid:
            try:
                return jwt.PyJWK(entry)
            except (jwt.PyJWTError, ValueError, TypeError, KeyError):
                return None
    return None


def _signing_key(kid: str, jwks_url: str) -> jwt.PyJWK:
    """Key for ``kid`` from the JWKS shared with app.auth.

    An unknown kid refetches the JWKS at most once every
    _JWKS_REFETCH_MIN_INTERVAL seconds, so random kids cannot turn every
    request into a call to Clerk.
    """
    global _jwks_last_fetch
    cache = app_auth._JWKS_CACHE
    if time.monotonic() < cache["expires_at"]:
        key = _find_key(cache["keys"], kid)
        if key is not None:
            return key

    with _jwks_lock:
        now = time.monotonic()
        fresh = now < cache["expires_at"]
        if fresh:
            # Another request may have refreshed the keys while we waited.
            key = _find_key(cache["keys"], kid)
            if key is not None:
                return key
        if now - _jwks_last_fetch < _JWKS_REFETCH_MIN_INTERVAL:
            if fresh:
                raise McpAuthError("invalid_token", "Unknown signing key", reason="unknown_kid")
            raise McpAuthError(
                "temporarily_unavailable", "Unable to verify token", status_code=503, reason="jwks_unavailable"
            )
        _jwks_last_fetch = now
        keys = app_auth._fetch_jwks(jwks_url)
        cache["keys"] = keys
        cache["expires_at"] = now + app_auth._JWKS_CACHE_TTL

    key = _find_key(keys, kid)
    if key is None:
        raise McpAuthError("invalid_token", "Unknown signing key", reason="unknown_kid")
    return key


def _verify_jwt(token: str, settings, config: McpConfig) -> McpPrincipal:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.InvalidTokenError as exc:
        raise McpAuthError("invalid_token", "Malformed token", reason="malformed") from exc

    typ = str(header.get("typ") or "").lower()
    if typ not in OAUTH_JWT_TYPES:
        # Clerk session tokens of the web app (typ "JWT") land here.
        raise McpAuthError("invalid_token", "Not an OAuth access token", reason="not_access_token")
    # Pinned: rejects "none", HS* (key confusion) and anything else.
    if header.get("alg") != "RS256":
        raise McpAuthError("invalid_token", "Unsupported token algorithm", reason="algorithm")
    # RFC 7515: unknown critical extensions must be rejected (PyJWT < 2.12
    # ignores "crit"); Clerk never sets it.
    if "crit" in header:
        raise McpAuthError("invalid_token", "Unsupported critical header", reason="malformed")
    kid = header.get("kid")
    if not isinstance(kid, str) or not kid or len(kid) > 256:
        raise McpAuthError("invalid_token", "Unknown signing key", reason="unknown_kid")

    try:
        signing_key = _signing_key(kid, config.jwks_url)
    except McpAuthError:
        raise
    except Exception as exc:  # network error, bad JSON from the JWKS endpoint
        logger.error("MCP auth: JWKS unavailable (%s)", type(exc).__name__)
        raise McpAuthError(
            "temporarily_unavailable", "Unable to verify token", status_code=503, reason="jwks_unavailable"
        ) from exc
    if signing_key.key_type != "RSA":
        raise McpAuthError("invalid_token", "Unknown signing key", reason="unknown_kid")

    try:
        claims = jwt.decode(
            token,
            key=signing_key.key,
            algorithms=["RS256"],
            issuer=config.issuer,
            leeway=_CLOCK_SKEW_SECONDS,
            options={
                "require": ["exp", "iat", "sub", "iss"],
                "verify_signature": True,
                "verify_exp": True,
                "verify_nbf": True,  # when present
                "verify_iat": True,  # rejects iat in the future (beyond leeway)
                "verify_iss": True,
                "verify_aud": False,  # checked in _build_principal
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise McpAuthError("invalid_token", "Token expired", reason="expired") from exc
    except jwt.ImmatureSignatureError as exc:
        raise McpAuthError("invalid_token", "Token not yet valid", reason="not_yet_valid") from exc
    except jwt.InvalidIssuerError as exc:
        raise McpAuthError("invalid_token", "Invalid token issuer", reason="issuer") from exc
    except jwt.InvalidSignatureError as exc:
        raise McpAuthError("invalid_token", "Invalid token", reason="signature") from exc
    except jwt.InvalidTokenError as exc:
        raise McpAuthError("invalid_token", "Invalid token", reason="claims") from exc

    max_lifetime = int(getattr(settings, "mcp_max_token_lifetime_seconds", 0) or 0)
    if max_lifetime > 0:
        try:
            lifetime = float(claims["exp"]) - float(claims["iat"])
        except (TypeError, ValueError) as exc:
            raise McpAuthError("invalid_token", "Invalid token", reason="claims") from exc
        if lifetime > max_lifetime:
            raise McpAuthError("invalid_token", "Token lifetime too long", reason="lifetime")

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
        raise McpAuthError("invalid_token", "Opaque tokens are not accepted by this server", reason="opaque_disabled")

    cache_key = token_fingerprint(token)
    cached = _accepted.get(cache_key)
    if cached is not None:
        return cached
    rejected = _rejected.get(cache_key)
    if rejected is not None:
        error, description, status_code = rejected
        raise McpAuthError(error, description, status_code, reason="cached_rejection")

    try:
        principal, ttl = _verify_opaque_with_clerk(token, secret_key, settings, config)
    except McpAuthError as exc:
        if exc.status_code in (401, 403):
            _rejected.put(
                cache_key,
                (exc.error, exc.description, exc.status_code),
                float(getattr(settings, "mcp_negative_token_cache_seconds", 0) or 0),
            )
        raise
    _accepted.put(cache_key, principal, ttl)
    return principal


def _verify_opaque_with_clerk(token: str, secret_key: str, settings, config: McpConfig) -> tuple[McpPrincipal, float]:
    """Ask Clerk; return the principal and how long it may be cached."""
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
        raise McpAuthError(
            "temporarily_unavailable", "Unable to verify token", status_code=503, reason="clerk_unavailable"
        ) from exc

    if response.status_code >= 500 or response.status_code == 429:
        logger.error("MCP auth: Clerk token verification failed with HTTP %s", response.status_code)
        raise McpAuthError(
            "temporarily_unavailable", "Unable to verify token", status_code=503, reason="clerk_unavailable"
        )
    if response.status_code != 200:
        raise McpAuthError("invalid_token", "Invalid token", reason="opaque_rejected")

    try:
        data = response.json()
    except ValueError as exc:
        raise McpAuthError("invalid_token", "Invalid token", reason="opaque_rejected") from exc
    if not isinstance(data, dict) or data.get("active") is False:
        raise McpAuthError("invalid_token", "Invalid token", reason="opaque_rejected")
    if data.get("revoked") is not False or data.get("expired") is not False:
        raise McpAuthError("invalid_token", "Token revoked or expired", reason="revoked_or_expired")

    now_ms = time.time() * 1000
    expiration = data.get("expiration")
    if expiration is not None:
        try:
            expiration_ms = float(expiration)
        except (TypeError, ValueError) as exc:
            raise McpAuthError("invalid_token", "Invalid token", reason="opaque_rejected") from exc
        if expiration_ms <= now_ms:
            raise McpAuthError("invalid_token", "Token expired", reason="expired")
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
    return principal, min(float(settings.mcp_token_cache_seconds), remaining)


def verify_access_token(token: str, settings, config: McpConfig) -> McpPrincipal:
    """Verify a Clerk OAuth access token. Blocking: may call Clerk over HTTP.

    Only tokens with the expected shape reach the JWKS or Clerk's API.
    """
    if not token or len(token) > MAX_TOKEN_LENGTH:
        raise McpAuthError("invalid_token", "Invalid token", reason="malformed")
    if token.startswith(OPAQUE_TOKEN_PREFIX):
        if not _OPAQUE_TOKEN_RE.fullmatch(token):
            raise McpAuthError("invalid_token", "Invalid token", reason="malformed")
        return _verify_opaque(token, settings, config)
    if _JWT_RE.fullmatch(token):
        return _verify_jwt(token, settings, config)
    raise McpAuthError("invalid_token", "Unsupported token type", reason="malformed")
