"""TASK-66: sedute del Tribunale su un PostgreSQL 16 reale (cluster usa e getta).

``TribunalStore`` sullo schema reale (``database/schema.sql`` + migrazioni) con la cifratura
attiva e il vero ``PortfolioRepository``: payload cifrato, upsert per (utente, scope),
contatore per giorno di Roma, cascata alla cancellazione del portafoglio (trigger) e
``delete_for_user``. Saltato senza i binari di Postgres (vedi conftest.py).
"""

from __future__ import annotations

import base64
import copy
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from app.crypto import FieldCrypto, is_encrypted, parse_keyring, set_field_crypto
from app.crypto.backfill import backfill_all
from app.models import PortfolioCreate
from app.repository import PortfolioRepository
from app.services.doctor_policy.scope import build_scope
from app.services.tribunal.store import TribunalStore
from app.sql import load_sql

FIXTURE = json.loads(
    (Path(__file__).resolve().parents[4] / "docs" / "tribunale" / "fixtures" / "seduta-esempio.json")
    .read_text(encoding="utf-8")
)
NOW = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)
KEY = base64.b64encode(os.urandom(32)).decode()


@pytest.fixture()
def crypto(pg_engine):
    instance = FieldCrypto(parse_keyring(f"k1:{KEY}"), base64.b64decode(base64.b64encode(os.urandom(32))))
    set_field_crypto(instance)
    yield instance
    set_field_crypto(None)
    # Il cluster è condiviso con gli altri test (es. rotazione della KEK): niente DEK estranee.
    with pg_engine.begin() as conn:
        conn.execute(text("delete from user_data_keys where user_id like 'trb_user_%'"))


@pytest.fixture()
def repo(pg_engine):
    return PortfolioRepository(pg_engine)


@pytest.fixture()
def store(pg_engine):
    # La copia della migrazione applicata all'avvio è idempotente sopra lo schema.
    with pg_engine.begin() as conn:
        conn.execute(text(load_sql("migrations/create_tribunal_sessions")))
        conn.execute(text(load_sql("migrations/create_tribunal_sessions")))
    return TribunalStore(pg_engine, clock=lambda: NOW)


def _portfolio(repo, user, name="Pensione"):
    return repo.create_portfolio(PortfolioCreate(name=name, base_currency="EUR", timezone="Europe/Rome"), user).id


def _session(ids, *, hash_=None, completed_at="2026-11-10T14:00:49Z", sid="trb_5f0c2a9e7d41b386"):
    session = copy.deepcopy(FIXTURE["session"])
    scope = build_scope(ids).model_dump()
    session["scope"] = scope
    session["case_file"]["scope"] = scope
    if hash_:
        session["case_file"]["hash"] = hash_
    session["completed_at"] = completed_at
    session["session_id"] = sid
    return session


def _scalar(engine, sql, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params).scalar()


def test_save_encrypts_payload_and_reads_back(pg_engine, repo, store, crypto):
    user = "trb_user_save"
    pid = _portfolio(repo, user)
    session = _session([pid])
    store.save(user, [pid], session, key_source="server")
    assert store.get_latest(user, build_scope([pid]).fingerprint) == session
    payload = _scalar(pg_engine, "select payload from tribunal_sessions where owner_user_id = :u", u=user)
    assert is_encrypted(payload) and "VWCE" not in payload
    assert _scalar(pg_engine, "select case_file_hash from tribunal_sessions where owner_user_id = :u", u=user) \
        == session["case_file"]["hash"]
    # Backfill: nulla da fare sulle sedute già cifrate.
    (result,) = backfill_all(crypto, pg_engine.begin, tables={"tribunal_sessions"})
    assert result.updated == 0 and not result.failed


def test_overwrite_and_daily_usage(pg_engine, repo, store, crypto):
    user = "trb_user_usage"
    a, b = _portfolio(repo, user, "A"), _portfolio(repo, user, "B")
    store.save(user, [a], _session([a], completed_at="2026-11-10T22:59:59Z"), key_source="server")
    store.save(user, [a], _session([a], hash_="f" * 64, completed_at="2026-11-10T22:59:59Z"), key_source="server")
    store.save(user, [a, b], _session([a, b], completed_at="2026-11-10T23:00:00Z"), key_source="server")
    store.save(user, [b], _session([b]), key_source="user")
    assert _scalar(pg_engine, "select count(*) from tribunal_sessions where owner_user_id = :u", u=user) == 3
    assert store.get_latest(user, build_scope([a]).fingerprint)["case_file"]["hash"] == "f" * 64
    assert store.count_today(user, now=datetime(2026, 11, 10, 22, 59, 59, tzinfo=timezone.utc)) == 2
    assert store.count_today(user, now=datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)) == 1


def test_plaintext_session_is_backfilled(pg_engine, repo, store, crypto):
    user = "trb_user_backfill"
    pid = _portfolio(repo, user)
    set_field_crypto(None)                       # salvata senza chiavi (dev)
    session = _session([pid])
    store.save(user, [pid], session, key_source="user")
    assert not is_encrypted(_scalar(pg_engine, "select payload from tribunal_sessions where owner_user_id = :u", u=user))
    set_field_crypto(crypto)
    (result,) = backfill_all(crypto, pg_engine.begin, tables={"tribunal_sessions"})
    assert result.updated >= 1 and not result.failed
    assert is_encrypted(_scalar(pg_engine, "select payload from tribunal_sessions where owner_user_id = :u", u=user))
    assert store.get_latest(user, build_scope([pid]).fingerprint) == session


def test_delete_portfolio_cascades_to_single_and_aggregate_sessions(pg_engine, repo, store, crypto):
    user = "trb_user_cascade"
    a, b = _portfolio(repo, user, "A"), _portfolio(repo, user, "B")
    for ids in ([a], [a, b], [b]):
        store.save(user, ids, _session(ids), key_source="server")
    repo.delete_portfolio(a, user)
    assert store.get_latest(user, build_scope([a]).fingerprint) is None
    assert store.get_latest(user, build_scope([a, b]).fingerprint) is None
    assert store.get_latest(user, build_scope([b]).fingerprint) is not None
    assert _scalar(pg_engine, "select count(*) from tribunal_session_members where portfolio_id = :a", a=a) == 0
    assert store.count_today(user, now=NOW) == 3     # il limite non si azzera cancellando


def test_delete_for_user(pg_engine, repo, store, crypto):
    user, other = "trb_user_delete", "trb_user_keep"
    a, o = _portfolio(repo, user), _portfolio(repo, other)
    store.save(user, [a], _session([a]), key_source="server")
    store.save(other, [o], _session([o]), key_source="server")
    assert store.delete_for_user(user) == 1
    assert store.get_latest(user, build_scope([a]).fingerprint) is None and store.count_today(user, now=NOW) == 0
    assert _scalar(pg_engine, "select count(*) from tribunal_session_members where portfolio_id = :a", a=a) == 0
    assert store.get_latest(other, build_scope([o]).fingerprint) is not None
    assert store.count_today(other, now=NOW) == 1


def test_rls_enabled(pg_engine, store):
    with pg_engine.begin() as conn:
        rows = conn.execute(
            text("select relname, relrowsecurity from pg_class where relname in "
                 "('tribunal_sessions', 'tribunal_session_members', 'tribunal_daily_usage')")
        ).all()
    assert sorted(rows) == [("tribunal_daily_usage", True), ("tribunal_session_members", True),
                            ("tribunal_sessions", True)]
