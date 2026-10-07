"""SQLAlchemy async unit of work for SQLite write-side transactions."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Any, Self

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncSessionTransaction,
    async_sessionmaker,
)

from ....application.integration.outbox import Outbox
from ....application.ports import UnitOfWork
from ....domain import Aggregate, DomainEvent
from ...clock import SystemClock
from .outbox import DEFAULT_MAX_ATTEMPTS, SqlAlchemyOutbox


class SqlAlchemyUnitOfWork(UnitOfWork):
    """SQLAlchemy-backed unit of work."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        max_attempts: int | None = DEFAULT_MAX_ATTEMPTS,
        now: Callable[[], datetime] = SystemClock.now,
    ) -> None:
        """Store the session factory and the outbox's retry policy."""
        self._session_factory = session_factory
        self._max_attempts = max_attempts
        self._now = now
        self._session: AsyncSession | None = None
        self._transaction: AsyncSessionTransaction | None = None
        self._tracked: list[Aggregate[Any]] = []
        self._outbox: SqlAlchemyOutbox | None = None

    @property
    def session(self) -> AsyncSession:
        """Expose the active session to infrastructure repository adapters."""
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._session

    @property
    def outbox(self) -> Outbox:
        """Return the outbox bound to this transaction."""
        if self._outbox is None:
            raise RuntimeError("UnitOfWork is not active")
        return self._outbox

    async def __aenter__(self) -> Self:
        """Begin the transaction."""
        if self._session is not None:
            raise RuntimeError("UnitOfWork cannot be re-entered")
        self._session = self._session_factory()
        self._transaction = await self._session.begin()
        self._outbox = SqlAlchemyOutbox(
            self._session, max_attempts=self._max_attempts, now=self._now
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit or roll back the transaction."""
        assert self._session is not None
        try:
            if self._transaction is not None and self._transaction.is_active:
                if exc_type is None:
                    await self._transaction.commit()
                else:
                    await self._transaction.rollback()
        finally:
            await self._session.close()
            self._session = None
            self._transaction = None
            self._outbox = None

    def track(self, aggregate: Aggregate[Any]) -> None:
        """Register an aggregate once so its events are included in this commit."""
        if self._session is None:
            raise RuntimeError("UnitOfWork is not active")
        if not any(item is aggregate for item in self._tracked):
            self._tracked.append(aggregate)

    def pull_events(self) -> list[DomainEvent]:
        """Drain recorded domain events from all tracked aggregates."""
        events: list[DomainEvent] = []
        for aggregate in self._tracked:
            events.extend(aggregate.pull_events())
        return events

    async def commit(self) -> None:
        """Commit exactly once; the context manager then only closes the session."""
        if self._transaction is None or not self._transaction.is_active:
            raise RuntimeError("No active transaction to commit")
        await self._transaction.commit()

    async def rollback(self) -> None:
        """Roll back the active transaction."""
        if self._transaction is not None and self._transaction.is_active:
            await self._transaction.rollback()
