"""Opaque session token primitives."""

from hashlib import sha256
from secrets import token_urlsafe


def new_session_token() -> str:
    """Generate a high-entropy token suitable only for the secure cookie."""
    return token_urlsafe(48)


def hash_session_token(token: str) -> str:
    """Create the non-reversible database identifier for a session token."""
    return sha256(token.encode("utf-8")).hexdigest()
