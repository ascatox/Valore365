"""TASK-57: field-level envelope encryption (app/crypto)."""

from __future__ import annotations

import base64
import os

import pytest

from app.config import Settings
from app.crypto import (
    CryptoConfigError,
    DecryptionError,
    DekCache,
    FieldCrypto,
    KeyUnavailableError,
    build_field_crypto,
    is_encrypted,
    normalize_email,
    parse_keyring,
)
from app.crypto.dek_store import WrappedDek
from app.crypto.keyring import DEV_BLIND_INDEX_KEY


def _key() -> str:
    return base64.b64encode(os.urandom(32)).decode()


class MemoryDekStore:
    """In-memory user_data_keys (the conn argument is ignored)."""

    def __init__(self) -> None:
        self.rows: dict[str, WrappedDek] = {}
        self.creates = 0

    def get(self, conn, user_id):
        return self.rows.get(user_id)

    def create_if_absent(self, conn, user_id, kek_id, wrapped_dek):
        self.creates += 1
        self.rows.setdefault(user_id, WrappedDek(user_id, kek_id, wrapped_dek))
        return self.rows[user_id]

    def delete(self, conn, user_id):
        return self.rows.pop(user_id, None) is not None

    def list_not_wrapped_with(self, conn, kek_id, *, after_user_id, limit):
        rows = sorted((r for r in self.rows.values() if r.kek_id != kek_id), key=lambda r: r.user_id)
        if after_user_id is not None:
            rows = [r for r in rows if r.user_id > after_user_id]
        return rows[:limit]

    def rewrap(self, conn, user_id, *, old_kek_id, kek_id, wrapped_dek):
        current = self.rows.get(user_id)
        if current is None or current.kek_id != old_kek_id:
            return False
        self.rows[user_id] = WrappedDek(user_id, kek_id, wrapped_dek)
        return True


class _Tx:
    def __enter__(self):
        return None

    def __exit__(self, *exc):
        return False


def _crypto(keys: str, store: MemoryDekStore | None = None, **kw) -> FieldCrypto:
    return FieldCrypto(parse_keyring(keys), None, store=store or MemoryDekStore(), **kw)


@pytest.fixture()
def crypto():
    return _crypto(f"k1:{_key()}")


def test_round_trip(crypto):
    token = crypto.encrypt(None, "portfolios", "name", "user_a", "Pensione ✓")
    assert is_encrypted(token) and token.startswith("enc:v1:")
    assert "Pensione" not in token
    assert crypto.decrypt(None, "portfolios", "name", "user_a", token) == "Pensione ✓"


def test_same_plaintext_gives_different_tokens(crypto):
    a = crypto.encrypt(None, "transactions", "notes", "user_a", "x")
    b = crypto.encrypt(None, "transactions", "notes", "user_a", "x")
    assert a != b


def test_none_and_empty_values(crypto):
    assert crypto.encrypt(None, "transactions", "notes", "user_a", None) is None
    assert crypto.decrypt(None, "transactions", "notes", "user_a", None) is None
    token = crypto.encrypt(None, "transactions", "notes", "user_a", "")
    assert crypto.decrypt(None, "transactions", "notes", "user_a", token) == ""


def test_value_that_looks_like_a_token_is_still_encrypted(crypto):
    token = crypto.encrypt(None, "portfolios", "name", "user_a", "enc:v1:abc")
    assert token != "enc:v1:abc"
    assert crypto.decrypt(None, "portfolios", "name", "user_a", token) == "enc:v1:abc"


@pytest.mark.parametrize(
    "table, column",
    [("portfolios", "notes"), ("transactions", "name")],
)
def test_wrong_aad_table_or_column_fails(crypto, table, column):
    token = crypto.encrypt(None, "portfolios", "name", "user_a", "secret")
    with pytest.raises(DecryptionError):
        crypto.decrypt(None, table, column, "user_a", token)


