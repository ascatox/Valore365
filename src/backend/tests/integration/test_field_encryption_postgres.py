"""TASK-57: field-level encryption against a real PostgreSQL 16 (throwaway cluster).

Runs the real PortfolioRepository, DoctorPolicyStore, app user sync and the
backfill on database/schema.sql + migrations with encryption turned on, and
checks that the columns are stored encrypted while the reads return plaintext.
Skipped when the Postgres binaries are missing (see conftest.py).
"""

from __future__ import annotations

import base64
import os
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

import app.auth as auth
from app.crypto import (
    FieldCrypto,
    KeyUnavailableError,
    is_encrypted,
    parse_keyring,
    set_field_crypto,
    shred_user_keys,
)
from app.crypto.backfill import backfill_all
from app.models import PortfolioCloneRequest, PortfolioCreate, PortfolioUpdate, TransactionCreate, TransactionUpdate
from app.repository import PortfolioRepository
from app.services.doctor_policy.store import DoctorPolicyStore

OLD_KEY = base64.b64encode(os.urandom(32)).decode()
NEW_KEY = base64.b64encode(os.urandom(32)).decode()
BIDX_KEY = base64.b64decode(base64.b64encode(os.urandom(32)))


@pytest.fixture()
def crypto():
    instance = FieldCrypto(parse_keyring(f"k1:{OLD_KEY}"), BIDX_KEY)
    set_field_crypto(instance)
    yield instance
    set_field_crypto(None)


@pytest.fixture()
def repo(pg_engine):
    return PortfolioRepository(pg_engine)


def _scalar(engine, sql, **params):
    with engine.begin() as conn:
        return conn.execute(text(sql), params).scalar_one()


def _new_portfolio(repo, user, name="Pensione"):
    return repo.create_portfolio(PortfolioCreate(name=name, base_currency="EUR", timezone="Europe/Rome"), user)


def test_portfolio_name_is_encrypted_and_read_back(pg_engine, repo, crypto):
    user = "fe_user_portfolio"
    created = _new_portfolio(repo, user, "Pensione Mario")
    assert created.name == "Pensione Mario"
    stored = _scalar(pg_engine, "select name from portfolios where id = :id", id=created.id)
    assert is_encrypted(stored) and "Mario" not in stored

    assert [p.name for p in repo.list_portfolios(user)] == ["Pensione Mario"]
    updated = repo.update_portfolio(created.id, PortfolioUpdate(name="Casa"), user)
    assert updated.name == "Casa"
    assert is_encrypted(_scalar(pg_engine, "select name from portfolios where id = :id", id=created.id))

    clone = repo.clone_portfolio(created.id, PortfolioCloneRequest(), user).portfolio
    assert clone.name == "Casa (Copia)"
    assert sorted(p.name for p in repo.list_portfolios(user)) == ["Casa", "Casa (Copia)"]


def test_transaction_notes_are_encrypted_and_read_back(pg_engine, repo, crypto):
    user = "fe_user_tx"
    portfolio = _new_portfolio(repo, user, "Liquidità")
    other = _new_portfolio(repo, user, "Secondo")
    tx = repo.create_transaction(
        TransactionCreate(
            portfolio_id=portfolio.id, side="deposit", trade_at=datetime(2026, 1, 5, tzinfo=timezone.utc),
            quantity=1000, price=1, trade_currency="EUR", notes="Bonifico stipendio",
        ),
        user,
    )
    assert tx.notes == "Bonifico stipendio"
    stored = _scalar(pg_engine, "select notes from transactions where id = :id", id=tx.id)
    assert is_encrypted(stored) and "stipendio" not in stored

    assert [t.notes for t in repo.list_transactions(portfolio.id, user)] == ["Bonifico stipendio"]
    multi = repo.list_transactions_multi([portfolio.id, other.id], user)
    assert [(t.notes, t.portfolio_name) for t in multi] == [("Bonifico stipendio", "Liquidità")]
    assert [t.notes for t in repo.get_transactions_in_range(portfolio.id, user)] == ["Bonifico stipendio"]
    cash = repo.get_computed_cash_balance(portfolio.id, user)
    assert [m.notes for m in cash.recent_movements] == ["Bonifico stipendio"]


