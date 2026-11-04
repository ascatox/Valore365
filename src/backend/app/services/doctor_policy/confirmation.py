"""One-shot confirmation tokens for saving a Doctor policy (contract §5).

A preview of a *valid* draft issues a random token (``secrets.token_urlsafe``)
bound to ``(user_id, scope_fingerprint, document_hash, base_version)``. Only
its sha256 is stored; the plain token goes back to the UI once and never into
logs or to the LLM. ``POST /doctor/policies`` consumes it atomically with a
single ``UPDATE ... WHERE used_at IS NULL AND expires_at > now() RETURNING``,
so two concurrent saves cannot both use it.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

TOKEN_TTL = timedelta(minutes=15)
TOKEN_SOURCES = ("manual", "copilot", "template")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class IssuedToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class ConsumedToken:
    source: str


def issue_token(
    conn_or_engine: Connection | Engine,
    *,
    user_id: str,
    scope_fingerprint: str,
    document_hash: str,
    base_version: int | None,
    source: str = "manual",
    ttl: timedelta = TOKEN_TTL,
) -> IssuedToken:
    """Store a new token's hash and return the plain token (shown once)."""
    if source not in TOKEN_SOURCES:
        source = "manual"
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc) + ttl
    params = {
        "token_hash": hash_token(token),
        "user_id": user_id,
        "fingerprint": scope_fingerprint,
        "document_hash": document_hash,
        "base_version": base_version,
        "source": source,
        "expires_at": expires_at,
    }
    sql = text(
        """
        insert into doctor_confirmation_tokens
          (token_hash, owner_user_id, scope_fingerprint, document_hash, base_version, source, expires_at)
        values (:token_hash, :user_id, :fingerprint, :document_hash, :base_version, :source, :expires_at)
        """
    )
    if isinstance(conn_or_engine, Engine):
        with conn_or_engine.begin() as conn:
            conn.execute(sql, params)
            _purge_expired(conn)
    else:
        conn_or_engine.execute(sql, params)
    return IssuedToken(token=token, expires_at=expires_at)


def consume_token(
    conn: Connection,
    *,
    token: str | None,
    user_id: str,
    scope_fingerprint: str,
    document_hash: str,
    base_version: int | None,
) -> ConsumedToken | None:
    """Mark the token used if it matches every binding; None otherwise.

    Runs on the caller's transaction: if the save that follows fails, the
    rollback makes the token usable again.
    """
    if not token or not isinstance(token, str) or len(token) > 512:
        return None
    row = conn.execute(
        text(
            """
            update doctor_confirmation_tokens
               set used_at = now()
             where token_hash = :token_hash
               and used_at is null
               and expires_at > now()
               and owner_user_id = :user_id
               and scope_fingerprint = :fingerprint
               and document_hash = :document_hash
               and base_version is not distinct from cast(:base_version as int)
            returning source
            """
        ),
        {
            "token_hash": hash_token(token),
            "user_id": user_id,
            "fingerprint": scope_fingerprint,
            "document_hash": document_hash,
            "base_version": base_version,
        },
    ).mappings().first()
    if row is None:
        return None
    return ConsumedToken(source=str(row["source"] or "manual"))


def _purge_expired(conn: Connection) -> None:
    """Housekeeping: drop tokens expired for more than a day."""
    conn.execute(
        text("delete from doctor_confirmation_tokens where expires_at < now() - interval '1 day'")
    )
