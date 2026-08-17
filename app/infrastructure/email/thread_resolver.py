"""Provider-neutral bounded e-mail thread resolution."""

from datetime import UTC, datetime

from app.domain.email.fingerprint import normalize_subject
from app.ports.email import EmailMessage, EmailThreadContext


def _timestamp(message: EmailMessage) -> datetime:
    value = message.received_at or message.header_date
    if value is None:
        return datetime.min.replace(tzinfo=UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _participants(message: EmailMessage) -> frozenset[str]:
    return frozenset(
        address.strip().casefold() for address in (message.sender, *message.recipients) if address
    )


def _related(current: EmailMessage, candidate: EmailMessage) -> bool:
    candidate_id = candidate.message_id
    strong_ids = {current.in_reply_to, *current.references}
    if candidate_id and candidate_id in strong_ids:
        return True
    if current.message_id and (
        candidate.in_reply_to == current.message_id or current.message_id in candidate.references
    ):
        return True
    return bool(
        normalize_subject(current.subject)
        and normalize_subject(current.subject) == normalize_subject(candidate.subject)
        and _participants(current).intersection(_participants(candidate))
    )


def resolve_thread_context(
    current: EmailMessage,
    candidates: tuple[EmailMessage, ...],
    *,
    max_messages: int,
    max_characters: int,
) -> EmailThreadContext:
    """Select related history with hard message and character bounds."""
    if max_messages < 1 or max_characters < 1:
        raise ValueError("thread limits must be positive")
    related = sorted(
        (
            message
            for message in candidates
            if message.locator != current.locator and _related(current, message)
        ),
        key=_timestamp,
        reverse=True,
    )
    selected: list[EmailMessage] = []
    total = 0
    truncated = len(related) > max_messages
    for message in related[:max_messages]:
        size = len(message.body_text or "") + len(message.body_html or "")
        if total + size > max_characters:
            truncated = True
            break
        selected.append(message)
        total += size
    selected.reverse()
    return EmailThreadContext(
        current=current,
        history=tuple(selected),
        total_characters=total,
        truncated=truncated,
    )