def test_transaction_notes_update(pg_engine, repo, crypto):
    user = "fe_user_tx_update"
    portfolio = _new_portfolio(repo, user)
    with pg_engine.begin() as conn:
        asset_id = conn.execute(
            text(
                "insert into assets (symbol, name, asset_type, exchange_code, quote_currency) "
                "values ('FEAST', 'FE asset', 'stock', 'XMIL', 'EUR') returning id"
            )
        ).scalar_one()
    tx = repo.create_transaction(
        TransactionCreate(
            portfolio_id=portfolio.id, asset_id=asset_id, side="buy",
            trade_at=datetime(2026, 1, 5, tzinfo=timezone.utc), quantity=1, price=10, trade_currency="EUR",
        ),
        user,
    )
    assert tx.notes is None
    assert _scalar(pg_engine, "select notes from transactions where id = :id", id=tx.id) is None
    updated = repo.update_transaction(tx.id, TransactionUpdate(notes="comprato per test"), user)
    assert updated.notes == "comprato per test"
    assert is_encrypted(_scalar(pg_engine, "select notes from transactions where id = :id", id=tx.id))


def test_csv_batch_is_encrypted_and_duplicate_detection_still_works(pg_engine, repo, crypto):
    user = "fe_user_csv"
    portfolio = _new_portfolio(repo, user)
    preview = {"rows": [{"row_number": 1, "notes": "riga"}], "source_sha256": "sha-abc"}
    batch_id = repo.create_csv_import_batch(
        portfolio_id=portfolio.id, user_id=user, filename="movimenti_2026.csv",
        total_rows=1, valid_rows=1, error_rows=0, preview_data=preview,
    )
    with pg_engine.begin() as conn:
        row = conn.execute(
            text(
                "select original_filename, original_filename_bidx, source_sha256, preview_data "
                "from csv_import_batches where id = :id"
            ),
            {"id": batch_id},
        ).mappings().one()
    assert is_encrypted(row["original_filename"]) and "movimenti" not in row["original_filename"]
    assert row["original_filename_bidx"] and row["source_sha256"] == "sha-abc"
    assert set(row["preview_data"]) == {"_enc"} and "riga" not in str(row["preview_data"])

    batch = repo.get_csv_import_batch(batch_id, user)
    assert batch["original_filename"] == "movimenti_2026.csv"
    assert batch["preview_data"] == preview

    with pg_engine.begin() as conn:
        conn.execute(text("update csv_import_batches set status = 'committed', committed_at = now() where id = :id"),
                     {"id": batch_id})
        # A legacy batch written before the migration: plaintext, no blind index, hash only in the jsonb.
        conn.execute(
            text(
                "insert into csv_import_batches (portfolio_id, owner_user_id, status, original_filename, preview_data, committed_at) "
                "values (:p, :u, 'committed', 'vecchio.csv', cast(:pd as jsonb), now() - interval '1 day')"
            ),
            {"p": portfolio.id, "u": user, "pd": '{"rows": [], "source_sha256": "sha-old"}'},
        )

    by_name = repo.find_committed_csv_import_batches(portfolio.id, user, "movimenti_2026.csv", "sha-other")
    assert [(b["id"], b["original_filename"], b["same_content"]) for b in by_name] == [
        (batch_id, "movimenti_2026.csv", False)
    ]
    by_hash = repo.find_committed_csv_import_batches(portfolio.id, user, "rinominato.csv", "sha-abc")
    assert [(b["id"], b["same_content"]) for b in by_hash] == [(batch_id, True)]
    legacy_by_name = repo.find_committed_csv_import_batches(portfolio.id, user, "vecchio.csv", None)
    assert [b["original_filename"] for b in legacy_by_name] == ["vecchio.csv"]
    assert repo.find_committed_csv_import_batches(portfolio.id, user, "altro.csv", "sha-none") == []
    assert repo.find_committed_csv_import_batches(portfolio.id, "someone_else", "movimenti_2026.csv", "sha-abc") == []


