"""Key material parsing: KEK keyring and blind-index key (TASK-57).

``DATA_ENCRYPTION_KEYS`` is a versioned keyring ``kid1:base64key,kid2:base64key``.
Every key is 32 bytes (AES-256). The first entry is the *active* KEK, used to
wrap new DEKs; the others are kept only to unwrap DEKs wrapped before a
rotation. ``DATA_BLIND_INDEX_KEY`` is a separate 32-byte key (base64) for the
HMAC-SHA256 blind indexes.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from dataclasses import dataclass

from .errors import CryptoConfigError

KEY_BYTES = 32
_KID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")

# Fixed, public key used for blind indexes when DATA_BLIND_INDEX_KEY is not
# set outside production: lookups keep working in dev/test, but the index
# gives no protection. Production refuses to start without a real key.
DEV_BLIND_INDEX_KEY = hashlib.sha256(b"valore365-dev-blind-index-key").digest()


def decode_key(raw: str, *, label: str) -> bytes:
    """Decode a base64 (standard or url-safe) 32-byte key."""
    value = (raw or "").strip()
    if not value:
        raise CryptoConfigError(f"{label}: chiave vuota")
    # Url-safe alphabet mapped to the standard one, then strict decoding
    # (non-strict b64decode silently drops unknown characters).
    padded = (value + "=" * (-len(value) % 4)).replace("-", "+").replace("_", "/")
    try:
        decoded = base64.b64decode(padded.encode("ascii"), validate=True)
    except (binascii.Error, ValueError, UnicodeEncodeError) as exc:
        raise CryptoConfigError(f"{label}: chiave non in base64") from exc
    if len(decoded) != KEY_BYTES:
        raise CryptoConfigError(f"{label}: la chiave deve essere di {KEY_BYTES} byte (trovati {len(decoded)})")
    return decoded


@dataclass(frozen=True)
class KeyRing:
    """Ordered KEKs: ``keys[0]`` is the active one."""

    keys: tuple[tuple[str, bytes], ...]

    @property
    def active_kid(self) -> str:
        return self.keys[0][0]

    @property
    def active_key(self) -> bytes:
        return self.keys[0][1]

    def get(self, kid: str) -> bytes | None:
        for key_id, key in self.keys:
            if key_id == kid:
                return key
        return None

    @property
    def kids(self) -> tuple[str, ...]:
        return tuple(kid for kid, _ in self.keys)


def parse_keyring(raw: str | None) -> KeyRing | None:
    """Parse ``kid:base64key,...``; None when the value is empty."""
    text = (raw or "").strip()
    if not text:
        return None
    entries: list[tuple[str, bytes]] = []
    seen: set[str] = set()
    for chunk in text.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        kid, sep, encoded = chunk.partition(":")
        kid = kid.strip()
        if not sep or not kid:
            raise CryptoConfigError("DATA_ENCRYPTION_KEYS: formato atteso 'kid:base64key,kid:base64key'")
        if not _KID_RE.match(kid):
            raise CryptoConfigError(f"DATA_ENCRYPTION_KEYS: kid non valido {kid!r} (ammessi lettere, cifre, _ . -)")
        if kid in seen:
            raise CryptoConfigError(f"DATA_ENCRYPTION_KEYS: kid duplicato {kid!r}")
        seen.add(kid)
        entries.append((kid, decode_key(encoded, label=f"DATA_ENCRYPTION_KEYS[{kid}]")))
    if not entries:
        return None
    return KeyRing(keys=tuple(entries))


def parse_blind_index_key(raw: str | None) -> bytes | None:
    """Decode DATA_BLIND_INDEX_KEY; None when the value is empty."""
    if not (raw or "").strip():
        return None
    return decode_key(raw or "", label="DATA_BLIND_INDEX_KEY")


def generate_key_b64() -> str:
    """A fresh random 32-byte key, base64-encoded (for docs and tests)."""
    import os

    return base64.b64encode(os.urandom(KEY_BYTES)).decode("ascii")
