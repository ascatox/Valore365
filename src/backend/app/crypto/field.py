"""Field-level envelope encryption of personal data (TASK-57, docs/field-encryption.md).

- Every user has a random 256-bit DEK, stored wrapped (AES-256-GCM) with the
  active KEK of ``DATA_ENCRYPTION_KEYS`` in ``user_data_keys`` (AAD
  ``dek:<user_id>``). Deleting that row crypto-shreds the user's data.
- A field value is encrypted with AES-256-GCM under the owner's DEK, a random
  12-byte nonce and AAD ``<table>:<column>:<owner_user_id>``, so a ciphertext
  copied to another column or user does not decrypt. It is stored as text
  ``enc:v1:<base64url(nonce || ciphertext)>``; jsonb columns store
  ``{"_enc": "<token>"}``.
- A value without the prefix is legacy plaintext and is returned unchanged,
  so data written before the migration stays readable until the backfill
  (scripts/encrypt_existing_data.py) encrypts it.
- Blind indexes are HMAC-SHA256 with ``DATA_BLIND_INDEX_KEY``, domain separated
  per column, for the columns looked up by equality.
- Without ``DATA_ENCRYPTION_KEYS`` (dev/test only: production refuses to
  start) writes stay plaintext and blind indexes use a fixed dev key.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from .dek_store import DekStore, SqlDekStore, WrappedDek
from .errors import CryptoConfigError, DecryptionError, KeyUnavailableError
from .keyring import DEV_BLIND_INDEX_KEY, KeyRing, parse_blind_index_key, parse_keyring

logger = logging.getLogger(__name__)

ENC_PREFIX = "enc:v1:"
JSON_ENC_KEY = "_enc"
NONCE_BYTES = 12
DEK_BYTES = 32

# Blind-index purposes (domain separation of the HMAC per column).
EMAIL_BIDX = "app_users.email"
CSV_FILENAME_BIDX = "csv_import_batches.original_filename"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode((data + "=" * (-len(data) % 4)).encode("ascii"))


def is_encrypted(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(ENC_PREFIX)


def is_encrypted_json(value: Any) -> bool:
    return isinstance(value, dict) and set(value.keys()) == {JSON_ENC_KEY} and is_encrypted(value[JSON_ENC_KEY])


def field_aad(table: str, column: str, owner_user_id: str) -> bytes:
    return f"{table}:{column}:{owner_user_id}".encode("utf-8")


def dek_aad(user_id: str) -> bytes:
    return f"dek:{user_id}".encode("utf-8")


def normalize_email(email: str | None) -> str | None:
    if email is None:
        return None
    normalized = email.strip().lower()
    return normalized or None


def _require_owner(owner_user_id: str) -> str:
    owner = (owner_user_id or "").strip() if isinstance(owner_user_id, str) else ""
    if not owner:
        raise ValueError("owner_user_id obbligatorio per cifrare/decifrare un campo")
    return owner_user_id


class DekCache:
    """Bounded LRU of unwrapped DEKs with a TTL, safe across threads."""

    def __init__(self, max_entries: int = 1024, ttl_seconds: float = 600.0, clock: Callable[[], float] = time.monotonic) -> None:
        self.max_entries = max(1, int(max_entries))
        self.ttl_seconds = float(ttl_seconds)
        self._clock = clock
        self._items: OrderedDict[str, tuple[bytes, float]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, user_id: str) -> bytes | None:
        now = self._clock()
        with self._lock:
            item = self._items.get(user_id)
            if item is None:
                return None
            dek, expires_at = item
            if expires_at <= now:
                del self._items[user_id]
                return None
            self._items.move_to_end(user_id)
            return dek

    def put(self, user_id: str, dek: bytes) -> None:
        if self.ttl_seconds <= 0:
            return
        with self._lock:
            self._items[user_id] = (dek, self._clock() + self.ttl_seconds)
            self._items.move_to_end(user_id)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def invalidate(self, user_id: str | None = None) -> None:
        with self._lock:
            if user_id is None:
                self._items.clear()
            else:
                self._items.pop(user_id, None)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


@dataclass
class RewrapResult:
    scanned: int = 0
    rewrapped: int = 0
    failed: list[str] = field(default_factory=list)


class FieldCrypto:
    """Encrypts/decrypts personal fields with per-user DEKs (see module docstring)."""

    def __init__(
        self,
        keyring: KeyRing | None,
        blind_index_key: bytes | None = None,
        *,
        store: DekStore | None = None,
        cache: DekCache | None = None,
    ) -> None:
        self.keyring = keyring
        self._bidx_key = blind_index_key or DEV_BLIND_INDEX_KEY
        self.store: DekStore = store or SqlDekStore()
        self.cache = cache or DekCache()

    @property
    def enabled(self) -> bool:
        return self.keyring is not None

    # -- DEKs --------------------------------------------------------------

    def _wrap(self, user_id: str, dek: bytes) -> tuple[str, bytes]:
        assert self.keyring is not None
        nonce = os.urandom(NONCE_BYTES)
        wrapped = nonce + AESGCM(self.keyring.active_key).encrypt(nonce, dek, dek_aad(user_id))
        return self.keyring.active_kid, wrapped

    def _unwrap(self, record: WrappedDek) -> bytes:
        if self.keyring is None:
            raise KeyUnavailableError("DATA_ENCRYPTION_KEYS non configurata: impossibile decifrare")
        kek = self.keyring.get(record.kek_id)
        if kek is None:
            raise KeyUnavailableError(
                f"KEK {record.kek_id!r} della DEK di {record.user_id} non presente in DATA_ENCRYPTION_KEYS"
            )
        blob = record.wrapped_dek
        if len(blob) <= NONCE_BYTES:
            raise DecryptionError(f"DEK di {record.user_id} corrotta")
        try:
            dek = AESGCM(kek).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], dek_aad(record.user_id))
        except InvalidTag as exc:
            raise DecryptionError(f"DEK di {record.user_id} non decifrabile con la KEK {record.kek_id!r}") from exc
        if len(dek) != DEK_BYTES:
            raise DecryptionError(f"DEK di {record.user_id} di lunghezza non valida")
        return dek

    def get_dek(self, conn: Any, user_id: str, *, create: bool) -> bytes | None:
        """The user's DEK (cached); created when missing and ``create`` is True."""
        cached = self.cache.get(user_id)
        if cached is not None:
            return cached
        if self.keyring is None:
            return None
        record = self.store.get(conn, user_id)
        if record is None:
            if not create:
                return None
            kid, wrapped = self._wrap(user_id, os.urandom(DEK_BYTES))
            # Committed on its own (see SqlDekStore.create_if_absent), so caching it is safe.
            record = self.store.create_if_absent(conn, user_id, kid, wrapped)
        dek = self._unwrap(record)
        self.cache.put(user_id, dek)
        return dek

    def invalidate(self, user_id: str | None = None) -> None:
        self.cache.invalidate(user_id)

    def shred_user(self, conn: Any, user_id: str) -> bool:
        """Delete the user's DEK: every value encrypted for them becomes unreadable.

        Legacy plaintext values and blind indexes are not touched (the caller
        deletes or anonymizes them). True if a key was deleted.
        """
        deleted = self.store.delete(conn, user_id)
        self.cache.invalidate(user_id)
        return deleted

    def rewrap_all(self, conn_factory: Callable[[], Any], *, batch_size: int = 500, dry_run: bool = False) -> RewrapResult:
        """Rewrap every DEK not wrapped with the active KEK (KEK rotation).

        ``conn_factory()`` returns a transaction context (e.g. ``engine.begin``):
        one per batch. Values stay as they are: only the wrapped DEKs change.
        """
        if self.keyring is None:
            raise CryptoConfigError("DATA_ENCRYPTION_KEYS non configurata")
        active = self.keyring.active_kid
        result = RewrapResult()
        after: str | None = None
        while True:
            with conn_factory() as conn:
                batch = self.store.list_not_wrapped_with(conn, active, after_user_id=after, limit=batch_size)
                if not batch:
                    break
                for record in batch:
                    result.scanned += 1
                    try:
                        dek = self._unwrap(record)
                    except DecryptionError as exc:
                        logger.error("rewrap: %s", exc)
                        result.failed.append(record.user_id)
                        continue
                    if dry_run:
                        result.rewrapped += 1
                        continue
                    kid, wrapped = self._wrap(record.user_id, dek)
                    if self.store.rewrap(conn, record.user_id, old_kek_id=record.kek_id, kek_id=kid, wrapped_dek=wrapped):
                        result.rewrapped += 1
                after = batch[-1].user_id
        return result

    # -- values ------------------------------------------------------------

    def encrypt(self, conn: Any, table: str, column: str, owner_user_id: str, value: str | None) -> str | None:
        """Ciphertext token for ``value`` (plaintext unchanged when encryption is off)."""
        if value is None or not self.enabled:
            return value
        # Always encrypted, even a value that looks like a token: a user typing
        # "enc:v1:..." as a name must get it back verbatim, not a decrypt error.
        owner = _require_owner(owner_user_id)
        dek = self.get_dek(conn, owner, create=True)
        assert dek is not None
        nonce = os.urandom(NONCE_BYTES)
        ciphertext = AESGCM(dek).encrypt(nonce, value.encode("utf-8"), field_aad(table, column, owner))
        return ENC_PREFIX + _b64url_encode(nonce + ciphertext)

    def decrypt(self, conn: Any, table: str, column: str, owner_user_id: str, value: Any) -> Any:
        """Plaintext of a token; legacy plaintext (no prefix) and None returned unchanged."""
        if not is_encrypted(value):
            return value
        owner = _require_owner(owner_user_id)
        try:
            blob = _b64url_decode(value[len(ENC_PREFIX):])
        except (binascii.Error, ValueError) as exc:
            raise DecryptionError(f"{table}.{column}: token cifrato non valido") from exc
        if len(blob) <= NONCE_BYTES:
            raise DecryptionError(f"{table}.{column}: token cifrato troppo corto")
        if not self.enabled:
            raise KeyUnavailableError(f"{table}.{column}: valore cifrato ma DATA_ENCRYPTION_KEYS non configurata")
        dek = self.get_dek(conn, owner, create=False)
        if dek is None:
            raise KeyUnavailableError(f"{table}.{column}: nessuna chiave dati per l'utente {owner} (crypto-shredding?)")
        try:
            plaintext = AESGCM(dek).decrypt(blob[:NONCE_BYTES], blob[NONCE_BYTES:], field_aad(table, column, owner))
        except InvalidTag as exc:
            raise DecryptionError(f"{table}.{column}: decifratura fallita (AAD o chiave non corrispondenti)") from exc
        return plaintext.decode("utf-8")

    def encrypt_json(self, conn: Any, table: str, column: str, owner_user_id: str, value: Any) -> Any:
        """``{"_enc": token}`` for a JSON-serializable value (unchanged when off)."""
        if value is None or not self.enabled or is_encrypted_json(value):
            return value
        payload = json.dumps(value, separators=(",", ":"), default=str)
        return {JSON_ENC_KEY: self.encrypt(conn, table, column, owner_user_id, payload)}

    def decrypt_json(self, conn: Any, table: str, column: str, owner_user_id: str, value: Any) -> Any:
        if isinstance(value, str):
            # Drivers hand back jsonb already decoded; a str is a raw JSON text.
            try:
                value = json.loads(value)
            except ValueError:
                return value
        if not is_encrypted_json(value):
            return value
        return json.loads(self.decrypt(conn, table, column, owner_user_id, value[JSON_ENC_KEY]))

    # -- blind index -------------------------------------------------------

    def blind_index(self, value: str | None, *, purpose: str) -> str | None:
        """Hex HMAC-SHA256 of ``purpose:value`` (None for None)."""
        if value is None:
            return None
        message = f"{purpose}\x00{value}".encode("utf-8")
        return hmac.new(self._bidx_key, message, hashlib.sha256).hexdigest()

    def email_blind_index(self, email: str | None) -> str | None:
        return self.blind_index(normalize_email(email), purpose=EMAIL_BIDX)

    def csv_filename_blind_index(self, filename: str | None) -> str | None:
        """Exact-match index of a CSV file name (same semantics as the old ``=``)."""
        return self.blind_index(filename, purpose=CSV_FILENAME_BIDX)


