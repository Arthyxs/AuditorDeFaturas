"""Persistence repository building blocks."""

from app.infrastructure.persistence.repositories.ai import PostgreSQLAITelemetryRepository
from app.infrastructure.persistence.repositories.base import SqlAlchemyRepository
from app.infrastructure.persistence.repositories.email import PostgreSQLMailIngestionRepository
from app.infrastructure.persistence.repositories.email_classification import (
    PostgreSQLEmailClassificationRepository,
)
from app.infrastructure.persistence.repositories.invoice_intake import (
    PostgreSQLIMAPInvoiceSourceRepository,
    PostgreSQLInvoiceIntakeRepository,
)
from app.infrastructure.persistence.repositories.jobs import JobLeaseError, PostgreSQLJobQueue
from app.infrastructure.persistence.repositories.tariff_selection import (
    PostgreSQLTariffSelectionRepository,
)

__all__ = [
    "JobLeaseError",
    "PostgreSQLAITelemetryRepository",
    "PostgreSQLJobQueue",
    "PostgreSQLIMAPInvoiceSourceRepository",
    "PostgreSQLInvoiceIntakeRepository",
    "PostgreSQLMailIngestionRepository",
    "PostgreSQLTariffSelectionRepository",
    "PostgreSQLEmailClassificationRepository",
    "SqlAlchemyRepository",
]