def test_doctor_policy_name_is_encrypted(pg_engine, crypto):
    user = "fe_user_doctor"
    store = DoctorPolicyStore(pg_engine)
    record = store.save_version(
        owner_user_id=user, scope_type="single", scope_fingerprint="p:999001", portfolio_ids=[999001],
        name="Piano pensione", document={"schema_version": 1, "rules": []}, document_hash="h1",
        schema_version=1, source="manual", base_version=None, diff=[],
    )
    assert record.name == "Piano pensione"
    stored = _scalar(pg_engine, "select name from doctor_policy_sets where id = :id", id=record.id)
    assert is_encrypted(stored)
    again = store.save_version(
        owner_user_id=user, scope_type="single", scope_fingerprint="p:999001", portfolio_ids=[999001],
        name=None, document={"schema_version": 1, "rules": []}, document_hash="h2",
        schema_version=1, source="manual", base_version=1, diff=[],
    )
    assert again.name == "Piano pensione"  # name kept when the save does not change it
    assert store.get_policy_set(user, "p:999001").name == "Piano pensione"


def test_app_user_email_is_encrypted_with_blind_index(pg_engine, crypto, monkeypatch):
    user = "fe_user_email"
    monkeypatch.setattr(auth, "engine", pg_engine)
    with auth._app_user_sync_lock:
        auth._app_user_synced_at.pop(user, None)
    auth._sync_app_user(user, "Mario.Rossi@Example.com", None)
    with pg_engine.begin() as conn:
        row = conn.execute(text("select email, email_bidx from app_users where user_id = :u"), {"u": user}).mappings().one()
        assert is_encrypted(row["email"]) and "rossi" not in row["email"].lower()
        assert crypto.decrypt(conn, "app_users", "email", user, row["email"]) == "Mario.Rossi@Example.com"
        found = conn.execute(
            text("select user_id from app_users where email_bidx = :b"),
            {"b": crypto.email_blind_index(" mario.rossi@example.COM ")},
        ).scalars().all()
    assert found == [user]


def test_dek_survives_rollback_of_the_first_write(pg_engine, crypto):
    user = "fe_user_rollback"
    with pytest.raises(RuntimeError):
        with pg_engine.begin() as conn:
            token = crypto.encrypt(conn, "portfolios", "name", user, "x")
            raise RuntimeError("rollback")
    # The DEK was committed on its own: the cached copy is backed by a stored row.
    assert _scalar(pg_engine, "select count(*) from user_data_keys where user_id = :u", u=user) == 1
    crypto.invalidate()
    with pg_engine.begin() as conn:
        assert crypto.decrypt(conn, "portfolios", "name", user, token) == "x"


def test_crypto_shredding_makes_the_users_data_unreadable(pg_engine, repo, crypto):
    user, other = "fe_user_shred", "fe_user_keep"
    _new_portfolio(repo, user, "Da dimenticare")
    _new_portfolio(repo, other, "Da tenere")
    with pg_engine.begin() as conn:
        assert shred_user_keys(conn, user) is True
    with pytest.raises(KeyUnavailableError):
        repo.list_portfolios(user)
    assert [p.name for p in repo.list_portfolios(other)] == ["Da tenere"]