def test_token_copied_to_another_user_fails(crypto):
    token = crypto.encrypt(None, "portfolios", "name", "user_a", "secret")
    crypto.encrypt(None, "portfolios", "name", "user_b", "other")  # user_b has a DEK too
    with pytest.raises(DecryptionError):
        crypto.decrypt(None, "portfolios", "name", "user_b", token)


def test_other_users_dek_cannot_decrypt(crypto):
    """Even with the right AAD, user_b's DEK does not open user_a's ciphertext."""
    token = crypto.encrypt(None, "portfolios", "name", "user_a", "secret")
    crypto.encrypt(None, "portfolios", "name", "user_b", "other")
    store = crypto.store
    store.rows["user_a"] = WrappedDek("user_a", store.rows["user_b"].kek_id, store.rows["user_b"].wrapped_dek)
    crypto.invalidate()
    # The swapped wrapped DEK carries AAD dek:user_b, so unwrapping it for user_a fails.
    with pytest.raises(DecryptionError):
        crypto.decrypt(None, "portfolios", "name", "user_a", token)


def test_tampered_token_fails(crypto):
    token = crypto.encrypt(None, "portfolios", "name", "user_a", "secret")
    body = bytearray(base64.urlsafe_b64decode(token[len("enc:v1:"):] + "=="))
    body[-1] ^= 1
    tampered = "enc:v1:" + base64.urlsafe_b64encode(bytes(body)).rstrip(b"=").decode()
    with pytest.raises(DecryptionError):
        crypto.decrypt(None, "portfolios", "name", "user_a", tampered)
    with pytest.raises(DecryptionError):
        crypto.decrypt(None, "portfolios", "name", "user_a", "enc:v1:@@not-base64@@")


def test_legacy_plaintext_passes_through(crypto):
    assert crypto.decrypt(None, "portfolios", "name", "user_a", "Portafoglio 2024") == "Portafoglio 2024"
    assert crypto.decrypt_json(None, "csv_import_batches", "preview_data", "user_a", [{"a": 1}]) == [{"a": 1}]
    legacy = {"rows": [], "source_sha256": "abc"}
    assert crypto.decrypt_json(None, "csv_import_batches", "preview_data", "user_a", legacy) == legacy
    # Reading plaintext never needs (or creates) a DEK.
    assert crypto.store.rows == {}


def test_json_round_trip(crypto):
    value = {"rows": [{"row_number": 1, "notes": "è"}], "source_sha256": "f00"}
    stored = crypto.encrypt_json(None, "csv_import_batches", "preview_data", "user_a", value)
    assert set(stored) == {"_enc"} and is_encrypted(stored["_enc"])
    assert crypto.decrypt_json(None, "csv_import_batches", "preview_data", "user_a", stored) == value


def test_dek_created_once_and_cached(crypto):
    crypto.encrypt(None, "portfolios", "name", "user_a", "a")
    crypto.encrypt(None, "portfolios", "name", "user_a", "b")
    assert crypto.store.creates == 1
    assert len(crypto.cache) == 1


def test_decrypt_does_not_create_a_dek(crypto):
    token = crypto.encrypt(None, "portfolios", "name", "user_a", "a")
    other = _crypto(f"k1:{_key()}")
    with pytest.raises(KeyUnavailableError):
        other.decrypt(None, "portfolios", "name", "user_a", token)
    assert other.store.rows == {}


def test_crypto_shred_makes_data_unreadable(crypto):
    token = crypto.encrypt(None, "transactions", "notes", "user_a", "nota personale")
    keep = crypto.encrypt(None, "transactions", "notes", "user_b", "altra nota")
    assert crypto.shred_user(None, "user_a") is True
    with pytest.raises(KeyUnavailableError):
        crypto.decrypt(None, "transactions", "notes", "user_a", token)
    assert crypto.decrypt(None, "transactions", "notes", "user_b", keep) == "altra nota"
    assert crypto.shred_user(None, "user_a") is False