# ---------------------------------------------------------------------------
# Process-wide instance
# ---------------------------------------------------------------------------

_instance: FieldCrypto | None = None
_instance_lock = threading.Lock()


def build_field_crypto(settings: Any) -> FieldCrypto:
    """FieldCrypto from settings; raises CryptoConfigError on a bad/missing config.

    In production (APP_ENV prod/production) both DATA_ENCRYPTION_KEYS and
    DATA_BLIND_INDEX_KEY are required. Elsewhere a missing keyring keeps
    writes in plaintext (one warning) and a missing blind-index key falls back
    to a fixed dev key.
    """
    keyring = parse_keyring(getattr(settings, "data_encryption_keys", ""))
    bidx_key = parse_blind_index_key(getattr(settings, "data_blind_index_key", ""))
    if getattr(settings, "is_production", False):
        if keyring is None:
            raise CryptoConfigError(
                "DATA_ENCRYPTION_KEYS obbligatoria in produzione (cifratura dei dati personali, "
                "vedi docs/field-encryption.md)"
            )
        if bidx_key is None:
            raise CryptoConfigError(
                "DATA_BLIND_INDEX_KEY obbligatoria in produzione (vedi docs/field-encryption.md)"
            )
    if keyring is None:
        logger.warning(
            "DATA_ENCRYPTION_KEYS non configurata: i dati personali vengono scritti in chiaro (solo dev/test)"
        )
    elif bidx_key is None:
        logger.warning("DATA_BLIND_INDEX_KEY non configurata: blind index con la chiave fissa di sviluppo")
    return FieldCrypto(
        keyring,
        bidx_key,
        cache=DekCache(
            max_entries=getattr(settings, "data_dek_cache_size", 1024),
            ttl_seconds=getattr(settings, "data_dek_cache_ttl_seconds", 600.0),
        ),
    )


