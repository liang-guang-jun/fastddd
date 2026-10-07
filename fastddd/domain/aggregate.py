"""Aggregate abstraction: the root of a consistency boundary."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable
from datetime import datetime

from .entity import Entity
from .error import AggregateDeletedError
from .event import DomainEvent


class SoftDeletable(ABC):
    """Mixin giving an aggregate a terminal soft-delete flag.

    The flag doubles as audit data: ``deleted_at`` stays ``None`` while the
    aggregate is live, and rows are never physically removed. Deletion is the
    last state change an aggregate can make, so every other behaviour guards
    against it.
    """

    _deleted_at: datetime | None = None

    @property
    def deleted_at(self) -> datetime | None:
        """Return the moment this aggregate was deleted, if it was."""
        return self._deleted_at

    @property
    def is_deleted(self) -> bool:
        """Return whether this aggregate is soft-deleted."""
        return self._deleted_at is not None

    def delete(self, *, at: datetime) -> None:
        """Soft-delete the aggregate; deleting a deleted aggregate is a no-op."""
        if self._deleted_at is not None:
            return

        self._deleted_at = at
        self._on_deleted(at)

    def _require_not_deleted(self, *, action: str) -> None:
        """Reject a state change on an aggregate that was already deleted."""
        if self._deleted_at is not None:
            raise AggregateDeletedError(
                f"{type(self).__name__} is deleted and cannot {action}"
            )

    @abstractmethod
    def _on_deleted(self, at: datetime) -> None:
        """Record the deletion of the concrete aggregate."""
        raise NotImplementedError


class Aggregate[TId: Hashable](Entity[TId], SoftDeletable):
    """Base class for aggregate roots.

    An aggregate is a transactional boundary. All external access
    must go through the aggregate root. Domain events are collected
    by the root and published by the application layer after commit.
    """

    def __init__(self) -> None:
        """Initialize the domain event buffer."""
        self._domain_events: list[DomainEvent] = []

    def _record_event(self, event: DomainEvent) -> None:
        """Record a domain event to be published later."""
        self._domain_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Return and clear all recorded domain events."""
        events = self._domain_events
        self._domain_events = []
        return events

    def _on_deleted(self, at: datetime) -> None:
        """React to a soft-deletion; nothing by default.

        ``SoftDeletable`` leaves this hook abstract so a direct mixin user must
        decide what deletion means. An aggregate, though, is usable as-is, so the
        default is to keep no extra bookkeeping; a concrete aggregate overrides it
        when a deletion has to be recorded or cascaded.
        """


class VersionedAggregate[TId: Hashable](Aggregate[TId]):
    """Base class for aggregates with a version number.

    The version is incremented on every state change and used by
    the persistence layer to detect concurrent modifications
    (optimistic locking) or to support event sourcing.
    """

    def __init__(self, *, version: int = 0) -> None:
        """Initialize the aggregate with version zero."""
        super().__init__()
        self._version = version

    @property
    def version(self) -> int:
        """Return the current version of this aggregate."""
        return self._version

    def _record_state_change(self, event: DomainEvent) -> None:
        """Advance version and retain the event after a state mutation."""
        self._version += 1

        self._record_event(event)

    def _restore_version(self, version: int) -> None:
        """Set a persisted version without creating an event."""
        if version < 0:
            raise ValueError("version must be non-negative")
        self._version = version
