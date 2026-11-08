"""Backfill of the field encryption (TASK-57): encrypt legacy plaintext, fill blind indexes.

Used by ``scripts/encrypt_existing_data.py``. Idempotent: a row is selected
only while it still has something to do (plaintext value, missing blind
index or source_sha256), and values already encrypted are left as they are.
Rows are walked by primary key in batches, one transaction per batch.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text

from .errors import FieldCryptoError
from .field import FieldCrypto, is_encrypted, is_encrypted_json

logger = logging.getLogger(__name__)


@dataclass
class TableResult:
    table: str
    scanned: int = 0
    updated: int = 0
    failed: list[str] = field(default_factory=list)


DRY_RUN_PLACEHOLDER = "<encrypt>"


@dataclass(frozen=True)
class Ctx:
    """The crypto engine plus the dry-run flag: a dry run never writes, DEKs included."""

    crypto: FieldCrypto
    dry_run: bool = False

    def encrypt(self, conn, table: str, column: str, owner: str, value: str) -> str:
        if self.dry_run:
            return DRY_RUN_PLACEHOLDER
        return self.crypto.encrypt(conn, table, column, owner, value)

    def encrypt_json(self, conn, table: str, column: str, owner: str, value: Any) -> str:
        if self.dry_run:
            return DRY_RUN_PLACEHOLDER
        return json.dumps(self.crypto.encrypt_json(conn, table, column, owner, value))


@dataclass(frozen=True)
class Target:
    table: str
    key: str
    columns: str  # select list (key and owner included)
    pending: str  # where clause: rows that still need work
    transform: Callable[[Ctx, Any, dict], dict[str, Any]]
    jsonb_columns: frozenset[str] = frozenset()


def _encrypt_if_plain(ctx: Ctx, conn, table: str, column: str, owner: str, value, updates: dict) -> None:
    if value is not None and not is_encrypted(value) and ctx.crypto.enabled:
        updates[column] = ctx.encrypt(conn, table, column, owner, value)


def _app_users(ctx: Ctx, conn, row: dict) -> dict[str, Any]:
    crypto = ctx.crypto
    owner = str(row["user_id"])
    updates: dict[str, Any] = {}
    email = row["email"]
    if row["email_bidx"] is None and email is not None:
        plain = crypto.decrypt(conn, "app_users", "email", owner, email)
        updates["email_bidx"] = crypto.email_blind_index(plain)
    _encrypt_if_plain(ctx, conn, "app_users", "email", owner, email, updates)
    return updates


def _simple(table: str, column: str) -> Callable[[Ctx, Any, dict], dict[str, Any]]:
    def transform(ctx: Ctx, conn, row: dict) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        _encrypt_if_plain(ctx, conn, table, column, str(row["owner_user_id"]), row[column], updates)
        return updates

    return transform


def _csv_import_batches(ctx: Ctx, conn, row: dict) -> dict[str, Any]:
    crypto = ctx.crypto
    table = "csv_import_batches"
    owner = str(row["owner_user_id"])
    updates: dict[str, Any] = {}
    filename = row["original_filename"]
    if row["original_filename_bidx"] is None and filename is not None:
        plain = crypto.decrypt(conn, table, "original_filename", owner, filename)
        updates["original_filename_bidx"] = crypto.csv_filename_blind_index(plain)
    _encrypt_if_plain(ctx, conn, table, "original_filename", owner, filename, updates)

    preview = row["preview_data"]
    if isinstance(preview, str):
        preview = json.loads(preview)
    if not is_encrypted_json(preview):
        if row["source_sha256"] is None and isinstance(preview, dict) and preview.get("source_sha256"):
            updates["source_sha256"] = str(preview["source_sha256"])
        if crypto.enabled:
            updates["preview_data"] = ctx.encrypt_json(conn, table, "preview_data", owner, preview)
    return updates


TARGETS: tuple[Target, ...] = (
    Target(
        table="app_users",
        key="user_id",
        columns="user_id, email, email_bidx",
        pending="email is not null and (email not like 'enc:v1:%' or email_bidx is null)",
        transform=_app_users,
    ),
    Target(
        table="portfolios",
        key="id",
        columns="id, owner_user_id, name",
        pending="name is not null and name not like 'enc:v1:%'",
        transform=_simple("portfolios", "name"),
    ),
    Target(
        table="transactions",
        key="id",
        columns="id, owner_user_id, notes",
        pending="notes is not null and notes not like 'enc:v1:%'",
        transform=_simple("transactions", "notes"),
    ),
    Target(
        table="csv_import_batches",
        key="id",
        columns="id, owner_user_id, original_filename, original_filename_bidx, source_sha256, preview_data",
        pending=(
            "(original_filename is not null and (original_filename not like 'enc:v1:%' "
            "or original_filename_bidx is null)) "
            "or not (jsonb_typeof(preview_data) = 'object' and preview_data ? '_enc') "
            "or (source_sha256 is null and jsonb_typeof(preview_data) = 'object' "
            "and preview_data ? 'source_sha256')"
        ),
        transform=_csv_import_batches,
        jsonb_columns=frozenset({"preview_data"}),
    ),
    Target(
        table="doctor_policy_sets",
        key="id",
        columns="id, owner_user_id, name",
        pending="name is not null and name not like 'enc:v1:%'",
        transform=_simple("doctor_policy_sets", "name"),
    ),
)


def _update_sql(target: Target, columns: list[str]) -> str:
    assignments = ", ".join(
        f"{c} = cast(:{c} as jsonb)" if c in target.jsonb_columns else f"{c} = :{c}" for c in columns
    )
    return f"update {target.table} set {assignments} where {target.key} = :_key"


def backfill_table(
    crypto: FieldCrypto,
    conn_factory: Callable[[], Any],
    target: Target,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
) -> TableResult:
    result = TableResult(target.table)
    ctx = Ctx(crypto, dry_run)
    after: Any = None
    while True:
        with conn_factory() as conn:
            params: dict[str, Any] = {"_limit": int(batch_size)}
            key_filter = ""
            if after is not None:
                key_filter = f"and {target.key} > :_after"
                params["_after"] = after
            rows = conn.execute(
                text(
                    f"select {target.columns} from {target.table} "
                    f"where ({target.pending}) {key_filter} order by {target.key} limit :_limit"
                ),
                params,
            ).mappings().all()
            if not rows:
                break
            for row in rows:
                result.scanned += 1
                key = row[target.key]
                try:
                    updates = target.transform(ctx, conn, dict(row))
                except (FieldCryptoError, ValueError) as exc:
                    logger.error("%s %s=%s: %s", target.table, target.key, key, exc)
                    result.failed.append(str(key))
                    continue
                if not updates:
                    continue
                result.updated += 1
                if not dry_run:
                    conn.execute(text(_update_sql(target, sorted(updates))), {**updates, "_key": key})
            after = rows[-1][target.key]
    return result


def backfill_all(
    crypto: FieldCrypto,
    conn_factory: Callable[[], Any],
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    tables: set[str] | None = None,
) -> list[TableResult]:
    return [
        backfill_table(crypto, conn_factory, target, batch_size=batch_size, dry_run=dry_run)
        for target in TARGETS
        if tables is None or target.table in tables
    ]
