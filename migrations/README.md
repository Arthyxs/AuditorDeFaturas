# Database migrations

Alembic is the only supported mechanism for PostgreSQL schema changes. The first revision
establishes migration lineage without creating product tables ahead of their owning
milestones.
