"""Persistence model conventions."""

from app.infrastructure.persistence.models.ai import AICall, AIPriceVersion
from app.infrastructure.persistence.models.auth import AuthSession, User, UserRole
from app.infrastructure.persistence.models.base import (
    Base,
    CreatedAtMixin,
    UpdatedAtMixin,
    UUIDPrimaryKeyMixin,
)
from app.infrastructure.persistence.models.email import MailAccount, MailAttachment, MailMessage
from app.infrastructure.persistence.models.intake import (
    DocumentChargeItem,
    Invoice,
    InvoiceDocument,
    InvoiceSubmission,
    Partner,
    SubmissionFile,
)
from app.infrastructure.persistence.models.jobs import ProcessingJob
from app.infrastructure.persistence.models.tariff_selection import (
    PendingItem,
    TariffSelectionFile,
    TariffSelectionRun,
)
from app.infrastructure.persistence.models.tariffs import TariffFile

__all__ = [
    "AuthSession",
    "AICall",
    "AIPriceVersion",
    "Base",
    "CreatedAtMixin",
    "MailAccount",
    "MailAttachment",
    "MailMessage",
    "DocumentChargeItem",
    "Invoice",
    "InvoiceDocument",
    "InvoiceSubmission",
    "Partner",
    "PendingItem",
    "ProcessingJob",
    "TariffFile",
    "TariffSelectionFile",
    "TariffSelectionRun",
    "SubmissionFile",
    "UpdatedAtMixin",
    "UUIDPrimaryKeyMixin",
    "User",
    "UserRole",
]
