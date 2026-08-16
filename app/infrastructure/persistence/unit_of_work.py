"""Explicit SQLAlchemy unit-of-work transaction boundary."""

from types import TracebackType

from sqlalchemy.orm import Session

from app.infrastructure.persistence.session import SessionFactory


class SqlAlchemyUnitOfWork:
    """Own one session and make commit/rollback behavior explicit."""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory
        self.session: Session
        self._committed = False

    def __enter__(self) -> "SqlAlchemyUnitOfWork":
        self.session = self._session_factory()
        self._committed = False
        return self

    def __exit__(
        self,
        exception_type: type[BaseException] | None,
        exception: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if exception_type is not None or not self._committed:
            self.session.rollback()
        self.session.close()

    def commit(self) -> None:
        """Commit the current transaction."""
        self.session.commit()
        self._committed = True

    def rollback(self) -> None:
        """Roll back the current transaction explicitly."""
        self.session.rollback()
