"""Exceptions of the field-level encryption package (TASK-57)."""


class FieldCryptoError(Exception):
    """Base class of every field-encryption error."""


class CryptoConfigError(FieldCryptoError):
    """DATA_ENCRYPTION_KEYS / DATA_BLIND_INDEX_KEY missing or malformed."""


class DecryptionError(FieldCryptoError):
    """A ciphertext could not be decrypted.

    Raised for a corrupt token, a token moved to another row/column/user
    (the AAD does not match) or a DEK wrapped with a key that fails to unwrap.
    """


class KeyUnavailableError(DecryptionError):
    """The key needed to decrypt is gone.

    The user's DEK row does not exist (crypto-shredded user), the KEK that
    wrapped it is not in the keyring any more, or encryption is not
    configured in this process while the value is encrypted.
    """
