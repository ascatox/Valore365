"""Persistenza delle sedute del Tribunale e limite giornaliero (TASK-66).

Contratto: ``docs/tribunale/api-contracts.md`` §8.6 (chiave, limite e riuso), §8.7
(``TribunalSession``), §3.3 (ultima seduta); interfaccia ``SessionStore`` di
``orchestrator.py``. Schema: ``database/migrations/20261110_01_tribunal_sessions.sql``.

- ``tribunal_sessions``: **una riga per (utente, fingerprint esatto)**, l'ultima seduta
  conclusa. ``save`` fa un upsert, quindi una nuova seduta sullo stesso scope sovrascrive la
  precedente. La seduta (JSON) è in ``payload``, cifrata a livello di campo con la DEK
  dell'utente (``app/crypto``, AAD ``tribunal_sessions:payload:<owner_user_id>``); in chiaro
  restano solo ``case_file_hash``, ``contract_version``, ``prompt_version``, ``key_source``,
  ``session_id`` e le date.
- ``tribunal_session_members``: portafogli dello scope, FK su ``portfolios`` con cascata; il
  trigger del database cancella la seduta quando un membro sparisce (portafoglio eliminato,
  anche dentro uno scope aggregato).
- ``tribunal_daily_usage``: contatore per (utente, giorno di calendario ``Europe/Rome``)
  delle sedute salvate con ``key_source = "server"``, nella stessa transazione del
  salvataggio. È separato dalle sedute: sovrascriverle o cancellarle non restituisce sedute
  al limite. Il giorno è quello di ``completed_at`` della seduta (l'orologio
  dell'orchestratore), così ``count_today(now=...)`` e ``save`` usano lo stesso orologio.

Solo le sedute concluse arrivano a ``save`` (l'orchestratore non lo chiama per sedute fallite,
interrotte o in timeout), quindi quelle non sono salvate né conteggiate.

Lo store non verifica la proprietà dei portafogli: lo fa l'orchestratore (``resolve_scope``)
prima di ogni lettura e scrittura. Query SQLAlchemy ``text`` sull'engine del repository, come
``services/doctor_policy/store.py``. Log: mai contenuti della seduta.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from ...crypto import DecryptionError, decrypt_field, encrypt_field
from ..doctor_policy.scope import build_scope

logger = logging.getLogger("app.services.tribunal")

_ROME = ZoneInfo("Europe/Rome")
_PAYLOAD_TABLE, _PAYLOAD_COLUMN = "tribunal_sessions", "payload"
_KEY_SOURCES = ("user", "server")
# Righe del contatore più vecchie di così vengono potate al salvataggio successivo.
USAGE_RETENTION_DAYS = 31


def rome_day(moment: datetime) -> date:
    """Giorno di calendario ``Europe/Rome`` di un istante (naive = UTC)."""
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return moment.astimezone(_ROME).date()


def _parse_iso(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


class TribunalStore:
    """Implementa ``orchestrator.SessionStore`` su Postgres."""

    def __init__(self, engine: Engine, *, clock: Callable[[], datetime] | None = None) -> None:
        self.engine = engine
        self._clock = clock or (lambda: datetime.now(UTC))

    # -- transazioni -------------------------------------------------------

    @contextmanager
    def transaction(self, conn: Connection | None = None) -> Iterator[Connection]:
        """Riusa la connessione del chiamante o apre una nuova transazione."""
        if conn is not None:
            yield conn
            return
        with self.engine.begin() as new_conn:
            yield new_conn

    # -- letture -----------------------------------------------------------

    def get_latest(self, user_id: str, scope_fingerprint: str, *,
                   conn: Connection | None = None) -> dict[str, Any] | None:
        """Ultima seduta salvata (``TribunalSession`` completa) o ``None``.

        Una seduta che non si decifra più (chiave dell'utente cancellata, valore corrotto) è
        trattata come assente: l'utente può sempre rifarla.
        """
        with self.transaction(conn) as c:
            row = c.execute(
                text(
                    "select owner_user_id, payload from tribunal_sessions "
                    "where owner_user_id = :owner and scope_fingerprint = :fp"
                ),
                {"owner": user_id, "fp": scope_fingerprint},
            ).mappings().first()
            if row is None:
                return None
            try:
                plain = decrypt_field(c, _PAYLOAD_TABLE, _PAYLOAD_COLUMN, str(row["owner_user_id"]), row["payload"])
                session = json.loads(plain)
            except (DecryptionError, ValueError, TypeError) as exc:
                logger.warning("tribunal.store read error=%s", type(exc).__name__)
                return None
        return session if isinstance(session, dict) else None

    def count_today(self, user_id: str, *, now: datetime | None = None,
                    conn: Connection | None = None) -> int:
        """Sedute salvate oggi (giorno ``Europe/Rome`` di ``now``) con la chiave del server."""
        day = rome_day(now or self._clock())
        with self.transaction(conn) as c:
            value = c.execute(
                text(
                    "select sessions from tribunal_daily_usage "
                    "where owner_user_id = :owner and usage_day = :day"
                ),
                {"owner": user_id, "day": day},
            ).scalar()
        return int(value or 0)

    # -- scritture ---------------------------------------------------------

    def save(self, user_id: str, portfolio_ids: list[int], session: dict[str, Any], *,
             key_source: str, conn: Connection | None = None) -> None:
        """Salva (sovrascrive) l'ultima seduta di ``(user_id, scope)``; con
        ``key_source = "server"`` conta una seduta nel giorno di ``completed_at``.

        Tutto in una transazione: se una scrittura fallisce non resta né la seduta né il
        conteggio. ``ValueError`` se la seduta non è una ``TribunalSession`` coerente con
        ``portfolio_ids``.
        """
        if key_source not in _KEY_SOURCES:
            raise ValueError("key_source non valido")
        ids: Sequence[int] = sorted({int(p) for p in portfolio_ids})
        fingerprint = build_scope(list(ids)).fingerprint
        scope = session.get("scope") or {}
        case_file = session.get("case_file") or {}
        session_id = session.get("session_id")
        case_hash = case_file.get("hash")
        contract_version = session.get("contract_version")
        if scope.get("fingerprint") != fingerprint:
            raise ValueError("lo scope della seduta non corrisponde ai portafogli")
        if not (isinstance(session_id, str) and session_id and isinstance(case_hash, str) and case_hash
                and isinstance(contract_version, str) and contract_version):
            raise ValueError("seduta incompleta")
        now = self._clock()
        completed_at = _parse_iso(session.get("completed_at")) or now
        created_at = _parse_iso(session.get("created_at")) or completed_at
        payload = json.dumps(session, ensure_ascii=False, separators=(",", ":"))

        with self.transaction(conn) as c:
            row_id = c.execute(
                text(
                    """
                    insert into tribunal_sessions
                      (owner_user_id, scope_fingerprint, session_id, case_file_hash, contract_version,
                       prompt_version, key_source, payload, created_at, completed_at, saved_at)
                    values (:owner, :fp, :sid, :hash, :cv, :pv, :ks, :payload, :created, :completed, :saved)
                    on conflict (owner_user_id, scope_fingerprint) do update set
                      session_id = excluded.session_id,
                      case_file_hash = excluded.case_file_hash,
                      contract_version = excluded.contract_version,
                      prompt_version = excluded.prompt_version,
                      key_source = excluded.key_source,
                      payload = excluded.payload,
                      created_at = excluded.created_at,
                      completed_at = excluded.completed_at,
                      saved_at = excluded.saved_at
                    returning id
                    """
                ),
                {
                    "owner": user_id,
                    "fp": fingerprint,
                    "sid": session_id,
                    "hash": case_hash,
                    "cv": contract_version,
                    "pv": str(session.get("prompt_version") or ""),
                    "ks": key_source,
                    "payload": encrypt_field(c, _PAYLOAD_TABLE, _PAYLOAD_COLUMN, user_id, payload),
                    "created": created_at,
                    "completed": completed_at,
                    "saved": now,
                },
            ).scalar_one()
            # Stesso fingerprint = stessi portafogli: i membri non cambiano mai su un
            # aggiornamento. Mai cancellarli qui: il trigger eliminerebbe la seduta.
            for pid in ids:
                c.execute(
                    text(
                        "insert into tribunal_session_members (tribunal_session_id, portfolio_id) "
                        "values (:id, :pid) on conflict do nothing"
                    ),
                    {"id": int(row_id), "pid": pid},
                )
            if key_source == "server":
                day = rome_day(completed_at)
                c.execute(
                    text(
                        """
                        insert into tribunal_daily_usage (owner_user_id, usage_day, sessions, updated_at)
                        values (:owner, :day, 1, :now)
                        on conflict (owner_user_id, usage_day) do update set
                          sessions = tribunal_daily_usage.sessions + 1,
                          updated_at = excluded.updated_at
                        """
                    ),
                    {"owner": user_id, "day": day, "now": now},
                )
                c.execute(
                    text("delete from tribunal_daily_usage where owner_user_id = :owner and usage_day < :cutoff"),
                    {"owner": user_id, "cutoff": day - timedelta(days=USAGE_RETENTION_DAYS)},
                )

    def delete_for_user(self, user_id: str, *, conn: Connection | None = None) -> int:
        """Cancella sedute e contatori dell'utente (cancellazione dell'account).

        Restituisce il numero di sedute cancellate. Nessun flusso del backend lo chiama ancora.
        """
        with self.transaction(conn) as c:
            result = c.execute(
                text("delete from tribunal_sessions where owner_user_id = :owner"), {"owner": user_id},
            )
            c.execute(text("delete from tribunal_daily_usage where owner_user_id = :owner"), {"owner": user_id})
            return int(result.rowcount or 0)


__all__ = ["USAGE_RETENTION_DAYS", "TribunalStore", "rome_day"]
