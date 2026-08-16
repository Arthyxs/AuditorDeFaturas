"""M05 password security tests."""

import pytest

from app.infrastructure.security.passwords import hash_password, verify_password


def test_argon2id_hash_and_verification() -> None:
    """Passwords use salted Argon2id and verify without retaining plaintext."""
    password = "test-only-strong-password"
    first = hash_password(password)
    second = hash_password(password)

    assert first.startswith("$argon2id$")
    assert first != second
    assert password not in first
    assert verify_password(first, password)
    assert not verify_password(first, "wrong-test-password")
    assert not verify_password("malformed", password)


def test_password_limits_are_enforced() -> None:
    """Weak and pathologically large inputs are rejected before hashing."""
    with pytest.raises(ValueError):
        hash_password("too-short")
    with pytest.raises(ValueError):
        hash_password("x" * 1025)
