"""PostgreSQL adapter for semantic tariff selection and pending state."""

from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from hashlib import sha256
from uuid import UUID

from sqlalchemy import Engine, func, select

from app.domain.tariffs.selection import (
    TariffCandidate,
    TariffSelectionContext,
    TariffSelectionRecord,
    TariffSelectionStatus,
)
from app.infrastructure.persistence.models import (
    Invoice,
    PendingItem,
    TariffFile,
    TariffSelectionFile,
    TariffSelectionRun,
)
from app.infrastructure.persistence.session import SessionFactory, session_scope


def _guard_key(invoice_id: UUID) -> int:
    unsigned = int.from_bytes(sha256(f"tariff-selection:{invoice_id}".encode()).digest()[:8], "big")
    return unsigned - (1 << 64) if unsigned >= (1 << 63) else unsigned


class PostgreSQLTariffSelectionRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        engine = session_factory.kw.get("bind")
        if not isinstance(engine, Engine):
            raise TypeError("tariff selection requires an Engine-bound session factory")
        self._engine = engine

    @contextmanager
    def selection_guard(self, invoice_id: UUID) -> Iterator[None]:
        key = _guard_key(invoice_id)
        with self._engine.connect() as connection:
            connection.execute(select(func.pg_advisory_lock(key)))
            connection.commit()
            try:
                yield
            finally:
                connection.execute(select(func.pg_advisory_unlock(key)))
                connection.commit()

    def context(self, invoice_id: UUID) -> TariffSelectionContext | None:
        with session_scope(self._session_factory) as database:
            invoice = database.get(Invoice, invoice_id)
            if invoice is None:
                return None
            candidates = database.scalars(
                select(TariffFile)
                .where(TariffFile.active.is_(True), TariffFile.deleted_at.is_(None))
                .order_by(TariffFile.created_at, TariffFile.id)
            ).all()
            documents = tuple(
                {
                    "document_type": item.document_type,
                    "document_number": item.document_number,
                    "issue_date": item.issue_date.isoformat() if item.issue_date else None,
                    "origin_city": item.origin_city,
                    "origin_state": item.origin_state,
                    "destination_city": item.destination_city,
                    "destination_state": item.destination_state,
                    "origin_zip": item.origin_zip,
                    "destination_zip": item.destination_zip,
                    "amount_charged": str(item.amount_charged)
                    if item.amount_charged is not None
                    else None,
                }
                for item in invoice.documents
            )
            return TariffSelectionContext(
                invoice_id=invoice.id,
                partner_name=invoice.partner_name_raw,
                invoice_number=invoice.invoice_number,
                issue_date=invoice.issue_date,
                due_date=invoice.due_date,
                currency=invoice.currency,
                amount_charged=invoice.amount_charged,
                documents=documents,
                candidates=tuple(
                    TariffCandidate(
                        id=item.id,
                        original_filename=item.original_filename,
                        extension=item.extension,
                        description=item.description,
                        notes=item.notes,
                        version=item.version,
                        created_at=item.created_at,
                    )
                    for item in candidates
                ),
            )

    def existing(self, invoice_id: UUID) -> TariffSelectionRecord | None:
        with session_scope(self._session_factory) as database:
            model = database.scalar(
                select(TariffSelectionRun).where(TariffSelectionRun.invoice_id == invoice_id)
            )
            return None if model is None else self._record(model)

    def save(
        self,
        invoice_id: UUID,
        *,
        status: TariffSelectionStatus,
        selected_tariff_ids: tuple[UUID, ...],
        confidence: Decimal | None,
        threshold: Decimal,
        reason: str,
        ai_call_id: UUID | None,
    ) -> TariffSelectionRecord:
        with session_scope(self._session_factory) as database:
            existing = database.scalar(
                select(TariffSelectionRun)
                .where(TariffSelectionRun.invoice_id == invoice_id)
                .with_for_update()
            )
            if existing is not None:
                return self._record(existing)
            invoice = database.scalar(
                select(Invoice).where(Invoice.id == invoice_id).with_for_update()
            )
            if invoice is None:
                raise LookupError("invoice not found")
            if status is TariffSelectionStatus.SELECTED:
                valid_ids = set(
                    database.scalars(
                        select(TariffFile.id).where(
                            TariffFile.id.in_(selected_tariff_ids),
                            TariffFile.active.is_(True),
                            TariffFile.deleted_at.is_(None),
                        )
                    ).all()
                )
                if valid_ids != set(selected_tariff_ids) or not valid_ids:
                    raise ValueError("selected tariffs are not an exact active catalog subset")
            run = TariffSelectionRun(
                invoice_id=invoice_id,
                status=status.value,
                confidence=confidence,
                threshold=threshold,
                reason=reason,
                ai_call_id=ai_call_id,
            )
            database.add(run)
            database.flush()
            for tariff_id in selected_tariff_ids:
                database.add(TariffSelectionFile(selection_run_id=run.id, tariff_file_id=tariff_id))
            if status is not TariffSelectionStatus.SELECTED:
                invoice.status = "PENDING"
                pending_type = (
                    "PENDING_NO_TARIFF"
                    if status is TariffSelectionStatus.NO_TARIFF
                    else "PENDING_TARIFF_SELECTION_LOW_CONFIDENCE"
                )
                database.add(
                    PendingItem(
                        invoice_id=invoice_id,
                        type=pending_type,
                        description=reason,
                        required_information={"action": "upload or identify an applicable tariff"},
                        status="OPEN",
                    )
                )
            database.flush()
            database.refresh(run, attribute_names=["files"])
            return self._record(run)

    def selected_storage_keys(self, invoice_id: UUID) -> tuple[str, ...]:
        with session_scope(self._session_factory) as database:
            return tuple(
                database.scalars(
                    select(TariffFile.storage_key)
                    .join(TariffSelectionFile, TariffSelectionFile.tariff_file_id == TariffFile.id)
                    .join(
                        TariffSelectionRun,
                        TariffSelectionRun.id == TariffSelectionFile.selection_run_id,
                    )
                    .where(TariffSelectionRun.invoice_id == invoice_id)
                    .order_by(TariffSelectionFile.created_at, TariffSelectionFile.id)
                ).all()
            )

    @staticmethod
    def _record(model: TariffSelectionRun) -> TariffSelectionRecord:
        return TariffSelectionRecord(
            invoice_id=model.invoice_id,
            status=TariffSelectionStatus(model.status),
            selected_tariff_ids=tuple(item.tariff_file_id for item in model.files),
            confidence=model.confidence,
            threshold=model.threshold,
            reason=model.reason,
            ai_call_id=model.ai_call_id,
            created_at=model.created_at,
        )
