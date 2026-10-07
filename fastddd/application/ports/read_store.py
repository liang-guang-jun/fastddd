"""Port for read-side queries returning DTOs."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ReadStore[TQuery, TResult](ABC):
    """Read-side port returning DTOs rather than aggregates."""

    @abstractmethod
    async def query(self, query: TQuery) -> TResult:
        """Return a projection shaped for the query use case."""
        raise NotImplementedError
