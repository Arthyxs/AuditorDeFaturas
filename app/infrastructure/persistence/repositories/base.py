"""Generic SQLAlchemy repository building block."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.persistence.models import Base


class SqlAlchemyRepository[ModelT: Base]:
    """Minimal typed repository used by entity-specific repositories later."""

    def __init__(self, session: Session, model_type: type[ModelT]) -> None:
        self._session = session
        self._model_type = model_type

    def add(self, instance: ModelT) -> None:
        """Stage an entity in the current transaction."""
        self._session.add(instance)

    def get(self, identifier: Any) -> ModelT | None:
        """Load an entity by its declared primary key."""
        return self._session.get(self._model_type, identifier)

    def list_all(self) -> list[ModelT]:
        """List all entities for simple repositories and tests."""
        return list(self._session.scalars(select(self._model_type)).all())
