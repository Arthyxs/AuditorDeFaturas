"""Durable background-job domain types."""

from app.domain.jobs.models import JobRecord, JobStatus

__all__ = ["JobRecord", "JobStatus"]
