import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import jwt
from fastapi import Header

from .config import get_settings
from .errors import AppError

logger = logging.getLogger(__name__)

_JWKS_CACHE: dict[str, Any] = {"keys": [], "expires_at": 0.0}
_JWKS_CACHE_TTL = 3600.0  # 1 hour


@dataclass
class AuthContext:
    user_id: str
    org_id: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)


def _fetch_jwks(url: str) -> list[dict[str, Any]]:
    """Fetch JWKS from Clerk and return the list of key dicts."""
    resp = httpx.get(url, timeout=10)
    resp.raise_for_status()
    return resp.json().get("keys", [])


def _get_signing_key(token: str, jwks_url: str) -> jwt.PyJWK:
    """Return the signing key matching the token's kid, with cache + auto-refresh."""
    now = time.monotonic()

    # Try cached keys first
    if now < _JWKS_CACHE["expires_at"] and _JWKS_CACHE["keys"]:
        try:
            jwk_set = jwt.PyJWKSet(keys=_JWKS_CACHE["keys"])
            header = jwt.get_unverified_header(token)
            return jwk_set[header["kid"]]
        except (KeyError, jwt.PyJWKError):
            pass  # kid mismatch — refresh below

    # Fetch fresh JWKS
    keys = _fetch_jwks(jwks_url)
    _JWKS_CACHE["keys"] = keys
    _JWKS_CACHE["expires_at"] = now + _JWKS_CACHE_TTL

    try:
        jwk_set = jwt.PyJWKSet(keys=keys)
        header = jwt.get_unverified_header(token)
        return jwk_set[header["kid"]]
    except (KeyError, jwt.PyJWKError) as exc:
        raise AppError(code="auth_error", message="Unable to find signing key", status_code=401) from exc


def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    settings = get_settings()

    if not settings.clerk_auth_enabled:
        return AuthContext(user_id="dev-user", org_id=None, claims={})

    if not authorization or not authorization.startswith("Bearer "):
        raise AppError(code="auth_error", message="Missing or invalid Authorization header", status_code=401)

    token = authorization[7:]

    try:
        signing_key = _get_signing_key(token, settings.clerk_jwks_url)

        decode_options: dict[str, Any] = {
            "algorithms": ["RS256"],
            "key": signing_key.key,
            "options": {"require": ["exp", "iat", "sub"], "verify_aud": False},
        }

        claims = jwt.decode(token, **decode_options)

        # Validate azp claim against authorized parties (supports wildcard patterns).
        azp_list = settings.clerk_authorized_parties_list
        if azp_list and "azp" in claims:
            azp = claims["azp"]
            def _azp_matches(azp_value: str, pattern: str) -> bool:
                if pattern == azp_value:
                    return True
                # Support wildcard: https://*.vercel.app matches https://foo.vercel.app
                wildcard = "://*."
                if wildcard in pattern:
                    scheme, suffix = pattern.split(wildcard, 1)
                    return azp_value.startswith(scheme + "://") and azp_value.endswith("." + suffix)
                return False

            if not any(_azp_matches(azp, party) for party in azp_list):
                logger.warning("azp rejected: azp=%s allowed=%s", azp, azp_list)
                raise AppError(
                    code="auth_error",
                    message=f"Token authorized party not allowed: {azp}",
                    status_code=401,
                )

        return AuthContext(
            user_id=claims["sub"],
            org_id=claims.get("org_id"),
            claims=claims,
        )

    except jwt.ExpiredSignatureError as exc:
        raise AppError(code="auth_error", message="Token expired", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(code="auth_error", message="Invalid token", status_code=401) from exc
