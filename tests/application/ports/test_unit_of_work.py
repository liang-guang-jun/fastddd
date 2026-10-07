"""Tests for the unit-of-work transactional boundary."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID

from fastddd.application.integration.outbox import IntegrationEvent, Outbox
from fastddd.application.ports.unit_of_work import UnitOfWork
from fastddd.domain import Aggregate, DomainEvent, EntityId


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
    """Outbox that only records what was appended."""

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


class InMemoryUnitOfWork(UnitOfWork):
    """Unit of work tracking aggregates and draining their events."""

    def __init__(self) -> None:
        self._outbox = FakeOutbox()
        self._tracked: list[Aggregate[Any]] = []

    @property
    def outbox(self) -> Outbox:
        return self._outbox

    def track(self, aggregate: Aggregate[Any]) -> None:
        if aggregate not in self._tracked:
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


def test_the_unit_of_work_contract_is_abstract() -> None:
    assert inspect.isabstract(UnitOfWork)


async def test_entering_the_transaction_returns_the_same_unit_of_work() -> None:
    uow = InMemoryUnitOfWork()

    async with uow as entered:
        assert entered is uow


def test_the_outbox_is_available_before_any_commit() -> None:
    assert isinstance(InMemoryUnitOfWork().outbox, FakeOutbox)


def test_pulling_with_nothing_tracked_returns_no_events() -> None:
    assert InMemoryUnitOfWork().pull_events() == []


def test_pulling_drains_every_tracked_aggregate_exactly_once() -> None:
    uow = InMemoryUnitOfWork()
    account = Account(AccountId(1))
    account.rename("ada")
    uow.track(account)

    assert uow.pull_events() == [Renamed(name="ada")]
    assert uow.pull_events() == []


def test_tracking_the_same_aggregate_twice_pulls_its_events_once() -> None:
    uow = InMemoryUnitOfWork()
    account = Account(AccountId(1))
    account.rename("ada")
    uow.track(account)
    uow.track(account)

    assert uow.pull_events() == [Renamed(name="ada")]
