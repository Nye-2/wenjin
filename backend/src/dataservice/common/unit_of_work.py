"""DataService unit-of-work boundary."""

from __future__ import annotations

from types import TracebackType

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.database.session import get_async_session_factory
from src.dataservice.domains.operations.repository import OperationsRepository


class DataServiceUnitOfWork:
    """Own one database transaction for a DataService command.

    Repositories never commit by themselves. Command handlers call
    ``commit()`` once after all aggregate updates and outbox writes are staged.
    Exiting without commit rolls the transaction back.
    """

    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
        session: AsyncSession | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._provided_session = session
        self.session: AsyncSession | None = None
        self.operations: OperationsRepository | None = None
        self._committed = False

    async def __aenter__(self) -> DataServiceUnitOfWork:
        self.session = self._provided_session or (self._session_factory or get_async_session_factory())()
        self.operations = OperationsRepository(self.session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self.session is None:
            return
        try:
            if exc_type is not None or not self._committed:
                await self.session.rollback()
        finally:
            if self._provided_session is None:
                await self.session.close()

    async def commit(self) -> None:
        """Commit the current transaction."""
        if self.session is None:
            raise RuntimeError("DataServiceUnitOfWork has not been entered")
        await self.session.commit()
        self._committed = True

    async def rollback(self) -> None:
        """Rollback the current transaction."""
        if self.session is None:
            raise RuntimeError("DataServiceUnitOfWork has not been entered")
        await self.session.rollback()
        self._committed = False

    @property
    def required_session(self) -> AsyncSession:
        """Return the active session or fail fast when used outside the context."""
        if self.session is None:
            raise RuntimeError("DataServiceUnitOfWork has not been entered")
        return self.session

    def __repr__(self) -> str:
        return f"{type(self).__name__}(entered={self.session is not None}, committed={self._committed})"
