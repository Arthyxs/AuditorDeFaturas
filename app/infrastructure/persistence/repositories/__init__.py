"""Persistence repository building blocks."""

from app.infrastructure.persistence.repositories.base import SqlAlchemyRepository
from app.infrastructure.persistence.repositories.email import PostgreSQLMailIngestionRepository
from app.infrastructure.persistence.repositories.jobs import JobLeaseError, PostgreSQLJobQueue

__all__ = [
    "JobLeaseError",
    "PostgreSQLJobQueue",
    "PostgreSQLMailIngestionRepository",
    "SqlAlchemyRepository",
]
