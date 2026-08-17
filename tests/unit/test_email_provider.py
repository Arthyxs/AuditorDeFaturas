"""M10 IMAP provider, MIME and bounded-thread acceptance tests."""

from __future__ import annotations

import builtins
import imaplib
import ssl
from datetime import UTC, datetime
from email.message import EmailMessage as MIMEMessage
from email.policy import SMTP
from typing import Any

import pytest

from app.infrastructure.email.imap_provider import IMAPConnection, IMAPEmailProvider
from app.infrastructure.email.mime_parser import parse_mime_message
from app.infrastructure.email.thread_resolver import resolve_thread_context
from app.ports.email import EmailMessageLocator, EmailMessageNotFoundError


def _raw_message(
    *,
    message_id: str,
    subject: str = "Fatura agosto",
    body: str = "Cobrança com acentuação: São Paulo",
    references: str | None = None,
    in_reply_to: str | None = None,
    attachment_name: str | None = "fatura-ç.csv",
) -> bytes:
    message = MIMEMessage()
    message["Message-ID"] = message_id
    message["From"] = "Financeiro <financeiro@example.com>"
    message["To"] = "Operação <operacao@example.com>"
    message["Subject"] = subject
    message["Date"] = "Mon, 17 Aug 2026 12:00:00 -0300"
    if references:
        message["References"] = references
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
    message.set_content(body, charset="iso-8859-1")
    message.add_alternative(f"<p>{body}</p>", subtype="html", charset="utf-8")
    if attachment_name:
        message.add_attachment(
            b"cte;valor\n123;10,00\n",
            maintype="text",
            subtype="csv",
            filename=attachment_name,
        )
    return message.as_bytes(policy=SMTP)


class FakeIMAP:
    capabilities: tuple[bytes, ...] = (b"IMAP4REV1", b"MOVE", b"UIDPLUS")

    def __init__(self, messages: dict[int, bytes], *, abort_search_once: bool = False) -> None:
        self.messages = messages
        self.abort_search_once = abort_search_once
        self.folders = {"INBOX"}
        self.uidvalidities = {"INBOX": 81, "Processed": 92}
        self.selected = "INBOX"
        self.readonly_selections: list[bool] = []
        self.fetch_queries: list[str] = []
        self.login_calls = 0
        self.logout_calls = 0
        self.created: list[str] = []
        self.moved: list[tuple[int, str]] = []

    def login(self, user: str, password: str) -> tuple[str, builtins.list[bytes]]:
        assert user == "account@example.com"
        assert password == "secret"
        self.login_calls += 1
        return "OK", [b"authenticated"]

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, builtins.list[bytes]]:
        if mailbox not in self.folders:
            return "NO", [b"missing"]
        self.selected = mailbox
        self.readonly_selections.append(readonly)
        return "OK", [str(len(self.messages)).encode()]

    def response(self, code: str) -> tuple[str | None, builtins.list[bytes] | None]:
        if code == "UIDVALIDITY":
            return code, [str(self.uidvalidities[self.selected]).encode()]
        if code == "COPYUID" and self.moved:
            source, _ = self.moved[-1]
            return code, [f"COPYUID 92 {source} 9001".encode()]
        return None, None

    def uid(self, command: str, *args: Any) -> tuple[str, builtins.list[Any]]:
        if command == "SEARCH":
            if self.abort_search_once:
                self.abort_search_once = False
                raise imaplib.IMAP4.abort("synthetic disconnect")
            return "OK", [b" ".join(str(uid).encode() for uid in sorted(self.messages))]
        if command == "FETCH":
            uid = int(args[0])
            self.fetch_queries.append(str(args[1]))
            raw = self.messages.get(uid)
            if raw is None:
                return "OK", [None]
            metadata = f'{uid} (UID {uid} INTERNALDATE "17-Aug-2026 15:00:00 +0000")'.encode()
            return "OK", [(metadata, raw), b")"]
        if command == "MOVE":
            uid, destination = int(args[0]), str(args[1])
            self.moved.append((uid, destination))
            return "OK", [f"MOVEUID 92 {uid} 9001".encode()]
        raise AssertionError(command)

    def list(self, directory: str = "", pattern: str = "*") -> tuple[str, builtins.list[bytes]]:
        if pattern in self.folders:
            return "OK", [f'(\\HasNoChildren) "/" "{pattern}"'.encode()]
        return "OK", []

    def create(self, mailbox: str) -> tuple[str, builtins.list[bytes]]:
        self.folders.add(mailbox)
        self.uidvalidities.setdefault(mailbox, 92)
        self.created.append(mailbox)
        return "OK", [b"created"]

    def starttls(self, ssl_context: ssl.SSLContext) -> tuple[str, builtins.list[bytes]]:
        return "OK", [b"tls"]

    def logout(self) -> tuple[str, builtins.list[bytes]]:
        self.logout_calls += 1
        return "BYE", [b"logout"]


