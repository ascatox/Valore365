import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx
import jwt
from fastapi import Depends, Header
from sqlalchemy import text

from .config import get_settings
from .db import engine
from .errors import AppError

logger = logging.getLogger(__name__)

_JWKS_CACHE: dict[str, Any] = {"keys": [], "expires_at": 0.0}
_JWKS_CACHE_TTL = 3600.0  # 1 hour


@dataclass
class AuthContext:
    user_id: str
    org_id: str | None = None
    email: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)


def _extract_email_from_claims(claims: dict[str, Any]) -> str | None:
    candidate_keys = ("email", "email_address", "primary_email", "primary_email_address")
    for key in candidate_keys:
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip().lower()
        if isinstance(value, dict):
            nested = value.get("email_address") or value.get("email")
            if isinstance(nested, str) and nested.strip():
                return nested.strip().lower()

    email_addresses = claims.get("email_addresses")
    if isinstance(email_addresses, list):
        for item in email_addresses:
            if isinstance(item, str) and item.strip():
                return item.strip().lower()
            if isinstance(item, dict):
                nested = item.get("email_address") or item.get("email")
                if isinstance(nested, str) and nested.strip():
                    return nested.strip().lower()

    return None


def _extract_last_sign_in_at(claims: dict[str, Any]) -> datetime | None:
    for key in ("last_sign_in_at", "lastSignInAt"):
        value = claims.get(key)
        if isinstance(value, (int, float)):
            try:
                return datetime.fromtimestamp(float(value), tz=timezone.utc)
            except (OverflowError, OSError, ValueError):
                return None
        if isinstance(value, str) and value.strip():
            try:
                normalized = value.replace("Z", "+00:00")
                return datetime.fromisoformat(normalized)
            except ValueError:
                return None
    return None


def _sync_app_user(user_id: str, email: str | None, last_sign_in_at: datetime | None) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    """
                    insert into app_users (user_id, email, last_sign_in_at, last_seen_at, updated_at)
                    values (:user_id, :email, :last_sign_in_at, now(), now())
                    on conflict (user_id) do update set
                      email = coalesce(excluded.email, app_users.email),
                      last_sign_in_at = coalesce(excluded.last_sign_in_at, app_users.last_sign_in_at),
                      last_seen_at = now(),
                      updated_at = now()
                    """
                ),
                {
                    "user_id": user_id,
                    "email": email,
                    "last_sign_in_at": last_sign_in_at,
                },
            )
    except Exception:
        logger.exception("Failed to sync app user for %s", user_id)


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
        return AuthContext(user_id="dev-user", org_id=None, email=None, claims={})

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
                    message="Token authorized party not allowed",
                    status_code=401,
                )

        email = _extract_email_from_claims(claims)
        _sync_app_user(claims["sub"], email, _extract_last_sign_in_at(claims))

        return AuthContext(
            user_id=claims["sub"],
            org_id=claims.get("org_id"),
            email=email,
            claims=claims,
        )

    except jwt.ExpiredSignatureError as exc:
        raise AppError(code="auth_error", message="Token expired", status_code=401) from exc
    except jwt.InvalidTokenError as exc:
        raise AppError(code="auth_error", message="Invalid token", status_code=401) from exc


def require_admin(auth: AuthContext = Depends(require_auth)) -> AuthContext:
    settings = get_settings()
    allowed_user_ids = set(settings.admin_user_ids_list)
    allowed_emails = set(settings.admin_emails_list)

    if auth.user_id in allowed_user_ids:
        return auth
    if auth.email and auth.email.lower() in allowed_emails:
        return auth

    raise AppError(code="forbidden", message="Admin access required", status_code=403)
