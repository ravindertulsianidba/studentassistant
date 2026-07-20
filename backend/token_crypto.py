"""Authenticated encryption for Google Play purchase tokens at rest.

Purchase tokens are needed later (Google Play verification, reconciliation), so they cannot be
stored as one-way hashes only. Instead we store:
  - purchase_token_hash    -> indexing / ownership / replay detection (non-reversible)
  - encrypted_purchase_token -> authenticated-encrypted ciphertext (reversible only server-side)

The raw token is NEVER written to the database and NEVER logged. Encryption uses Fernet
(AES-128-CBC + HMAC-SHA256 authenticated encryption) with a key derived from a server-side
secret supplied via GOOGLE_PLAY_TOKEN_ENCRYPTION_KEY. When billing is enabled and the key is
missing/invalid, callers fail closed (never store plaintext, never grant Premium).
"""
import base64
import hashlib
import os

from cryptography.fernet import Fernet, InvalidToken


class TokenCryptoError(Exception):
    """Raised when the encryption key is missing/invalid or a token cannot be decrypted."""


def token_hash(raw: str) -> str:
    """Non-reversible fingerprint used for indexing, ownership and replay detection."""
    return hashlib.sha256((raw or "").encode("utf-8")).hexdigest()


def _fernet() -> Fernet:
    secret = os.environ.get("GOOGLE_PLAY_TOKEN_ENCRYPTION_KEY", "")
    if not secret:
        raise TokenCryptoError("GOOGLE_PLAY_TOKEN_ENCRYPTION_KEY is not configured")
    # Derive a valid 32-byte urlsafe Fernet key from any server secret string.
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def encryption_ready() -> bool:
    try:
        _fernet()
        return True
    except Exception:
        return False


def encrypt_token(raw: str) -> str:
    if not raw:
        raise TokenCryptoError("cannot encrypt an empty token")
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_token(enc: str) -> str:
    try:
        return _fernet().decrypt(enc.encode("utf-8")).decode("utf-8")
    except InvalidToken as e:
        raise TokenCryptoError("purchase token decryption failed") from e
