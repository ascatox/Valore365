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


def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    return AuthContext(user_id="dev-user", claims={})