def init_field_crypto(settings: Any) -> FieldCrypto:
    """Validate the configuration and install the process-wide instance (app startup)."""
    global _instance
    crypto = build_field_crypto(settings)
    with _instance_lock:
        _instance = crypto
    return crypto


def get_field_crypto() -> FieldCrypto:
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                from ..config import get_settings

                _instance = build_field_crypto(get_settings())
    return _instance


def set_field_crypto(crypto: FieldCrypto | None) -> None:
    """Replace the process-wide instance (tests); None = rebuild lazily from settings."""
    global _instance
    with _instance_lock:
        _instance = crypto


# Thin module-level helpers used by the repositories.

def encrypt_field(conn: Any, table: str, column: str, owner_user_id: str, value: str | None) -> str | None:
    return get_field_crypto().encrypt(conn, table, column, owner_user_id, value)


def decrypt_field(conn: Any, table: str, column: str, owner_user_id: str, value: Any) -> Any:
    return get_field_crypto().decrypt(conn, table, column, owner_user_id, value)


def encrypt_json_field(conn: Any, table: str, column: str, owner_user_id: str, value: Any) -> Any:
    return get_field_crypto().encrypt_json(conn, table, column, owner_user_id, value)


def decrypt_json_field(conn: Any, table: str, column: str, owner_user_id: str, value: Any) -> Any:
    return get_field_crypto().decrypt_json(conn, table, column, owner_user_id, value)


def blind_index(value: str | None, *, purpose: str) -> str | None:
    return get_field_crypto().blind_index(value, purpose=purpose)


def email_blind_index(email: str | None) -> str | None:
    return get_field_crypto().email_blind_index(email)


def csv_filename_blind_index(filename: str | None) -> str | None:
    return get_field_crypto().csv_filename_blind_index(filename)


def shred_user_keys(conn: Any, user_id: str) -> bool:
    """Crypto-shred a user (deletes their DEK). Not exposed by any endpoint."""
    return get_field_crypto().shred_user(conn, user_id)


def invalidate_dek_cache(user_id: str | None = None) -> None:
    get_field_crypto().invalidate(user_id)
