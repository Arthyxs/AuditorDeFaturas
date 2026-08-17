"""M11 canonical e-mail fingerprint vectors."""

from datetime import UTC, datetime
from uuid import UUID

from app.domain.email.fingerprint import (
    build_server_key,
    fingerprint_message,
    normalize_sender,
    normalize_text,
)
from app.ports.email import EmailAttachment, EmailMessage, EmailMessageLocator


def _message(
    *,
    uid: int = 1,
    folder: str = "INBOX",
    message_id: str | None = "<Invoice-1@Example.COM>",
    attachments: tuple[EmailAttachment, ...] | None = None,
) -> EmailMessage:
    return EmailMessage(
        locator=EmailMessageLocator(folder=folder, uidvalidity=7, uid=uid),
        raw_message=b"raw-rfc-message",
        headers=(("From", "Billing <BILLING@example.com>"),),
        message_id=message_id,
        in_reply_to=None,
        references=(),
        subject="  RE:  Fatura   Agosto  ",
        sender="Billing <BILLING@example.com>",
        recipients=("finance@example.com",),
        header_date=datetime(2026, 8, 17, 12, 30, tzinfo=UTC),
        received_at=datetime(2026, 8, 17, 12, 31, tzinfo=UTC),
        body_text="Valor： 10,00  \r\nLinha 2   \r\n",
        body_html="<p>Valor: 10,00</p>\r\n",
        attachments=attachments
        or (
            EmailAttachment("b.csv", "text/csv", None, "attachment", b"second"),
            EmailAttachment("a.pdf", "application/pdf", None, "attachment", b"first"),
        ),
    )


def test_normalization_and_server_key_vectors() -> None:
    assert normalize_sender("Billing <BILLING@Example.COM>") == "billing@example.com"
    assert normalize_text("Ａ  \r\nB\t \r\n") == "A\nB"
    account_id = UUID("11111111-2222-3333-4444-555555555555")
    assert build_server_key(account_id, uidvalidity=9, uid=42) == (
        "11111111-2222-3333-4444-555555555555:9:42"
    )


def test_canonical_fingerprint_is_stable_without_message_id_and_ignores_attachment_order() -> None:
    original = _message(message_id=None)
    reversed_parts = tuple(reversed(original.attachments))
    moved = _message(
        uid=99,
        folder="Processed",
        message_id=None,
        attachments=reversed_parts,
    )
    first = fingerprint_message(original)
    second = fingerprint_message(moved)

    assert first.sender_normalized == "billing@example.com"
    assert first.subject_normalized == "fatura agosto"
    assert first.message_id_normalized is None
    assert first.attachment_sha256s == tuple(sorted(first.attachment_sha256s))
    assert first.content_fingerprint == second.content_fingerprint
    assert first.content_fingerprint == (
        "ba13bdfd8f1478ccfe397354401a74a6dcb3ff250a7b7e03198c17bada94ef97"
    )
