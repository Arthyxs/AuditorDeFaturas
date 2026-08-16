"""Safe test-process configuration defaults."""

import os

os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("APP_SECRET_KEY", "test-app-secret-key-000000000000000000000000")
os.environ.setdefault("POSTGRES_PASSWORD", "test-postgres-password-000000000000000000000")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://invoice_auditor:test@localhost:5432/invoice_auditor_test",
)