def test_mime_parser_preserves_headers_bodies_encodings_and_attachment() -> None:
    raw = _raw_message(message_id="<current@example.com>")
    locator = EmailMessageLocator(folder="INBOX", uidvalidity=81, uid=7)
    parsed = parse_mime_message(raw, locator=locator, received_at=datetime.now(UTC))

    assert parsed.raw_message == raw
    assert parsed.message_id == "<current@example.com>"
    assert parsed.subject == "Fatura agosto"
    assert "São Paulo" in (parsed.body_text or "")
    assert "<p>" in (parsed.body_html or "")
    assert parsed.sender == "financeiro@example.com"
    assert parsed.recipients == ("operacao@example.com",)
    assert dict(parsed.headers)["Message-ID"] == "<current@example.com>"
    assert len(parsed.attachments) == 1
    assert parsed.attachments[0].filename == "fatura-ç.csv"
    assert parsed.attachments[0].mime_type == "text/csv"
    assert parsed.attachments[0].payload.startswith(b"cte;valor")


def test_contract_lists_peeks_fetches_creates_and_moves_with_uid_traceability() -> None:
    fake = FakeIMAP({7: _raw_message(message_id="<current@example.com>")})
    calls: list[tuple[str, int, bool, bool, float]] = []

    def factory(
        host: str,
        port: int,
        implicit_tls: bool,
        starttls: bool,
        timeout: float,
        ssl_context: ssl.SSLContext,
    ) -> IMAPConnection:
        assert isinstance(ssl_context, ssl.SSLContext)
        calls.append((host, port, implicit_tls, starttls, timeout))
        return fake

    provider = IMAPEmailProvider(
        host="imap.example.com",
        port=993,
        username="account@example.com",
        password="secret",
        implicit_tls=True,
        timeout_seconds=4.5,
        connection_factory=factory,
    )
    locators = provider.list_messages("INBOX", limit=10)
    assert locators == (EmailMessageLocator(folder="INBOX", uidvalidity=81, uid=7),)
    message = provider.get_message(locators[0])
    assert message.attachments[0].payload.startswith(b"cte;valor")
    assert fake.readonly_selections == [True, True]
    assert fake.fetch_queries == ["(UID INTERNALDATE BODY.PEEK[])"]

    moved = provider.move_message(locators[0], "Processed")
    assert fake.created == ["Processed"]
    assert fake.moved == [(7, "Processed")]
    assert moved == EmailMessageLocator(folder="Processed", uidvalidity=92, uid=9001)
    assert calls == [("imap.example.com", 993, True, False, 4.5)]
    provider.close()


def test_read_operation_reconnects_once_after_abort() -> None:
    first = FakeIMAP({}, abort_search_once=True)
    second = FakeIMAP({3: _raw_message(message_id="<three@example.com>")})
    connections = iter((first, second))
    provider = IMAPEmailProvider(
        host="imap.example.com",
        port=143,
        username="account@example.com",
        password="secret",
        implicit_tls=False,
        starttls=True,
        connection_factory=lambda *_: next(connections),
    )
    assert provider.list_messages("INBOX", limit=1)[0].uid == 3
    assert first.logout_calls == 1
    assert second.login_calls == 1


def test_uidvalidity_change_rejects_stale_locator() -> None:
    fake = FakeIMAP({7: _raw_message(message_id="<current@example.com>")})
    provider = IMAPEmailProvider(
        host="imap.example.com",
        port=993,
        username="account@example.com",
        password="secret",
        connection_factory=lambda *_: fake,
    )
    stale = EmailMessageLocator(folder="INBOX", uidvalidity=80, uid=7)
    with pytest.raises(EmailMessageNotFoundError, match="UIDVALIDITY"):
        provider.get_message(stale)


def test_thread_context_uses_ids_then_bounded_subject_participant_fallback() -> None:
    current_locator = EmailMessageLocator("INBOX", 81, 5)
    parent_locator = EmailMessageLocator("INBOX", 81, 4)
    older_locator = EmailMessageLocator("INBOX", 81, 3)
    unrelated_locator = EmailMessageLocator("INBOX", 81, 2)
    current = parse_mime_message(
        _raw_message(
            message_id="<current@example.com>",
            subject="RE: Fatura agosto",
            references="<parent@example.com>",
            in_reply_to="<parent@example.com>",
            attachment_name=None,
        ),
        locator=current_locator,
        received_at=datetime(2026, 8, 17, 15, tzinfo=UTC),
    )
    parent = parse_mime_message(
        _raw_message(message_id="<parent@example.com>", attachment_name=None),
        locator=parent_locator,
        received_at=datetime(2026, 8, 16, 15, tzinfo=UTC),
    )
    older = parse_mime_message(
        _raw_message(
            message_id="<older@example.com>",
            subject="FWD: Fatura agosto",
            attachment_name=None,
        ),
        locator=older_locator,
        received_at=datetime(2026, 8, 15, 15, tzinfo=UTC),
    )
    unrelated = parse_mime_message(
        _raw_message(
            message_id="<other@example.com>",
            subject="Outro assunto",
            attachment_name=None,
        ),
        locator=unrelated_locator,
        received_at=datetime(2026, 8, 14, 15, tzinfo=UTC),
    )

    limited = resolve_thread_context(
        current,
        (unrelated, older, parent),
        max_messages=1,
        max_characters=10000,
    )
    assert [message.message_id for message in limited.history] == ["<parent@example.com>"]
    assert limited.truncated is True
    character_limited = resolve_thread_context(
        current,
        (parent,),
        max_messages=5,
        max_characters=1,
    )
    assert character_limited.history == ()
    assert character_limited.truncated is True
