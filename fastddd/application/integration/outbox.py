"""Outbox abstraction for reliable integration-event publication."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

type JsonValue = (
    bool | int | float | str | list[JsonValue] | dict[str, JsonValue] | None
)

UNVERSIONED = 0
"""The aggregate version of a fact that makes no ordering claim.

``aggregate_version`` exists so a consumer can reject an event that arrives after
a newer one. A context whose aggregates are not versioned says so with this
rather than inventing a number, and a consumer that needs ordering must not rely
on such an event.
"""


@dataclass(frozen=True, slots=True)
class IntegrationEvent:
    """Integration-event envelope persisted by the outbox.

    ``aggregate_version`` orders the facts about one aggregate: a consumer can
    reject an event that arrived after a newer one. A fact that makes no such claim
    says so with :data:`UNVERSIONED`.
    """

    event_type: str
    payload: dict[str, JsonValue]
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    event_id: UUID
    occurred_at: datetime
    schema_version: int = 1
    correlation_id: str | None = None
    causation_id: str | None = None
    tenant_id: str | None = None

    def __post_init__(self) -> None:
        """Validate stable integration-event metadata."""
        if not self.event_type:
            raise ValueError("event_type is required")

        if self.schema_version < 1:
            raise ValueError("schema_version must be >= 1")

        if self.aggregate_version < 0:
            raise ValueError("aggregate_version must be >= 0")

        if self.occurred_at.tzinfo is None:
            raise ValueError("occurred_at must be timezone-aware")


class Outbox(ABC):
    """Persist, claim, and settle integration events awaiting publication.

    Claiming is a time-boxed lease: a worker takes a batch for itself, so two
    workers never publish the same row, and a lease that outlives its worker is
    recovered by the next claim rather than stranding the event. Settling is
    guarded by the claiming worker, so a worker whose lease was reclaimed cannot
    overwrite what its successor did.
    """

    @abstractmethod
    async def append(self, event: IntegrationEvent) -> None:
        """Append an event to the outbox in the current transaction."""
        raise NotImplementedError

    @abstractmethod
    async def claim(
        self,
        limit: int,
        worker: str,
        lease_seconds: float,
    ) -> list[IntegrationEvent]:
        """Lease up to ``limit`` ready events to ``worker`` for ``lease_seconds``.

        Also recovers events whose lease has expired, so an event abandoned by a
        stopped worker becomes publishable again.
        """
        raise NotImplementedError

    @abstractmethod
    async def mark_as_published(self, event_id: UUID, worker: str) -> None:
        """Mark an event published, if ``worker`` still holds its lease."""
        raise NotImplementedError

    @abstractmethod
    async def mark_failed(self, event_id: UUID, error: str, worker: str) -> None:
        """Record a failed attempt and schedule a retry, if ``worker`` holds the lease."""
        raise NotImplementedError

    @abstractmethod
    async def purge_published(self, before: datetime) -> int:
        """Delete events published before ``before`` and return how many went."""
        raise NotImplementedError
