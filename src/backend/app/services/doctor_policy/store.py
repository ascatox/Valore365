"""Persistence of Doctor 2.0 policies (contract §6) with optimistic locking.

A *policy set* is the active policy of one user for one exact scope
(``scope_fingerprint``); its documents live in immutable *versions*. Every
save creates a new version inside one transaction that locks the set row
(``select ... for update``) and compares ``current_version`` with the
caller's ``base_version``:

- no set yet and ``base_version is None`` -> create the set, version 1;
- no set yet and ``base_version`` given  -> :class:`StoreVersionConflict`;
- set exists and ``base_version`` differs from ``current_version`` (``None``
  included) -> :class:`StoreVersionConflict`; the older save never
  overwrites a more recent one (two tabs, PRD example F).

Creating the same set concurrently is guarded by the partial unique index on
``(owner_user_id, scope_fingerprint) where archived_at is null``: the loser
gets a conflict, not a duplicate.

The store does not check portfolio ownership: the service does that for every
read and write (scope members are stored without FK to ``portfolios``).
Plain SQLAlchemy ``text`` queries on the repository engine, like the other
repositories.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.exc import IntegrityError


class StoreVersionConflict(Exception):
    def __init__(self, current_version: int | None) -> None:
        super().__init__("version conflict")
        self.current_version = current_version


@dataclass(frozen=True)
class PolicySetRecord:
    id: int
    owner_user_id: str
    scope_type: str
    scope_fingerprint: str
    name: str
    active: bool
    current_version: int
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    portfolio_ids: tuple[int, ...] = ()
    document: dict[str, Any] | None = None
    document_hash: str | None = None


@dataclass(frozen=True)
class PolicyVersionRecord:
    id: int
    policy_set_id: int
    version_number: int
    schema_version: int
    document: dict[str, Any]
    document_hash: str
    source: str
    diff: list[dict[str, Any]] = field(default_factory=list)
    confirmed_at: datetime | None = None
    actor_user_id: str | None = None


def _json(value: Any) -> Any:
    if value is None or isinstance(value, (dict, list)):
        return value
    return json.loads(value)


_SET_COLUMNS = """
    s.id, s.owner_user_id, s.scope_type, s.scope_fingerprint, s.name, s.active,
    s.current_version, s.created_at, s.updated_at, s.archived_at,
    v.constraints as document, v.document_hash
