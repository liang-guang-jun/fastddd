"""Tests for the shared application helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID, uuid4

import pytest

from fastddd.application.execution.context import MessageMetadata
from fastddd.application.integration.outbox import IntegrationEvent, Outbox
from fastddd.application.ports.unit_of_work import UnitOfWork
from fastddd.application.support import (
    enqueue_integration_events,
    require_found,
)
from fastddd.domain import Aggregate, DomainEvent, EntityId
from fastddd.domain.error import NotFoundError


class AccountId(EntityId[int]):
    """Identity of the sample aggregate."""

    def __init__(self, value: int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value


@dataclass(frozen=True, slots=True)
class Renamed(DomainEvent):
    """Event recorded by the sample aggregate."""

    name: str


class Account(Aggregate[int]):
    """Aggregate recording an event on rename."""

    def __init__(self, account_id: AccountId) -> None:
        super().__init__()
        self._account_id = account_id

    @property
    def id(self) -> EntityId[int]:
        return self._account_id

    def rename(self, name: str) -> None:
        """Rename, recording the fact."""
        self._record_event(Renamed(name=name))


class FakeOutbox(Outbox):
    """Outbox recording what was appended."""

    def __init__(self) -> None:
        self.appended: list[IntegrationEvent] = []

    async def append(self, event: IntegrationEvent) -> None:
        self.appended.append(event)

    async def claim(
        self,
        limit: int,
        worker: str,
        lease_seconds: float,
    ) -> list[IntegrationEvent]:
        return self.appended[:limit]

    async def mark_as_published(self, event_id: UUID, worker: str) -> None:
        pass

    async def mark_failed(self, event_id: UUID, error: str, worker: str) -> None:
        pass

    async def purge_published(self, before: datetime) -> int:
        return 0


class FakeUnitOfWork(UnitOfWork):
    """Unit of work tracking aggregates and draining their events."""

    def __init__(self) -> None:
        self._outbox = FakeOutbox()
        self._tracked: list[Aggregate[Any]] = []

    @property
    def outbox(self) -> Outbox:
        return self._outbox

    def track(self, aggregate: Aggregate[Any]) -> None:
        self._tracked.append(aggregate)

    def pull_events(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for aggregate in self._tracked:
            events.extend(aggregate.pull_events())
        return events

    async def __aenter__(self) -> Self:
        """Enter the transaction."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Exit the transaction."""

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class RenamedMapper:
    """Mapper turning the sample event into one integration event."""

    def __init__(self) -> None:
        self.metadata: list[MessageMetadata | None] = []

    def map(
        self,
        event: DomainEvent,
        metadata: MessageMetadata | None,
    ) -> list[IntegrationEvent]:
        self.metadata.append(metadata)
        name = event.name if isinstance(event, Renamed) else ""
        return [
            IntegrationEvent(
                event_type="account.renamed",
                payload={"name": name},
                aggregate_type="Account",
                aggregate_id="1",
                aggregate_version=0,
                event_id=uuid4(),
                occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]


def request_metadata() -> MessageMetadata:
    """Return metadata for a sample request."""
    return MessageMetadata(
        message_id="message-1",
        correlation_id=None,
        causation_id=None,
        principal_id=None,
        tenant_id=None,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_require_found_returns_the_loaded_aggregate() -> None:
    async def load() -> str | None:
        return "account"

    loaded = await require_found(load(), subject="account", error_type=NotFoundError)

    assert loaded == "account"


async def test_require_found_raises_the_supplied_error_type() -> None:
    class AccountMissingError(NotFoundError):
        """A context-specific not-found error."""

    async def load() -> str | None:
        return None

    with pytest.raises(AccountMissingError, match="account does not exist"):
        await require_found(load(), subject="account", error_type=AccountMissingError)


async def test_enqueue_translates_and_appends_every_pulled_event() -> None:
    uow = FakeUnitOfWork()
    account = Account(AccountId(1))
    account.rename("ada")
    uow.track(account)
    mapper = RenamedMapper()

    await enqueue_integration_events(uow, mapper)

    pending = await uow.outbox.claim(10, "test-worker", 30.0)
    assert [event.event_type for event in pending] == ["account.renamed"]
    assert mapper.metadata == [None]


async def test_enqueue_appends_nothing_without_events() -> None:
    uow = FakeUnitOfWork()

    await enqueue_integration_events(uow, RenamedMapper())

    assert await uow.outbox.claim(10, "test-worker", 30.0) == []


async def test_enqueue_forwards_the_metadata() -> None:
    uow = FakeUnitOfWork()
    account = Account(AccountId(1))
    account.rename("ada")
    uow.track(account)
    mapper = RenamedMapper()
    metadata = request_metadata()

    await enqueue_integration_events(uow, mapper, metadata)

    assert mapper.metadata == [metadata]
