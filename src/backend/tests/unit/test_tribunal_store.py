"""Store delle sedute del Tribunale (TASK-66, docs/tribunale/api-contracts.md §3.3, §8.6, §8.7).

``TribunalStore`` gira su SQLite in memoria con uno schema equivalente a quello di
``database/migrations/20261110_01_tribunal_sessions.sql`` (stesse tabelle, FK con cascata e un
trigger con lo stesso effetto), con la cifratura a livello di campo attiva (DEK in memoria).
La versione Postgres reale è in ``tests/integration/test_tribunal_store_postgres.py``.
"""

from __future__ import annotations

import base64
import copy
import os
import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import Any

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

from app.crypto import FieldCrypto, is_encrypted, parse_keyring, set_field_crypto
from app.services.doctor_policy.scope import build_scope
from app.services.tribunal import orchestrator as orch_module
from app.services.tribunal.orchestrator import NullSessionStore, TribunalOrchestrator, _default_store
from app.services.tribunal.store import USAGE_RETENTION_DAYS, TribunalStore, rome_day
from tests.unit.test_field_crypto import MemoryDekStore
from tests.unit.test_tribunal_orchestrator import (
    FIXTURE,
    USER,
    CaseFileBuilder,
    FakeLLM,
    FakeRepo,
    FakeService,
    make_settings,
    parse_sse,
)
from app.copilot.structured import StructuredOutputProviderError

OTHER = "u2"
NOW = datetime(2026, 11, 10, 14, 0, tzinfo=timezone.utc)

# SQLite: adattatori espliciti (quelli di default sono deprecati da Python 3.12).
sqlite3.register_adapter(date, lambda d: d.isoformat())
sqlite3.register_adapter(datetime, lambda d: d.isoformat())

_SQLITE_SCHEMA = (
    "create table portfolios (id integer primary key, owner_user_id text not null)",
    """
    create table tribunal_sessions (
      id integer primary key autoincrement,
      owner_user_id text not null,
      scope_fingerprint text not null,
      session_id text not null,
      case_file_hash text not null,
      contract_version text not null,
      prompt_version text not null,
      key_source text not null check (key_source in ('user', 'server')),
      payload text not null,
      created_at timestamp not null,
      completed_at timestamp not null,
      saved_at timestamp not null,
      unique (owner_user_id, scope_fingerprint)
    )
    """,
    """
    create table tribunal_session_members (
      tribunal_session_id integer not null references tribunal_sessions(id) on delete cascade,
      portfolio_id integer not null references portfolios(id) on delete cascade,
      primary key (tribunal_session_id, portfolio_id)
    )
    """,
    """
    create table tribunal_daily_usage (
      owner_user_id text not null,
      usage_day date not null,
      sessions int not null default 0 check (sessions >= 0),
      updated_at timestamp not null,
      primary key (owner_user_id, usage_day)
    )
    """,
    """
    create trigger trg_tribunal_session_members_cleanup
    after delete on tribunal_session_members
    begin
      delete from tribunal_sessions where id = old.tribunal_session_id;
    end
    """,
)


@pytest.fixture()
def engine():
    eng = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})

    @event.listens_for(eng, "connect")
    def _fk(dbapi_conn, _record):  # pragma: no cover - eseguito alla connessione
        dbapi_conn.execute("pragma foreign_keys = on")

    with eng.begin() as conn:
        for ddl in _SQLITE_SCHEMA:
            conn.execute(text(ddl))
        for pid, owner in ((19, USER), (26, USER), (30, USER), (40, OTHER)):
            conn.execute(text("insert into portfolios (id, owner_user_id) values (:id, :o)"), {"id": pid, "o": owner})
    yield eng
    eng.dispose()


@pytest.fixture()
def crypto():
    instance = FieldCrypto(parse_keyring("k1:" + base64.b64encode(os.urandom(32)).decode()),
                           store=MemoryDekStore())
    set_field_crypto(instance)
    yield instance
    set_field_crypto(None)


@pytest.fixture(autouse=True)
def _release_locks():
    yield
    orch_module._LOCKS._active.clear()


def make_session(ids: list[int], *, hash_: str | None = None, completed_at: str = "2026-11-10T14:00:49Z",
                 session_id: str = "trb_5f0c2a9e7d41b386") -> dict[str, Any]:
    session = copy.deepcopy(FIXTURE["session"])
    scope = build_scope(ids).model_dump()
    session["scope"] = scope
    session["case_file"]["scope"] = scope
    if hash_ is not None:
        session["case_file"]["hash"] = hash_
    session["completed_at"] = completed_at
    session["session_id"] = session_id
    return session


