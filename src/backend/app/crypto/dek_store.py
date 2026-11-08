"""Persistence of the wrapped per-user DEKs (table ``user_data_keys``)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from sqlalchemy import text


@dataclass(frozen=True)
class WrappedDek:
    user_id: str
    kek_id: str
    wrapped_dek: bytes


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, (bytearray, memoryview)):
        return bytes(value)
    raise TypeError(f"wrapped_dek: tipo inatteso {type(value).__name__}")


class DekStore(Protocol):
    def get(self, conn: Any, user_id: str) -> WrappedDek | None: ...

    def create_if_absent(self, conn: Any, user_id: str, kek_id: str, wrapped_dek: bytes) -> WrappedDek:
        """Insert the row unless one exists; return the stored (committed) row."""
        ...

    def delete(self, conn: Any, user_id: str) -> bool: ...

    def list_not_wrapped_with(self, conn: Any, kek_id: str, *, after_user_id: str | None, limit: int) -> list[WrappedDek]: ...

    def rewrap(self, conn: Any, user_id: str, *, old_kek_id: str, kek_id: str, wrapped_dek: bytes) -> bool: ...


class SqlDekStore:
    """``user_data_keys`` through SQLAlchemy ``text`` queries."""

    def get(self, conn: Any, user_id: str) -> WrappedDek | None:
        row = conn.execute(
            text("select user_id, kek_id, wrapped_dek from user_data_keys where user_id = :user_id"),
            {"user_id": user_id},
        ).mappings().fetchone()
        if row is None:
            return None
        return WrappedDek(str(row["user_id"]), str(row["kek_id"]), _as_bytes(row["wrapped_dek"]))

    def create_if_absent(self, conn: Any, user_id: str, kek_id: str, wrapped_dek: bytes) -> WrappedDek:
        # The DEK is created in its own short transaction on a separate
        # connection, committed before it is used: if the caller's transaction
        # rolled back after encrypting with it, a DEK created there would vanish
        # while values encrypted with it (or a cached copy) survived.
        # "on conflict do nothing" + re-select makes two concurrent creators
        # agree on the same DEK (the loser waits for the winner's commit).
        engine = conn.engine
        with engine.begin() as own:
            own.execute(
                text(
                    """
                    insert into user_data_keys (user_id, kek_id, wrapped_dek)
                    values (:user_id, :kek_id, :wrapped_dek)
                    on conflict (user_id) do nothing
                    """
                ),
                {"user_id": user_id, "kek_id": kek_id, "wrapped_dek": wrapped_dek},
            )
            stored = self.get(own, user_id)
        if stored is None:  # pragma: no cover - deleted between insert and select
            raise RuntimeError(f"DEK di {user_id} non trovata dopo la creazione")
        return stored

    def delete(self, conn: Any, user_id: str) -> bool:
        result = conn.execute(
            text("delete from user_data_keys where user_id = :user_id"),
            {"user_id": user_id},
        )
        return (result.rowcount or 0) > 0

    def list_not_wrapped_with(self, conn: Any, kek_id: str, *, after_user_id: str | None, limit: int) -> list[WrappedDek]:
        rows = conn.execute(
            text(
                """
                select user_id, kek_id, wrapped_dek
                from user_data_keys
                where kek_id <> :kek_id
                  and (cast(:after as varchar) is null or user_id > cast(:after as varchar))
                order by user_id
                limit :limit
                """
            ),
            {"kek_id": kek_id, "after": after_user_id, "limit": int(limit)},
        ).mappings().all()
        return [WrappedDek(str(r["user_id"]), str(r["kek_id"]), _as_bytes(r["wrapped_dek"])) for r in rows]

    def rewrap(self, conn: Any, user_id: str, *, old_kek_id: str, kek_id: str, wrapped_dek: bytes) -> bool:
        result = conn.execute(
            text(
                """
                update user_data_keys
                   set kek_id = :kek_id, wrapped_dek = :wrapped_dek, rotated_at = now()
                 where user_id = :user_id and kek_id = :old_kek_id
                """
            ),
            {"user_id": user_id, "kek_id": kek_id, "wrapped_dek": wrapped_dek, "old_kek_id": old_kek_id},
        )
        return (result.rowcount or 0) > 0
