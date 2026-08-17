"""Standards-based MIME parsing without provider or domain dependencies."""

from __future__ import annotations

from datetime import datetime
from email import policy
from email.headerregistry import AddressHeader, DateHeader
from email.message import EmailMessage as ParsedEmailMessage
from email.parser import BytesParser
from email.utils import getaddresses, parsedate_to_datetime

from app.ports.email import EmailAttachment, EmailMessage, EmailMessageLocator


def _text_payload(part: ParsedEmailMessage) -> str | None:
    try:
        content = part.get_content()
    except (LookupError, UnicodeError):
        raw = part.get_payload(decode=True)
        if not isinstance(raw, bytes):
            return None
        content = raw.decode(part.get_content_charset() or "utf-8", errors="replace")
    if isinstance(content, str):
        return content.replace("\r\n", "\n").replace("\r", "\n")
    return None


def _date(message: ParsedEmailMessage) -> datetime | None:
    value = message.get("Date")
    if isinstance(value, DateHeader):
        return value.datetime
    if not value:
        return None
    try:
        return parsedate_to_datetime(str(value))
    except (TypeError, ValueError):
        return None


def _addresses(message: ParsedEmailMessage, names: tuple[str, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for name in names:
        header = message.get(name)
        if isinstance(header, AddressHeader):
            values.extend(address.addr_spec for address in header.addresses)
        elif header:
            values.extend(address for _, address in getaddresses([str(header)]) if address)
    return tuple(dict.fromkeys(values))


def _message_ids(value: str | None) -> tuple[str, ...]:
    if not value:
        return ()
    return tuple(token for token in value.replace("\r", " ").replace("\n", " ").split() if token)


def parse_mime_message(
    raw_message: bytes,
    *,
    locator: EmailMessageLocator,
    received_at: datetime | None,
) -> EmailMessage:
    """Decode one RFC message while retaining the exact original bytes."""
    parsed: ParsedEmailMessage = BytesParser(policy=policy.default).parsebytes(raw_message)
    text_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[EmailAttachment] = []

    for part in parsed.walk():
        if part.is_multipart():
            continue
        disposition = part.get_content_disposition()
        filename = part.get_filename()
        content_id = part.get("Content-ID")
        content_type = part.get_content_type()
        is_attachment = (
            disposition == "attachment"
            or filename is not None
            or content_id is not None
            or not content_type.startswith("text/")
        )
        if is_attachment:
            raw_payload = part.get_payload(decode=True)
            payload = raw_payload if isinstance(raw_payload, bytes) else b""
            attachments.append(
                EmailAttachment(
                    filename=filename or f"attachment-{len(attachments)}.bin",
                    mime_type=part.get_content_type(),
                    content_id=str(content_id) if content_id else None,
                    disposition=disposition,
                    payload=payload,
                )
            )
            continue
        if content_type == "text/plain":
            content = _text_payload(part)
            if content:
                text_parts.append(content)
        elif content_type == "text/html":
            content = _text_payload(part)
            if content:
                html_parts.append(content)

    headers = tuple((name, str(value)) for name, value in parsed.raw_items())
    senders = _addresses(parsed, ("From",))
    return EmailMessage(
        locator=locator,
        raw_message=raw_message,
        headers=headers,
        message_id=str(parsed.get("Message-ID")) if parsed.get("Message-ID") else None,
        in_reply_to=str(parsed.get("In-Reply-To")) if parsed.get("In-Reply-To") else None,
        references=_message_ids(
            str(parsed.get("References")) if parsed.get("References") else None
        ),
        subject=str(parsed.get("Subject", "")),
        sender=senders[0] if senders else "",
        recipients=_addresses(parsed, ("To", "Cc", "Bcc")),
        header_date=_date(parsed),
        received_at=received_at,
        body_text="\n".join(text_parts) or None,
        body_html="\n".join(html_parts) or None,
        attachments=tuple(attachments),
    )