def fp(ids: list[int]) -> str:
    return build_scope(ids).fingerprint


def rows(engine, sql: str, **params: Any) -> list[Any]:
    with engine.begin() as conn:
        return conn.execute(text(sql), params).all()


# ---------------------------------------------------------------------------
# Salvataggio e lettura
# ---------------------------------------------------------------------------

def test_save_and_get_latest_round_trip_encrypted_at_rest(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    session = make_session([19])
    store.save(USER, [19], session, key_source="server")

    assert store.get_latest(USER, fp([19])) == session
    (row,) = rows(engine, "select owner_user_id, scope_fingerprint, session_id, case_file_hash, contract_version, "
                          "prompt_version, key_source, payload from tribunal_sessions")
    assert tuple(row[:7]) == (USER, "p:19", session["session_id"], session["case_file"]["hash"],
                              session["contract_version"], session["prompt_version"], "server")
    payload = row[7]
    assert is_encrypted(payload)
    # Nessun contenuto della seduta in chiaro (testi, simboli, hash dentro il payload).
    for needle in (session["arguments"][0]["text"][:20], session["case_file"]["hash"], "VWCE", "arguments"):
        assert needle not in payload
    assert [tuple(r) for r in rows(engine, "select portfolio_id from tribunal_session_members")] == [(19,)]


def test_payload_is_bound_to_owner(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    store.save(USER, [19], make_session([19]), key_source="user")
    # Payload copiato su un altro utente: non si decifra (AAD con owner_user_id) → nessuna seduta.
    with engine.begin() as conn:
        payload = conn.execute(text("select payload from tribunal_sessions")).scalar_one()
        conn.execute(
            text("insert into tribunal_sessions (owner_user_id, scope_fingerprint, session_id, case_file_hash, "
                 "contract_version, prompt_version, key_source, payload, created_at, completed_at, saved_at) "
                 "values (:o, 'p:40', 's', 'h', 'c', 'p', 'user', :p, :t, :t, :t)"),
            {"o": OTHER, "p": payload, "t": NOW},
        )
    assert store.get_latest(OTHER, "p:40") is None
    assert store.get_latest(USER, "p:19") is not None


def test_undecryptable_session_reads_as_absent(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    store.save(USER, [19], make_session([19]), key_source="user")
    crypto.store.rows.clear()          # crypto-shredding della DEK
    crypto.cache.invalidate()
    assert store.get_latest(USER, fp([19])) is None


def test_plaintext_without_keys_is_still_readable(engine):
    set_field_crypto(None)              # dev senza DATA_ENCRYPTION_KEYS: payload in chiaro
    store = TribunalStore(engine, clock=lambda: NOW)
    session = make_session([19, 26])
    store.save(USER, [26, 19], session, key_source="user")
    assert store.get_latest(USER, "p:19,26") == session
    assert not is_encrypted(rows(engine, "select payload from tribunal_sessions")[0][0])


def test_latest_is_per_user_and_exact_scope(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    single = make_session([19], session_id="trb_" + "1" * 16)
    aggregate = make_session([19, 26], session_id="trb_" + "2" * 16)
    store.save(USER, [19], single, key_source="user")
    store.save(USER, [19, 26], aggregate, key_source="user")
    assert store.get_latest(USER, "p:19")["session_id"] == single["session_id"]
    assert store.get_latest(USER, "p:19,26")["session_id"] == aggregate["session_id"]
    assert store.get_latest(USER, "p:26") is None
    assert store.get_latest(OTHER, "p:19") is None


def test_new_session_overwrites_the_previous_one(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    store.save(USER, [19], make_session([19], session_id="trb_" + "1" * 16), key_source="server")
    second = make_session([19], hash_="f" * 64, session_id="trb_" + "2" * 16,
                          completed_at="2026-11-10T15:00:00Z")
    store.save(USER, [19], second, key_source="user")
    assert store.get_latest(USER, "p:19") == second
    assert rows(engine, "select count(*) from tribunal_sessions")[0][0] == 1
    assert rows(engine, "select case_file_hash, key_source from tribunal_sessions")[0] == ("f" * 64, "user")
    assert rows(engine, "select count(*) from tribunal_session_members")[0][0] == 1
    # Il conteggio non segue la sovrascrittura: la prima seduta (server) resta contata.
    assert store.count_today(USER, now=NOW) == 1


def test_invalid_saves_write_nothing(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    with pytest.raises(ValueError):
        store.save(USER, [19], make_session([19]), key_source="other")
    with pytest.raises(ValueError):
        store.save(USER, [26], make_session([19]), key_source="server")     # scope diverso
    broken = make_session([19])
    broken["case_file"].pop("hash")
    with pytest.raises(ValueError):
        store.save(USER, [19], broken, key_source="server")
    assert rows(engine, "select count(*) from tribunal_sessions")[0][0] == 0
    assert store.count_today(USER, now=NOW) == 0


def test_failed_write_rolls_back_session_and_count(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    # Portafoglio inesistente: la FK dei membri fallisce dopo l'upsert della seduta.
    with pytest.raises(Exception):
        store.save(USER, [19, 99], make_session([19, 99]), key_source="server")
    assert rows(engine, "select count(*) from tribunal_sessions")[0][0] == 0
    assert store.count_today(USER, now=NOW) == 0


# ---------------------------------------------------------------------------
# Limite giornaliero
# ---------------------------------------------------------------------------

def test_count_today_counts_only_server_key_sessions_across_scopes(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    store.save(USER, [19], make_session([19]), key_source="server")
    store.save(USER, [19, 26], make_session([19, 26]), key_source="server")
    store.save(USER, [30], make_session([30]), key_source="user")
    store.save(USER, [19], make_session([19]), key_source="server")         # stesso scope, di nuovo
    assert store.count_today(USER, now=NOW) == 3
    assert store.count_today(OTHER, now=NOW) == 0


def test_rome_midnight_boundary(engine, crypto):
    store = TribunalStore(engine)
    # 22:59:59Z del 10 novembre = 23:59:59 a Roma (CET): conta per il 10.
    store.save(USER, [19], make_session([19], completed_at="2026-11-10T22:59:59Z"), key_source="server")
    assert store.count_today(USER, now=datetime(2026, 11, 10, 22, 59, 59, tzinfo=timezone.utc)) == 1
    assert store.count_today(USER, now=datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)) == 1
    # 23:00Z = mezzanotte a Roma: giorno nuovo, contatore a zero.
    assert store.count_today(USER, now=datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)) == 0
    # 23:30Z del 10 = 00:30 dell'11 a Roma: conta per l'11, non per il 10.
    store.save(USER, [26], make_session([26], completed_at="2026-11-10T23:30:00Z"), key_source="server")
    assert store.count_today(USER, now=datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)) == 1
    assert store.count_today(USER, now=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)) == 1
    # Ora legale (CEST, UTC+2): mezzanotte a Roma = 22:00Z.
    store.save(USER, [30], make_session([30], completed_at="2026-07-10T21:59:00Z"), key_source="server")
    assert store.count_today(USER, now=datetime(2026, 7, 10, 21, 59, 59, tzinfo=timezone.utc)) == 1
    assert store.count_today(USER, now=datetime(2026, 7, 10, 22, 0, tzinfo=timezone.utc)) == 0


def test_rome_day_helper():
    assert rome_day(datetime(2026, 11, 10, 22, 59, 59, tzinfo=timezone.utc)) == date(2026, 11, 10)
    assert rome_day(datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)) == date(2026, 11, 11)
    assert rome_day(datetime(2026, 11, 10, 23, 0)) == date(2026, 11, 11)       # naive = UTC


def test_count_today_defaults_to_store_clock_and_old_days_are_pruned(engine, crypto):
    old = NOW - timedelta(days=USAGE_RETENTION_DAYS + 5)
    store = TribunalStore(engine, clock=lambda: old)
    store.save(USER, [19], make_session([19], completed_at=old.strftime("%Y-%m-%dT%H:%M:%SZ")), key_source="server")
    assert store.count_today(USER) == 1
    store = TribunalStore(engine, clock=lambda: NOW)
    assert store.count_today(USER) == 0
    store.save(USER, [19], make_session([19]), key_source="server")
    assert [tuple(r) for r in rows(engine, "select usage_day, sessions from tribunal_daily_usage")] == [
        ("2026-11-10", 1),
    ]


# ---------------------------------------------------------------------------
# Cancellazione
# ---------------------------------------------------------------------------

def test_delete_for_user_removes_sessions_and_usage(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    store.save(USER, [19], make_session([19]), key_source="server")
    store.save(USER, [19, 26], make_session([19, 26]), key_source="server")
    store.save(OTHER, [40], make_session([40]), key_source="server")
    assert store.delete_for_user(USER) == 2
    assert store.get_latest(USER, "p:19") is None and store.get_latest(USER, "p:19,26") is None
    assert store.count_today(USER, now=NOW) == 0
    assert rows(engine, "select count(*) from tribunal_session_members")[0][0] == 1
    assert store.get_latest(OTHER, "p:40") is not None and store.count_today(OTHER, now=NOW) == 1
    assert store.delete_for_user(USER) == 0


def test_deleting_a_portfolio_deletes_single_and_aggregate_sessions(engine, crypto):
    store = TribunalStore(engine, clock=lambda: NOW)
    store.save(USER, [19], make_session([19]), key_source="server")
    store.save(USER, [19, 26], make_session([19, 26]), key_source="server")
    store.save(USER, [26], make_session([26]), key_source="server")
    with engine.begin() as conn:
        conn.execute(text("delete from portfolios where id = 19"))
    assert store.get_latest(USER, "p:19") is None
    assert store.get_latest(USER, "p:19,26") is None
    assert store.get_latest(USER, "p:26") is not None
    assert [tuple(r) for r in rows(engine, "select portfolio_id from tribunal_session_members")] == [(26,)]
    # Il limite del giorno non torna indietro cancellando il portafoglio.
    assert store.count_today(USER, now=NOW) == 3


# ---------------------------------------------------------------------------
# Orchestratore con lo store reale
# ---------------------------------------------------------------------------

class Clock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


def make_orch(store: TribunalStore, *, llm: Any = None, builder: Any = None, clock: Any = None,
              settings: Any = None) -> TribunalOrchestrator:
    service = FakeService()
    return TribunalOrchestrator(
        FakeRepo(), settings or make_settings(), store=store, llm_call=llm or FakeLLM(),
        service_getter=lambda: service, case_file_builder=builder or CaseFileBuilder(),
        clock=clock or (lambda: NOW),
    )


def start(orch: TribunalOrchestrator, ids: list[int] | None = None, **kwargs: Any) -> list[dict[str, Any]]:
    events, _ = parse_sse(orch.start(USER, ids or [19], **kwargs))
    return events


def app_error(fn):
    from app.errors import AppError

    with pytest.raises(AppError) as info:
        fn()
    return info.value


def test_default_store_uses_repo_engine(engine):
    class RepoWithEngine(FakeRepo):
        def __init__(self) -> None:
            super().__init__()
            self.engine = engine

    store = _default_store(RepoWithEngine())
    assert isinstance(store, TribunalStore) and store.engine is engine
    assert isinstance(_default_store(FakeRepo()), NullSessionStore)


def test_live_session_saved_then_reused_without_calling_the_model(engine, crypto):
    store = TribunalStore(engine)
    llm = FakeLLM()
    orch = make_orch(store, llm=llm)
    events = start(orch)
    assert events[-1]["type"] == "done"
    assert events[-1]["content"]["saved"] is True and events[-1]["content"]["reused"] is False
    session_id = events[0]["content"]["session_id"]
    assert store.count_today(USER, now=NOW) == 1
    saved = store.get_latest(USER, "p:19")
    assert saved["session_id"] == session_id and saved["completed_at"] == "2026-11-10T14:00:00Z"

    latest = orch.latest(USER, [19])
    assert latest["session"] == saved
    assert latest["data_changed"] is False
    assert latest["current_case_file_hash"] == saved["case_file"]["hash"]

    calls = len(llm.calls)
    replay = start(orch)
    assert len(llm.calls) == calls                                   # nessuna chiamata al modello
    assert replay[0]["content"]["reused"] is True and replay[0]["content"]["session_id"] == session_id
    assert replay[-1]["content"]["saved"] is False and replay[-1]["content"]["reused"] is True
    assert store.count_today(USER, now=NOW) == 1                      # la riproduzione non conta

    # «Rifai la seduta»: nuova seduta dal vivo che sovrascrive e conta.
    redo = start(orch, force_new=True)
    assert redo[0]["content"]["reused"] is False and redo[-1]["content"]["saved"] is True
    assert store.get_latest(USER, "p:19")["session_id"] == redo[0]["content"]["session_id"] != session_id
    assert store.count_today(USER, now=NOW) == 2


def test_changed_data_marks_latest_and_runs_a_new_session(engine, crypto):
    store = TribunalStore(engine)
    start(make_orch(store))
    changed = CaseFileBuilder({**FIXTURE["session"]["case_file"], "hash": "e" * 64})
    llm = FakeLLM()
    orch = make_orch(store, llm=llm, builder=changed)
    latest = orch.latest(USER, [19])
    assert latest["data_changed"] is True and latest["current_case_file_hash"] == "e" * 64
    events = start(orch)
    assert llm.calls and events[0]["content"]["reused"] is False and events[-1]["content"]["saved"] is True
    assert store.get_latest(USER, "p:19")["case_file"]["hash"] == "e" * 64
    assert orch.latest(USER, [19])["data_changed"] is False


def test_latest_without_saved_session(engine, crypto):
    orch = make_orch(TribunalStore(engine))
    assert orch.latest(USER, [19]) == {"session": None, "current_case_file_hash": None, "data_changed": None}


def test_daily_limit_with_server_key_and_rome_midnight(engine, crypto):
    store = TribunalStore(engine)
    clock = Clock(datetime(2026, 11, 10, 22, 0, tzinfo=timezone.utc))
    orch = make_orch(store, clock=clock, settings=make_settings(doctor_tribunal_daily_limit=2))
    assert start(orch, [19])[-1]["content"]["saved"] is True
    assert start(orch, [26])[-1]["content"]["saved"] is True
    assert orch.status(USER, [19])["limit"]["remaining"] == 0

    clock.now = datetime(2026, 11, 10, 22, 59, 59, tzinfo=timezone.utc)
    err = app_error(lambda: orch.start(USER, [19], force_new=True))
    assert (err.status_code, err.code) == (429, "daily_limit_reached")
    assert err.details["used_today"] == 2 and err.details["resets_at"] == "2026-11-10T23:00:00Z"
    assert err.headers["Retry-After"] == "1"
    # A limite esaurito la seduta salvata con fascicolo invariato si riproduce comunque.
    assert start(orch, [19])[0]["content"]["reused"] is True

    clock.now = datetime(2026, 11, 10, 23, 0, tzinfo=timezone.utc)   # mezzanotte a Roma
    assert orch.status(USER, [19])["limit"]["used_today"] == 0
    assert start(orch, [19], force_new=True)[-1]["content"]["saved"] is True
    assert store.count_today(USER, now=clock.now) == 1


def test_own_key_sessions_are_saved_but_not_counted(engine, crypto):
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    enc = Fernet(key.encode()).encrypt(b"sk-user").decode()
    store = TribunalStore(engine)
    service = FakeService()
    orch = TribunalOrchestrator(
        FakeRepo(provider="anthropic", model="claude-x", key_enc=enc),
        make_settings(copilot_encryption_key=key, doctor_tribunal_daily_limit=0),
        store=store, llm_call=FakeLLM(), service_getter=lambda: service,
        case_file_builder=CaseFileBuilder(), clock=lambda: NOW,
    )
    for _ in range(2):
        assert start(orch, force_new=True)[-1]["content"]["saved"] is True
    assert store.count_today(USER, now=NOW) == 0
    assert rows(engine, "select key_source from tribunal_sessions")[0][0] == "user"


def test_failed_session_is_not_saved_and_not_counted(engine, crypto):
    store = TribunalStore(engine)
    bad = {"arguments": [{"theme": "costi", "stance": "neutro", "text": "Testo senza fatti validi qui.",
                          "fact_ids": []}]}
    llm = FakeLLM(behaviour={
        ("apertura", "prudente"): bad,
        ("apertura", "fattoriale"): StructuredOutputProviderError("x", provider="openai"),
    })
    events = start(make_orch(store, llm=llm))
    assert events[-1]["type"] == "error"
    synth_fail = FakeLLM(behaviour={("sintesi", "sintesi"): StructuredOutputProviderError("x", provider="openai")})
    assert start(make_orch(store, llm=synth_fail))[-1]["type"] == "error"
    assert store.get_latest(USER, "p:19") is None and store.count_today(USER, now=NOW) == 0
    assert rows(engine, "select count(*) from tribunal_sessions")[0][0] == 0


def test_interrupted_session_is_not_saved_and_not_counted(engine, crypto):
    store = TribunalStore(engine)
    stream = make_orch(store).start(USER, [19])
    next(stream)                     # evento session, poi il client si disconnette
    stream.close()
    assert store.get_latest(USER, "p:19") is None and store.count_today(USER, now=NOW) == 0


def test_save_failure_still_delivers_the_session(engine, crypto):
    with engine.begin() as conn:
        conn.execute(text("drop table tribunal_session_members"))
    store = TribunalStore(engine)
    events = start(make_orch(store))
    assert events[-1]["type"] == "done" and events[-1]["content"]["saved"] is False
    assert rows(engine, "select count(*) from tribunal_sessions")[0][0] == 0      # rollback completo
