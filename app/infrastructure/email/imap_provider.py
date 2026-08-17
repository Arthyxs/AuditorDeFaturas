"""IMAP implementation of the replaceable e-mail provider."""

from __future__ import annotations

import builtins
import imaplib
import re
import ssl
from collections.abc import Callable
from contextlib import suppress
from datetime import datetime
from email.utils import parsedate_to_datetime
from types import TracebackType
from typing import Any, Protocol, Self, cast

from app.infrastructure.email.mime_parser import parse_mime_message
from app.infrastructure.email.thread_resolver import resolve_thread_context
from app.ports.email import (
    EmailConnectionError,
    EmailFolderError,
    EmailMessage,
    EmailMessageLocator,
    EmailMessageNotFoundError,
    EmailProvider,
    EmailThreadContext,
)

_INTERNAL_DATE = re.compile(rb'INTERNALDATE "([^"]+)"')
_COPY_UID = re.compile(rb"(?:COPYUID|MOVEUID)\s+(\d+)\s+\d+(?::\d+)?\s+(\d+)")


class IMAPConnection(Protocol):
    """Small subset of imaplib used by the adapter and fakes."""

    capabilities: tuple[bytes, ...]

    def login(self, user: str, password: str) -> tuple[str, builtins.list[bytes]]: ...

    def select(self, mailbox: str, readonly: bool = False) -> tuple[str, builtins.list[bytes]]: ...

    def response(self, code: str) -> tuple[str | None, builtins.list[bytes] | None]: ...

    def uid(self, command: str, *args: Any) -> tuple[str, builtins.list[Any]]: ...

    def list(self, directory: str = "", pattern: str = "*") -> tuple[str, builtins.list[bytes]]: ...

    def create(self, mailbox: str) -> tuple[str, builtins.list[bytes]]: ...

    def starttls(self, ssl_context: ssl.SSLContext) -> tuple[str, builtins.list[bytes]]: ...

    def logout(self) -> tuple[str, builtins.list[bytes]]: ...


ConnectionFactory = Callable[[str, int, bool, bool, float, ssl.SSLContext], IMAPConnection]


def _default_connection_factory(
    host: str,
    port: int,
    implicit_tls: bool,
    starttls: bool,
    timeout: float,
    ssl_context: ssl.SSLContext,
) -> IMAPConnection:
    if implicit_tls:
        return cast(
            IMAPConnection,
            imaplib.IMAP4_SSL(host, port, ssl_context=ssl_context, timeout=timeout),
        )
    connection = cast(IMAPConnection, imaplib.IMAP4(host, port, timeout=timeout))
    if starttls:
        connection.starttls(ssl_context=ssl_context)
    return connection


