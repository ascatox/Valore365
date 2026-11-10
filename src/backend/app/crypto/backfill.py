"""Backfill of the field encryption (TASK-57): encrypt legacy plaintext, fill blind indexes.

Used by ``scripts/encrypt_existing_data.py`` and, at app startup, by
``app/services/field_encryption_backfill.py``. Idempotent: a row is selected
only while it still has something to do (plaintext value, missing blind
index or source_sha256), and values already encrypted are left as they are.
Rows are walked by primary key in batches, one transaction per batch.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import StatementError

from .errors import FieldCryptoError
from .field import FieldCrypto, is_encrypted, is_encrypted_json

logger = logging.getLogger(__name__)


@dataclass
class TableResult:
    table: str
    scanned: int = 0
    updated: int = 0
    failed: list[str] = field(default_factory=list)
    stopped: bool = False  # interrupted by stop_event before the table was done
    error: str | None = None  # batch-level failure (isolate_errors=True only)


DRY_RUN_PLACEHOLDER = "<encrypt>"


def describe_error(exc: BaseException) -> str:
    """One-line error description without SQL parameters (they can hold personal data)."""
    if isinstance(exc, StatementError) and exc.orig is not None:
        exc = exc.orig
    first_line = (str(exc).strip().splitlines() or [""])[0]
    return f"{type(exc).__name__}: {first_line[:300]}"


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
    # TASK-66: the saved Tribunale session (JSON text), written encrypted when the
    # keys are configured; only rows saved without keys (dev) are pending.
    Target(
        table="tribunal_sessions",
        key="id",
        columns="id, owner_user_id, payload",
        pending="payload is not null and payload not like 'enc:v1:%'",
        transform=_simple("tribunal_sessions", "payload"),
    ),
)


def _update_sql(target: Target, columns: list[str]) -> str:
    assignments = ", ".join(
        f"{c} = cast(:{c} as jsonb)" if c in target.jsonb_columns else f"{c} = :{c}" for c in columns
    )
    # The pending clause again: a row rewritten (encrypted) by the app between the
    # select and this update is left alone instead of getting the old value back.
    return f"update {target.table} set {assignments} where {target.key} = :_key and ({target.pending})"


def backfill_table(
    crypto: FieldCrypto,
    conn_factory: Callable[[], Any],
    target: Target,
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    stop_event: threading.Event | None = None,
    batch_pause_seconds: float = 0.0,
    on_batch: Callable[[], None] | None = None,
    isolate_errors: bool = False,
) -> TableResult:
    """Walk the pending rows of ``target`` in batches (one transaction each).

    A row that fails to transform (FieldCryptoError/ValueError) is logged,
    listed in ``failed`` and skipped. Any other error (database, connection)
    rolls back the current batch: it propagates, or with ``isolate_errors``
    it is logged and stored in ``error`` (the batches already committed stay,
    and their counts too). After each batch: ``on_batch()`` (e.g. a lock
    heartbeat), then a stop check (``stop_event`` set = ``stopped``, the table
    is left for the next run), then a pause of ``batch_pause_seconds``
    (interrupted by ``stop_event``).
    """
    result = TableResult(target.table)
    ctx = Ctx(crypto, dry_run)
    after: Any = None
    try:
        while True:
            scanned = updated = 0
            failed: list[str] = []
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
                    scanned += 1
                    key = row[target.key]
                    try:
                        updates = target.transform(ctx, conn, dict(row))
                    except (FieldCryptoError, ValueError) as exc:
                        logger.error("%s %s=%s: %s", target.table, target.key, key, exc)
                        failed.append(str(key))
                        continue
                    if not updates:
                        continue
                    updated += 1
                    if not dry_run:
                        conn.execute(text(_update_sql(target, sorted(updates))), {**updates, "_key": key})
            # The batch is committed: count it.
            result.scanned += scanned
            result.updated += updated
            result.failed.extend(failed)
            after = rows[-1][target.key]
            if on_batch is not None:
                on_batch()
            if stop_event is not None and stop_event.is_set():
                result.stopped = True
                break
            if batch_pause_seconds > 0:
                if stop_event is not None:
                    if stop_event.wait(batch_pause_seconds):
                        result.stopped = True
                        break
                else:
                    time.sleep(batch_pause_seconds)
    except Exception as exc:
        if not isolate_errors:
            raise
        result.error = describe_error(exc)
        # No traceback: SQLAlchemy errors carry the statement parameters.
        logger.error("field encryption backfill: table %s aborted after %d rows: %s", target.table, result.scanned, result.error)
    return result


def backfill_all(
    crypto: FieldCrypto,
    conn_factory: Callable[[], Any],
    *,
    batch_size: int = 500,
    dry_run: bool = False,
    tables: set[str] | None = None,
    stop_event: threading.Event | None = None,
    batch_pause_seconds: float = 0.0,
    on_batch: Callable[[], None] | None = None,
    isolate_errors: bool = False,
) -> list[TableResult]:
    """Backfill every target (or only ``tables``); see backfill_table. Once
    ``stop_event`` is set the remaining tables are reported as ``stopped``."""
    results: list[TableResult] = []
    for target in TARGETS:
        if tables is not None and target.table not in tables:
            continue
        if stop_event is not None and stop_event.is_set():
            results.append(TableResult(target.table, stopped=True))
            continue
        results.append(
            backfill_table(
                crypto,
                conn_factory,
                target,
                batch_size=batch_size,
                dry_run=dry_run,
                stop_event=stop_event,
                batch_pause_seconds=batch_pause_seconds,
                on_batch=on_batch,
                isolate_errors=isolate_errors,
            )
        )
    return results
