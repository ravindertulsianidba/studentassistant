"""Password hashing (Argon2id), token generation/hashing, and password policy."""
import hashlib
import secrets

from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

# Argon2id (pwdlib's Argon2Hasher uses the argon2id variant by default).
_pwd = PasswordHash((Argon2Hasher(),))

# Constant dummy hash to verify against when a user does not exist — mitigates
# user-enumeration via response-timing on login.
DUMMY_HASH = _pwd.hash("a-dummy-password-for-timing-safety")

MIN_LEN = 10
MAX_LEN = 128

# A small bundled set of the most common / compromised passwords. "where feasible"
# — a full HIBP check needs network access and is deferred to a later phase.
_COMMON = {
    "password", "123456", "123456789", "12345678", "12345", "1234567",
    "qwerty", "abc123", "password1", "111111", "1234567890", "123123",
    "iloveyou", "000000", "qwerty123", "1q2w3e4r", "admin", "letmein",
    "welcome", "monkey", "dragon", "passw0rd", "password123", "qwertyuiop",
    "sunshine", "princess", "football", "charlie", "aa123456", "donald",
    "starwars", "whatever", "trustno1", "1qaz2wsx", "654321", "superman",
}


def hash_password(pw: str) -> str:
    return _pwd.hash(pw)


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return _pwd.verify(pw, hashed)
    except Exception:
        return False


def new_token() -> str:
    """URL-safe, high-entropy raw token (kept only in the email; never stored)."""
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validate_password(pw: str) -> str | None:
    """Return an error string if the password is unacceptable, else None.
    Passwords are NOT truncated; spaces/passphrases are allowed."""
    if not isinstance(pw, str) or len(pw) < MIN_LEN:
        return f"Password must be at least {MIN_LEN} characters."
    if len(pw) > MAX_LEN:
        return f"Password must be at most {MAX_LEN} characters."
    if pw.strip().lower() in _COMMON:
        return "This password is too common. Please choose a stronger one."
    return None
