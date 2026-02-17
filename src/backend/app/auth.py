import time
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from fastapi import Header

from .config import get_settings
from .errors import AppError

_JWKS_CACHE: dict[str, Any] = {"value": None, "expires_at": 0.0}


@dataclass
class AuthContext:
    user_id: str
    claims: dict[str, Any]


def _get_jwks(jwks_url: str) -> dict[str, Any]:
    now = time.time()
    if _JWKS_CACHE["value"] and now < _JWKS_CACHE["expires_at"]:
        return _JWKS_CACHE["value"]

    with httpx.Client(timeout=8.0) as client:
        response = client.get(jwks_url)
        response.raise_for_status()
        payload = response.json()

    if not isinstance(payload, dict) or "keys" not in payload:
        raise AppError(code="unauthorized", message="JWKS non valido", status_code=401)

    _JWKS_CACHE["value"] = payload
    _JWKS_CACHE["expires_at"] = now + 300
    return payload


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise AppError(code="unauthorized", message="Authorization header mancante", status_code=401)
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AppError(code="unauthorized", message="Authorization header non valido", status_code=401)
    return parts[1].strip()


def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    settings = get_settings()
    if not settings.clerk_auth_enabled:
        return AuthContext(user_id="dev-user", claims={})

    if not settings.clerk_jwks_url:
        raise AppError(code="unauthorized", message="Config Clerk incompleta", status_code=401)

    token = _extract_bearer_token(authorization)
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise AppError(code="unauthorized", message="Token JWT non valido", status_code=401) from exc

    kid = header.get("kid")
    if not kid:
        raise AppError(code="unauthorized", message="Token senza kid", status_code=401)

    jwks = _get_jwks(settings.clerk_jwks_url)
    key = None
    for candidate in jwks.get("keys", []):
        if candidate.get("kid") == kid:
            key = jwt.algorithms.RSAAlgorithm.from_jwk(candidate)
            break
    if key is None:
        raise AppError(code="unauthorized", message="Chiave JWT non trovata", status_code=401)

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
    except jwt.PyJWTError as exc:
        raise AppError(code="unauthorized", message="Token scaduto o non valido", status_code=401) from exc

    allowed_azp = settings.clerk_authorized_parties_list
    if allowed_azp:
        azp = claims.get("azp")
        if azp not in allowed_azp:
            raise AppError(code="unauthorized", message="Authorized party non valida", status_code=401)

    user_id = claims.get("sub")
    if not user_id:
        raise AppError(code="unauthorized", message="Claim sub mancante", status_code=401)

    return AuthContext(user_id=str(user_id), claims=claims)