"""


class DoctorPolicyStore:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    # -- transactions ------------------------------------------------------

    @contextmanager
    def transaction(self, conn: Connection | None = None) -> Iterator[Connection]:
        """Reuse the caller's connection or open a new transaction."""
        if conn is not None:
            yield conn
            return
        with self.engine.begin() as new_conn:
            yield new_conn

    # -- reads -------------------------------------------------------------

    def _members(self, conn: Connection, policy_set_id: int) -> tuple[int, ...]:
        rows = conn.execute(
            text(
                "select portfolio_id from doctor_policy_scope_members "
                "where policy_set_id = :id order by portfolio_id"
            ),
            {"id": policy_set_id},
        ).all()
        return tuple(int(r[0]) for r in rows)

    def _set_from_row(self, conn: Connection, row) -> PolicySetRecord:
        return PolicySetRecord(
            id=int(row["id"]),
            owner_user_id=str(row["owner_user_id"]),
            scope_type=str(row["scope_type"]),
            scope_fingerprint=str(row["scope_fingerprint"]),
            name=str(row["name"]),
            active=bool(row["active"]),
            current_version=int(row["current_version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            archived_at=row["archived_at"],
            portfolio_ids=self._members(conn, int(row["id"])),
            document=_json(row["document"]),
            document_hash=row["document_hash"],
        )

    def get_policy_set(
        self, owner_user_id: str, scope_fingerprint: str, *, conn: Connection | None = None,
    ) -> PolicySetRecord | None:
        """Active (non archived) set of the user for this exact scope."""
        with self.transaction(conn) as c:
            row = c.execute(
                text(
                    f"""
                    select {_SET_COLUMNS}
                    from doctor_policy_sets s
                    left join doctor_policy_versions v
                      on v.policy_set_id = s.id and v.version_number = s.current_version
                    where s.owner_user_id = :owner and s.scope_fingerprint = :fp and s.archived_at is null
                    """
                ),
                {"owner": owner_user_id, "fp": scope_fingerprint},
            ).mappings().first()
            return self._set_from_row(c, row) if row else None

    def get_policy_set_by_id(
        self, owner_user_id: str, policy_set_id: int, *, conn: Connection | None = None,
    ) -> PolicySetRecord | None:
        """Active set by id, only if it belongs to the user."""
        with self.transaction(conn) as c:
            row = c.execute(
                text(
                    f"""
                    select {_SET_COLUMNS}
                    from doctor_policy_sets s
                    left join doctor_policy_versions v
                      on v.policy_set_id = s.id and v.version_number = s.current_version
                    where s.id = :id and s.owner_user_id = :owner and s.archived_at is null
                    """
                ),
                {"owner": owner_user_id, "id": int(policy_set_id)},
            ).mappings().first()
            return self._set_from_row(c, row) if row else None

    def list_versions(self, policy_set_id: int, *, conn: Connection | None = None) -> list[PolicyVersionRecord]:
        """Every version of a set, newest first."""
        with self.transaction(conn) as c:
            rows = c.execute(
                text(
                    """
                    select id, policy_set_id, version_number, schema_version, constraints, document_hash,
                           source, diff, confirmed_at, actor_user_id
                    from doctor_policy_versions
                    where policy_set_id = :id
                    order by version_number desc
                    """
                ),
                {"id": int(policy_set_id)},
            ).mappings().all()
        return [self._version_from_row(r) for r in rows]

    def get_version(
        self, policy_set_id: int, version_number: int, *, conn: Connection | None = None,
    ) -> PolicyVersionRecord | None:
        with self.transaction(conn) as c:
            row = c.execute(
                text(
                    """
                    select id, policy_set_id, version_number, schema_version, constraints, document_hash,
                           source, diff, confirmed_at, actor_user_id
                    from doctor_policy_versions
                    where policy_set_id = :id and version_number = :n
                    """
                ),
                {"id": int(policy_set_id), "n": int(version_number)},
            ).mappings().first()
        return self._version_from_row(row) if row else None

    @staticmethod
    def _version_from_row(row) -> PolicyVersionRecord:
        return PolicyVersionRecord(
            id=int(row["id"]),
            policy_set_id=int(row["policy_set_id"]),
            version_number=int(row["version_number"]),
            schema_version=int(row["schema_version"]),
            document=_json(row["constraints"]),
            document_hash=str(row["document_hash"]),
            source=str(row["source"]),
            diff=_json(row["diff"]) or [],
            confirmed_at=row["confirmed_at"],
            actor_user_id=row["actor_user_id"],
        )

    # -- writes ------------------------------------------------------------

    def save_version(
        self,
        *,
        owner_user_id: str,
        scope_type: str,
        scope_fingerprint: str,
        portfolio_ids: Sequence[int],
        name: str | None,
        document: dict[str, Any],
        document_hash: str,
        schema_version: int,
        source: str,
        base_version: int | None,
        diff: list[dict[str, Any]],
        conn: Connection | None = None,
    ) -> PolicySetRecord:
        """Append a version with optimistic locking; returns the updated set.

        Raises :class:`StoreVersionConflict` when ``base_version`` is not the
        current version of the scope's set (or a set exists while
        ``base_version`` is None, or none exists while it is not).
        """
        with self.transaction(conn) as c:
            row = c.execute(
                text(
                    """
                    select id, current_version
                    from doctor_policy_sets
                    where owner_user_id = :owner and scope_fingerprint = :fp and archived_at is null
                    for update
                    """
                ),
                {"owner": owner_user_id, "fp": scope_fingerprint},
            ).mappings().first()

            if row is None:
                if base_version is not None:
                    raise StoreVersionConflict(None)
                try:
                    with c.begin_nested():
                        set_id = c.execute(
                            text(
                                """
                                insert into doctor_policy_sets
                                  (owner_user_id, scope_type, scope_fingerprint, name, active, current_version)
                                values (:owner, :scope_type, :fp, :name, true, 0)
                                returning id
                                """
                            ),
                            {
                                "owner": owner_user_id,
                                "scope_type": scope_type,
                                "fp": scope_fingerprint,
                                "name": name or "La mia policy",
                            },
                        ).scalar_one()
                except IntegrityError as exc:
                    # Another request created the set between our select and insert.
                    raise StoreVersionConflict(None) from exc
                for pid in sorted({int(p) for p in portfolio_ids}):
                    c.execute(
                        text(
                            "insert into doctor_policy_scope_members (policy_set_id, portfolio_id) "
                            "values (:id, :pid)"
                        ),
                        {"id": set_id, "pid": pid},
                    )
                current = 0
            else:
                set_id = int(row["id"])
                current = int(row["current_version"])
                if base_version is None or int(base_version) != current:
                    raise StoreVersionConflict(current)

            new_version = current + 1
            c.execute(
                text(
                    """
                    insert into doctor_policy_versions
                      (policy_set_id, version_number, schema_version, constraints, document_hash,
                       source, diff, actor_user_id)
                    values (:id, :n, :schema_version, cast(:doc as jsonb), :hash, :source,
                            cast(:diff as jsonb), :actor)
                    """
                ),
                {
                    "id": set_id,
                    "n": new_version,
                    "schema_version": int(schema_version),
                    "doc": json.dumps(document, sort_keys=True),
                    "hash": document_hash,
                    "source": source,
                    "diff": json.dumps(diff or [], sort_keys=True, default=str),
                    "actor": owner_user_id,
                },
            )
            c.execute(
                text(
                    """
                    update doctor_policy_sets
                       set current_version = :n,
                           name = coalesce(cast(:name as text), name),
                           updated_at = now()
                     where id = :id
                    """
                ),
                {"id": set_id, "n": new_version, "name": name},
            )
            record = self.get_policy_set_by_id(owner_user_id, set_id, conn=c)
            assert record is not None
            return record

    def archive(self, owner_user_id: str, policy_set_id: int, *, conn: Connection | None = None) -> bool:
        """Archive the set (frees the scope for a new one). True if archived."""
        with self.transaction(conn) as c:
            result = c.execute(
                text(
                    """
                    update doctor_policy_sets
                       set archived_at = now(), active = false, updated_at = now()
                     where id = :id and owner_user_id = :owner and archived_at is null
                    """
                ),
                {"id": int(policy_set_id), "owner": owner_user_id},
            )
            return (result.rowcount or 0) > 0