def test_kek_rotation_old_kid_still_unwraps_and_rewrap_moves_to_active():
    old_key, new_key = _key(), _key()
    store = MemoryDekStore()
    before = _crypto(f"old:{old_key}", store)
    token = before.encrypt(None, "portfolios", "name", "user_a", "Pensione")
    before.encrypt(None, "portfolios", "name", "user_b", "Casa")
    assert {r.kek_id for r in store.rows.values()} == {"old"}

    rotated = _crypto(f"new:{new_key},old:{old_key}", store)
    # DEKs wrapped with the old KEK still unwrap.
    assert rotated.decrypt(None, "portfolios", "name", "user_a", token) == "Pensione"
    # New DEKs are wrapped with the active (first) KEK.
    rotated.encrypt(None, "portfolios", "name", "user_c", "Nuovo")
    assert store.rows["user_c"].kek_id == "new"

    dry = rotated.rewrap_all(_Tx, batch_size=1, dry_run=True)
    assert (dry.scanned, dry.rewrapped, dry.failed) == (2, 2, [])
    assert {store.rows[u].kek_id for u in ("user_a", "user_b")} == {"old"}

    result = rotated.rewrap_all(_Tx, batch_size=1)
    assert (result.scanned, result.rewrapped, result.failed) == (2, 2, [])
    assert {r.kek_id for r in store.rows.values()} == {"new"}

    # The old KEK can now be dropped: data is unchanged and still readable.
    only_new = _crypto(f"new:{new_key}", store)
    assert only_new.decrypt(None, "portfolios", "name", "user_a", token) == "Pensione"


def test_unknown_kek_id_is_key_unavailable():
    store = MemoryDekStore()
    token = _crypto(f"old:{_key()}", store).encrypt(None, "portfolios", "name", "user_a", "x")
    with pytest.raises(KeyUnavailableError):
        _crypto(f"new:{_key()}", store).decrypt(None, "portfolios", "name", "user_a", token)


def test_rewrap_reports_dek_that_cannot_be_unwrapped():
    store = MemoryDekStore()
    _crypto(f"lost:{_key()}", store).encrypt(None, "portfolios", "name", "user_a", "x")
    result = _crypto(f"new:{_key()}", store).rewrap_all(_Tx)
    assert result.failed == ["user_a"] and result.rewrapped == 0


def test_disabled_crypto_keeps_plaintext_and_refuses_tokens():
    enabled = _crypto(f"k1:{_key()}")
    token = enabled.encrypt(None, "portfolios", "name", "user_a", "x")
    disabled = FieldCrypto(None, None, store=MemoryDekStore())
    assert disabled.enabled is False
    assert disabled.encrypt(None, "portfolios", "name", "user_a", "x") == "x"
    assert disabled.encrypt_json(None, "csv_import_batches", "preview_data", "user_a", {"a": 1}) == {"a": 1}
    with pytest.raises(KeyUnavailableError):
        disabled.decrypt(None, "portfolios", "name", "user_a", token)


def test_owner_is_required(crypto):
    with pytest.raises(ValueError):
        crypto.encrypt(None, "portfolios", "name", "", "x")


def test_blind_index_normalizes_email(crypto):
    assert normalize_email("  Mario.Rossi@Example.COM ") == "mario.rossi@example.com"
    a = crypto.email_blind_index("  Mario.Rossi@Example.COM ")
    assert a == crypto.email_blind_index("mario.rossi@example.com")
    assert a != crypto.email_blind_index("mario.rossi@example.org")
    assert len(a) == 64 and "mario" not in a
    assert crypto.email_blind_index(None) is None
    assert crypto.email_blind_index("   ") is None


