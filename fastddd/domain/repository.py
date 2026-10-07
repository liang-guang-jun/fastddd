"""Domain collection contract without persistence concerns."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from typing import Any

from .aggregate import Aggregate
from .entity import EntityId


class AggregateRepository[TAggregate: Aggregate[Any], TId: Hashable](ABC):
    """Asynchronous repository contract for loading and storing aggregates.

    Storing is expressed as a single ``save``: the aggregate itself knows
    whether it is new, modified, or soft-deleted, and the repository persists
    whatever state it is in. Physical removal, when a use case genuinely needs
    it, is a separate ``purge``.
    """

    @abstractmethod
    async def get(self, id: EntityId[TId]) -> TAggregate | None:
        """Return the aggregate with the given identity, if it exists."""
        ...

    @abstractmethod
    async def save(self, aggregate: TAggregate) -> None:
        """Persist the aggregate in its current state.

        Inserts a new aggregate, updates an existing one, and records a soft
        delete when the aggregate is deleted. A versioned aggregate is written
        only if its version still matches the stored one.

        Raises:
            InvariantViolationError: If a new aggregate's identity already exists.
            ConcurrencyError: If another writer changed the aggregate first.
        """
        ...

    @abstractmethod
    async def purge(self, id: EntityId[TId]) -> None:
        """Physically remove the aggregate.

        Only for compliance or cleanup. Normal deletion is
        ``aggregate.delete(at=...)`` followed by ``save``.
        """
        ...