class IMAPEmailProvider(EmailProvider):
    """Read originals with PEEK and perform explicit UID-based mailbox operations."""

    def __init__(
        self,
        *,
        host: str,
        port: int,
        username: str,
        password: str,
        implicit_tls: bool = True,
        starttls: bool = False,
        timeout_seconds: float = 30.0,
        thread_scan_limit: int = 100,
        connection_factory: ConnectionFactory = _default_connection_factory,
        ssl_context: ssl.SSLContext | None = None,
    ) -> None:
        if not host or not username or not password:
            raise ValueError("IMAP host, username and password are required")
        if implicit_tls and starttls:
            raise ValueError("implicit TLS and STARTTLS are mutually exclusive")
        if timeout_seconds <= 0 or thread_scan_limit < 1:
            raise ValueError("IMAP timeout and thread scan limit must be positive")
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._implicit_tls = implicit_tls
        self._starttls = starttls
        self._timeout_seconds = timeout_seconds
        self._thread_scan_limit = thread_scan_limit
        self._connection_factory = connection_factory
        self._ssl_context = ssl_context or ssl.create_default_context()
        self._connection: IMAPConnection | None = None

    def __enter__(self) -> Self:
        self._connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _connect(self) -> IMAPConnection:
        if self._connection is not None:
            return self._connection
        try:
            connection = self._connection_factory(
                self._host,
                self._port,
                self._implicit_tls,
                self._starttls,
                self._timeout_seconds,
                self._ssl_context,
            )
            status, _ = connection.login(self._username, self._password)
            if status != "OK":
                raise EmailConnectionError("IMAP authentication failed")
            self._connection = connection
            return connection
        except EmailConnectionError:
            raise
        except (imaplib.IMAP4.error, OSError, TimeoutError) as exc:
            raise EmailConnectionError("IMAP connection failed") from exc

    def _reset(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            with suppress(imaplib.IMAP4.error, OSError, TimeoutError):
                connection.logout()

    def _read_operation(self, operation: Callable[[IMAPConnection], Any]) -> Any:
        for attempt in range(2):
            try:
                return operation(self._connect())
            except (imaplib.IMAP4.abort, OSError, TimeoutError) as exc:
                self._reset()
                if attempt:
                    raise EmailConnectionError("IMAP operation failed after reconnect") from exc
        raise AssertionError("unreachable")

    @staticmethod
    def _uidvalidity(connection: IMAPConnection) -> int:
        _, values = connection.response("UIDVALIDITY")
        if not values:
            raise EmailFolderError("selected folder did not report UIDVALIDITY")
        try:
            return int(values[-1])
        except (TypeError, ValueError) as exc:
            raise EmailFolderError("selected folder returned invalid UIDVALIDITY") from exc

    @classmethod
    def _select(cls, connection: IMAPConnection, folder: str, *, readonly: bool) -> int:
        status, _ = connection.select(folder, readonly=readonly)
        if status != "OK":
            raise EmailFolderError("IMAP folder could not be selected")
        return cls._uidvalidity(connection)

    def list_messages(self, folder: str, *, limit: int) -> tuple[EmailMessageLocator, ...]:
        if limit < 1:
            raise ValueError("message list limit must be positive")

        def operation(connection: IMAPConnection) -> tuple[EmailMessageLocator, ...]:
            uidvalidity = self._select(connection, folder, readonly=True)
            status, data = connection.uid("SEARCH", None, "ALL")
            if status != "OK":
                raise EmailFolderError("IMAP search failed")
            raw_uids = data[0] if data else b""
            if not isinstance(raw_uids, bytes):
                raise EmailFolderError("IMAP search returned an invalid response")
            uids = [int(item) for item in raw_uids.split()]
            return tuple(
                EmailMessageLocator(folder=folder, uidvalidity=uidvalidity, uid=uid)
                for uid in uids[-limit:]
            )

        return cast(tuple[EmailMessageLocator, ...], self._read_operation(operation))

    @staticmethod
    def _extract_fetch(data: list[Any]) -> tuple[bytes, datetime | None]:
        for item in data:
            if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                metadata = item[0] if isinstance(item[0], bytes) else b""
                match = _INTERNAL_DATE.search(metadata)
                received_at = None
                if match:
                    try:
                        received_at = parsedate_to_datetime(match.group(1).decode("ascii"))
                    except (UnicodeDecodeError, TypeError, ValueError):
                        received_at = None
                return item[1], received_at
        raise EmailMessageNotFoundError("IMAP message body was not returned")

    def get_message(self, locator: EmailMessageLocator) -> EmailMessage:
        def operation(connection: IMAPConnection) -> EmailMessage:
            current_uidvalidity = self._select(connection, locator.folder, readonly=True)
            if current_uidvalidity != locator.uidvalidity:
                raise EmailMessageNotFoundError("folder UIDVALIDITY changed")
            status, data = connection.uid(
                "FETCH", str(locator.uid), "(UID INTERNALDATE BODY.PEEK[])"
            )
            if status != "OK":
                raise EmailMessageNotFoundError("IMAP message could not be fetched")
            raw_message, received_at = self._extract_fetch(data)
            return parse_mime_message(
                raw_message,
                locator=locator,
                received_at=received_at,
            )

        return cast(EmailMessage, self._read_operation(operation))

    def ensure_folder(self, folder: str) -> None:
        connection = self._connect()
        try:
            status, data = connection.list("", folder)
            if status == "OK" and any(item for item in data if item):
                return
            status, _ = connection.create(folder)
            if status != "OK":
                raise EmailFolderError("IMAP folder could not be created")
        except (imaplib.IMAP4.error, OSError, TimeoutError) as exc:
            self._reset()
            raise EmailConnectionError("IMAP folder operation failed") from exc

    def move_message(self, locator: EmailMessageLocator, destination: str) -> EmailMessageLocator:
        self.ensure_folder(destination)
        connection = self._connect()
        try:
            current_uidvalidity = self._select(connection, locator.folder, readonly=False)
            if current_uidvalidity != locator.uidvalidity:
                raise EmailMessageNotFoundError("folder UIDVALIDITY changed")
            status, data = connection.uid("MOVE", str(locator.uid), destination)
            if status != "OK":
                raise EmailFolderError("IMAP MOVE failed")
            response_chunks = [item for item in data if isinstance(item, bytes)]
            _, copyuid = connection.response("COPYUID")
            response_chunks.extend(copyuid or [])
            for chunk in response_chunks:
                match = _COPY_UID.search(chunk)
                if match:
                    return EmailMessageLocator(
                        folder=destination,
                        uidvalidity=int(match.group(1)),
                        uid=int(match.group(2)),
                    )
            raise EmailFolderError("IMAP server moved the message without COPYUID traceability")
        except (imaplib.IMAP4.abort, OSError, TimeoutError) as exc:
            self._reset()
            raise EmailConnectionError(
                "IMAP MOVE outcome is unknown; safe retry is required"
            ) from exc

    def get_thread_context(
        self,
        locator: EmailMessageLocator,
        *,
        max_messages: int,
        max_characters: int,
    ) -> EmailThreadContext:
        current = self.get_message(locator)
        locators = self.list_messages(locator.folder, limit=self._thread_scan_limit)
        candidates = tuple(
            self.get_message(candidate) for candidate in locators if candidate != locator
        )
        return resolve_thread_context(
            current,
            candidates,
            max_messages=max_messages,
            max_characters=max_characters,
        )

    def close(self) -> None:
        self._reset()