def test_blind_index_is_keyed_and_domain_separated():
    k1 = base64.b64decode(_key())
    a = FieldCrypto(None, k1)
    b = FieldCrypto(None, base64.b64decode(_key()))
    assert a.blind_index("x", purpose="p") != b.blind_index("x", purpose="p")
    assert a.blind_index("x", purpose="p") != a.blind_index("x", purpose="q")
    # File names are matched exactly (no normalization), like the old SQL "=".
    assert a.csv_filename_blind_index("Export.csv") != a.csv_filename_blind_index("export.csv")
    # Without a key the deterministic dev key keeps lookups working.
    dev1, dev2 = FieldCrypto(None, None), FieldCrypto(None, None)
    assert dev1.blind_index("x", purpose="p") == dev2.blind_index("x", purpose="p")
    assert dev1._bidx_key == DEV_BLIND_INDEX_KEY


def test_dek_cache_lru_and_ttl():
    clock = {"now": 0.0}
    cache = DekCache(max_entries=2, ttl_seconds=10, clock=lambda: clock["now"])
    cache.put("a", b"A")
    cache.put("b", b"B")
    assert cache.get("a") == b"A"  # a is now most recent
    cache.put("c", b"C")  # evicts b
    assert cache.get("b") is None and cache.get("a") == b"A" and cache.get("c") == b"C"
    clock["now"] = 11
    assert cache.get("a") is None
    cache.put("d", b"D")
    cache.invalidate("d")
    assert cache.get("d") is None
    cache.put("e", b"E")
    cache.invalidate()
    assert len(cache) == 0


@pytest.mark.parametrize(
    "raw",
    [
        "nokid",
        ":abc",
        "k1:not-base64!!",
        f"k1:{base64.b64encode(os.urandom(16)).decode()}",
        "k1:{0},k1:{0}".format(base64.b64encode(os.urandom(32)).decode()),
        f"bad kid:{base64.b64encode(os.urandom(32)).decode()}",
    ],
)
def test_keyring_rejects_malformed_values(raw):
    with pytest.raises(CryptoConfigError):
        parse_keyring(raw)


def test_keyring_order_and_urlsafe_keys():
    raw_new = os.urandom(32)
    ring = parse_keyring(f" new:{base64.urlsafe_b64encode(raw_new).decode().rstrip('=')} , old:{_key()} ")
    assert ring.active_kid == "new" and ring.active_key == raw_new
    assert ring.kids == ("new", "old")
    assert parse_keyring("") is None and parse_keyring(" , ") is None


def test_prod_startup_requires_keys():
    with pytest.raises(CryptoConfigError, match="DATA_ENCRYPTION_KEYS"):
        build_field_crypto(Settings(app_env="prod", data_encryption_keys="", data_blind_index_key=_key()))
    with pytest.raises(CryptoConfigError, match="DATA_BLIND_INDEX_KEY"):
        build_field_crypto(Settings(app_env="production", data_encryption_keys=f"k1:{_key()}", data_blind_index_key=""))
    crypto = build_field_crypto(
        Settings(app_env="prod", data_encryption_keys=f"k1:{_key()}", data_blind_index_key=_key())
    )
    assert crypto.enabled


def test_dev_without_keys_starts_in_plaintext_mode(caplog):
    with caplog.at_level("WARNING"):
        crypto = build_field_crypto(Settings(app_env="dev", data_encryption_keys="", data_blind_index_key=""))
    assert crypto.enabled is False
    assert "DATA_ENCRYPTION_KEYS" in caplog.text
    with pytest.raises(CryptoConfigError):
        build_field_crypto(Settings(app_env="dev", data_encryption_keys="k1:short"))


def test_lifespan_refuses_to_start_in_prod_without_keys(monkeypatch):
    import asyncio

    import app.main as api_main

    monkeypatch.setattr(
        api_main,
        "settings",
        Settings(app_env="prod", clerk_auth_enabled=True, data_encryption_keys="", data_blind_index_key=""),
    )
    monkeypatch.setattr(api_main, "_apply_pending_migrations", lambda: pytest.fail("must not get this far"))

    async def run():
        async with api_main.lifespan(api_main.app):
            pass

    with pytest.raises(RuntimeError, match="DATA_ENCRYPTION_KEYS"):
        asyncio.run(run())
