"""PostgreSQL e-mail ingestion repository with transaction-scoped deduplication guards."""

from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.domain.email.models import MailAccountRecord, MailMessageRecord, NewMailMessage
from app.infrastructure.persistence.models import MailAccount, MailAttachment, MailMessage
from app.infrastructure.persistence.session import SessionFactory
from app.ports.email_ingestion import MailIngestionRepository, MailIngestionTransaction


def _advisory_key(value: str) -> int:
    unsigned = int.from_bytes(sha256(value.encode("utf-8")).digest()[:8], "big")
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


class PostgreSQLMailIngestionTransaction(MailIngestionTransaction):
    def __init__(self, database: Session) -> None:
        self._database = database

    def find_duplicate(
        self, *, server_key: str, content_fingerprint: str
    ) -> tuple[MailMessageRecord, str] | None:
        by_server = self._database.scalar(
            select(MailMessage).where(MailMessage.server_key == server_key)
        )
        if by_server is not None:
            return self._record(by_server), "server_key"
        by_content = self._database.scalar(
            select(MailMessage).where(MailMessage.content_fingerprint == content_fingerprint)
        )
        if by_content is not None:
            return self._record(by_content), "content_fingerprint"
        return None

    def insert(self, message: NewMailMessage) -> MailMessageRecord:
        model = MailMessage(
            mail_account_id=message.mail_account_id,
            uidvalidity=message.uidvalidity,
            uid=message.uid,
            message_id=message.message_id,
            in_reply_to=message.in_reply_to,
            references=list(message.references),
            subject=message.subject,
            normalized_subject=message.normalized_subject,
            sender=message.sender,
            normalized_sender=message.normalized_sender,
            recipients=list(message.recipients),
            headers=[list(header) for header in message.headers],
            header_date=message.header_date,
            received_at=message.received_at,
            body_text=message.body_text,
            body_html=message.body_html,
            normalized_body_hash=message.normalized_body_hash,
            raw_size=message.raw_size,
            raw_sha256=message.raw_sha256,
            raw_storage_key=message.raw_storage_key,
            server_key=message.server_key,
            content_fingerprint=message.content_fingerprint,
            status="INGESTED",
            original_folder=message.original_folder,
            current_folder=message.current_folder,
        )
        self._database.add(model)
        self._database.flush()
        for attachment in message.attachments:
            self._database.add(
                MailAttachment(
                    mail_message_id=model.id,
                    ordinal=attachment.ordinal,
                    filename=attachment.filename,
                    mime_type=attachment.mime_type,
                    content_id=attachment.content_id,
                    size=attachment.size,
                    sha256=attachment.sha256,
                    storage_key=attachment.storage_key,
                )
            )
        self._database.flush()
        return self._record(model)

    @staticmethod
    def _record(model: MailMessage) -> MailMessageRecord:
        return MailMessageRecord(
            id=model.id,
            mail_account_id=model.mail_account_id,
            server_key=model.server_key,
            content_fingerprint=model.content_fingerprint,
            raw_sha256=model.raw_sha256,
            raw_storage_key=model.raw_storage_key,
            attachment_count=len(model.attachments),
            created_at=model.created_at,
        )


class PostgreSQLMailIngestionRepository(MailIngestionRepository):
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def get_or_create_account(
        self,
        *,
        display_name: str,
        host: str,
        port: int,
        ssl: bool,
        username: str,
        active: bool = True,
    ) -> MailAccountRecord:
        database = self._session_factory()
        try:
            with database.begin():
                account_id = database.scalar(
                    insert(MailAccount)
                    .values(
                        id=uuid4(),
                        display_name=display_name,
                        host=host.casefold(),
                        port=port,
                        ssl=ssl,
                        username=username.casefold(),
                        active=active,
                    )
                    .on_conflict_do_update(
                        constraint="uq_mail_accounts_mailbox_identity",
                        set_={
                            "display_name": display_name,
                            "ssl": ssl,
                            "active": active,
                        },
                    )
                    .returning(MailAccount.id)
                )
                if account_id is None:
                    raise RuntimeError("mail account upsert returned no identity")
                account = database.get(MailAccount, account_id)
                if account is None:
                    raise RuntimeError("mail account disappeared after upsert")
                return MailAccountRecord(
                    id=account.id,
                    display_name=account.display_name,
                    host=account.host,
                    port=account.port,
                    ssl=account.ssl,
                    username=account.username,
                    active=account.active,
                )
        finally:
            database.close()

    @contextmanager
    def begin_guarded(
        self, *, server_key: str, content_fingerprint: str
    ) -> Iterator[MailIngestionTransaction]:
        database = self._session_factory()
        try:
            with database.begin():
                for key in sorted({_advisory_key(server_key), _advisory_key(content_fingerprint)}):
                    database.execute(select(func.pg_advisory_xact_lock(key)))
                yield PostgreSQLMailIngestionTransaction(database)
        finally:
            database.close()
