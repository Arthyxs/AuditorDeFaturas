"""Transaction-scoped PostgreSQL locks for invoice processing."""

from hashlib import sha256
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.orm import Session


def invoice_lock_key(invoice_id: UUID) -> int:
    """Derive a stable signed 64-bit advisory-lock key for an invoice UUID."""
    digest = sha256(b"invoice-auditor:invoice:" + invoice_id.bytes).digest()
    return int.from_bytes(digest[:8], byteorder="big", signed=True)


def try_invoice_lock(database: Session, invoice_id: UUID) -> bool:
    """Acquire an invoice lock until the current transaction ends, without waiting."""
    acquired = database.scalar(
        text("SELECT pg_try_advisory_xact_lock(:lock_key)"),
        {"lock_key": invoice_lock_key(invoice_id)},
    )
    return bool(acquired)


def acquire_invoice_lock(database: Session, invoice_id: UUID) -> None:
    """Wait for and hold an invoice lock until the current transaction ends."""
    database.execute(
        text("SELECT pg_advisory_xact_lock(:lock_key)"),
        {"lock_key": invoice_lock_key(invoice_id)},
    )