def test_backfill_encrypts_legacy_rows_idempotently(pg_engine, repo, crypto):
    user = "fe_user_legacy"
    with pg_engine.begin() as conn:
        pid = conn.execute(
            text("insert into portfolios (name, base_currency, owner_user_id) values ('Legacy', 'EUR', :u) returning id"),
            {"u": user},
        ).scalar_one()
        conn.execute(
            text(
                "insert into transactions (portfolio_id, side, trade_at, quantity, price, trade_currency, notes, owner_user_id) "
                "values (:p, 'deposit', now(), 10, 1, 'EUR', 'nota legacy', :u)"
            ),
            {"p": pid, "u": user},
        )
        conn.execute(
            text(
                "insert into csv_import_batches (portfolio_id, owner_user_id, original_filename, preview_data) "
                "values (:p, :u, 'legacy.csv', cast(:pd as jsonb))"
            ),
            {"p": pid, "u": user, "pd": '{"rows": [{"row_number": 1}], "source_sha256": "sha-legacy"}'},
        )
        conn.execute(
            text("insert into app_users (user_id, email) values (:u, 'Legacy@Example.com')"),
            {"u": user},
        )
    tables = {"portfolios", "transactions", "csv_import_batches", "app_users", "doctor_policy_sets"}

    dry = {r.table: r for r in backfill_all(crypto, pg_engine.begin, batch_size=2, dry_run=True, tables=tables)}
    assert dry["portfolios"].updated >= 1 and dry["transactions"].updated >= 1
    assert _scalar(pg_engine, "select name from portfolios where id = :id", id=pid) == "Legacy"
    assert _scalar(pg_engine, "select count(*) from user_data_keys where user_id = :u", u=user) == 0

    first = {r.table: r for r in backfill_all(crypto, pg_engine.begin, batch_size=2, tables=tables)}
    assert all(not r.failed for r in first.values()), {t: r.failed for t, r in first.items()}
    with pg_engine.begin() as conn:
        row = conn.execute(
            text(
                "select p.name, t.notes, b.original_filename, b.original_filename_bidx, b.source_sha256, b.preview_data, "
                "u.email, u.email_bidx "
                "from portfolios p join transactions t on t.portfolio_id = p.id "
                "join csv_import_batches b on b.portfolio_id = p.id join app_users u on u.user_id = p.owner_user_id "
                "where p.id = :id"
            ),
            {"id": pid},
        ).mappings().one()
    assert all(is_encrypted(row[c]) for c in ("name", "notes", "original_filename", "email"))
    assert set(row["preview_data"]) == {"_enc"}
    assert row["source_sha256"] == "sha-legacy"
    assert row["original_filename_bidx"] == crypto.csv_filename_blind_index("legacy.csv")
    assert row["email_bidx"] == crypto.email_blind_index("legacy@example.com")

    second = backfill_all(crypto, pg_engine.begin, batch_size=2, tables=tables)
    assert sum(r.updated for r in second) == 0

    assert [p.name for p in repo.list_portfolios(user)] == ["Legacy"]
    assert [t.notes for t in repo.list_transactions(pid, user)] == ["nota legacy"]


def test_kek_rotation_rewraps_stored_deks(pg_engine, repo, crypto):
    user = "fe_user_rotation"
    created = _new_portfolio(repo, user, "Ruotato")
    assert _scalar(pg_engine, "select kek_id from user_data_keys where user_id = :u", u=user) == "k1"

    rotated = FieldCrypto(parse_keyring(f"k2:{NEW_KEY},k1:{OLD_KEY}"), BIDX_KEY)
    result = rotated.rewrap_all(pg_engine.begin, batch_size=1)
    assert not result.failed and result.rewrapped >= 1
    assert _scalar(pg_engine, "select kek_id from user_data_keys where user_id = :u", u=user) == "k2"
    assert _scalar(pg_engine, "select count(*) from user_data_keys where kek_id <> 'k2'") == 0

    # Old KEK removed: the data (never re-encrypted) is still readable.
    set_field_crypto(FieldCrypto(parse_keyring(f"k2:{NEW_KEY}"), BIDX_KEY))
    assert [p.name for p in repo.list_portfolios(user) if p.id == created.id] == ["Ruotato"]
