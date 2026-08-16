"""Argon2id password hashing isolated from application services."""

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

_PASSWORD_HASHER = PasswordHasher(type=Type.ID)


def hash_password(password: str) -> str:
    """Hash a password with Argon2id after applying safe input limits."""
    if len(password) < 12:
        raise ValueError("password must contain at least 12 characters")
    if len(password.encode("utf-8")) > 1024:
        raise ValueError("password is too long")
    return _PASSWORD_HASHER.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verify without leaking malformed-hash or mismatch details."""
    try:
        return _PASSWORD_HASHER.verify(password_hash, password)
    except (InvalidHashError, VerificationError):
        return False
