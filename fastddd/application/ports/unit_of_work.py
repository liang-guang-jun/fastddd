"""UnitOfWork abstraction: the transactional boundary of a single use case."""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

from ...domain import Aggregate, DomainEvent

if TYPE_CHECKING:
    from ..integration.outbox import Outbox


class UnitOfWork(ABC):
    """Transactional boundary for a single use case.

    Defines only what every unit of work must provide: a transaction
    scope and an outbox bound to that transaction. Repositories are
    exposed by concrete implementations in whatever way suits them.
    """

    @property
    @abstractmethod
    def outbox(self) -> Outbox:
        """Return the outbox bound to this transaction."""
        raise NotImplementedError

    @abstractmethod
    def track(self, aggregate: Aggregate[Any]) -> None:
        """Track an aggregate whose transient events belong to this transaction."""
        raise NotImplementedError

    @abstractmethod
    def pull_events(self) -> list[DomainEvent]:
        """Pull pending events from every tracked aggregate exactly once."""
        raise NotImplementedError

    @abstractmethod
    async def __aenter__(self) -> Self:
        """Begin the transaction."""
        raise NotImplementedError

    @abstractmethod
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit or roll back the transaction."""
        raise NotImplementedError

    @abstractmethod
    async def commit(self) -> None:
        """Commit the current transaction."""
        raise NotImplementedError

    @abstractmethod
    async def rollback(self) -> None:
        """Roll back the current transaction."""
        raise NotImplementedError
