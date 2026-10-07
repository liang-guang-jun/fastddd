"""Tests for the polling outbox dispatcher."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastddd.application.execution.context import current_unit_of_work_or_none
from fastddd.application.integration.outbox import IntegrationEvent
from fastddd.application.integration.publisher import EventPublisher
from fastddd.infrastructure.messaging import OutboxDispatcher
from fastddd.infrastructure.persistence.sqlalchemy.models import OutboxRecord
from fastddd.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SqlAlchemyUnitOfWork,
)


class _Publisher(EventPublisher):
    """Record what is published, refusing the types it was told to refuse."""

    def __init__(self, refuse: str | None = None) -> None:
        self.refuse = refuse
        self.delivered: list[str] = []
        self.transaction_bound: list[bool] = []

    async def publish(self, event: IntegrationEvent) -> None:
        self.transaction_bound.append(current_unit_of_work_or_none() is not None)
        if event.event_type == self.refuse:
            raise RuntimeError(f"consumer refused {event.event_type}")
        self.delivered.append(event.event_type)

    async def publish_all(self, events: list[IntegrationEvent]) -> None:
        for event in events:
            await self.publish(event)


async def _seed(
    session_factory: async_sessionmaker[AsyncSession], *event_types: str
) -> list[str]:
    """Write pending outbox rows and return their event ids."""
    event_ids = [str(uuid4()) for _ in event_types]
    async with session_factory() as session:
        for event_id, event_type in zip(event_ids, event_types, strict=True):
            session.add(
                OutboxRecord(
                    event_id=event_id,
                    event_type=event_type,
                    schema_version=1,
                    aggregate_type="Account",
                    aggregate_id="1",
                    aggregate_version=1,
                    occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
                    payload={"name": "acme"},
                    next_attempt_at=datetime.now(UTC),
                )
            )
        await session.commit()

    return event_ids


async def _queued(
    session_factory: async_sessionmaker[AsyncSession],
) -> list[OutboxRecord]:
    """Return every outbox row, in key order."""
    async with session_factory() as session:
        statement = select(OutboxRecord).order_by(OutboxRecord.id)

        return list((await session.execute(statement)).scalars())


def test_a_batch_size_below_one_is_refused(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    with pytest.raises(ValueError, match="batch_size must be positive"):
        OutboxDispatcher(uow_factory, _Publisher(), batch_size=0)


async def test_dispatching_an_empty_outbox_delivers_nothing(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    assert await OutboxDispatcher(uow_factory, _Publisher()).dispatch_once() == 0


async def test_a_ready_batch_is_published_and_marked(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_factory, "account.opened", "account.closed")
    publisher = _Publisher()
    dispatcher = OutboxDispatcher(uow_factory, publisher)

    assert await dispatcher.dispatch_once() == 2
    assert publisher.delivered == ["account.opened", "account.closed"]
    assert [row.status for row in await _queued(session_factory)] == [
        "published",
        "published",
    ]

    # Nothing is left to publish, so a second pass is idle.
    assert await dispatcher.dispatch_once() == 0


async def test_events_are_published_outside_the_read_transaction(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_factory, "account.opened")
    publisher = _Publisher()

    await OutboxDispatcher(uow_factory, publisher).dispatch_once()

    assert publisher.transaction_bound == [False]


async def test_only_the_configured_batch_is_taken_at_a_time(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_factory, *["account.opened"] * 3)
    dispatcher = OutboxDispatcher(uow_factory, _Publisher(), batch_size=1)

    assert await dispatcher.dispatch_once() == 1
    assert [row.status for row in await _queued(session_factory)] == [
        "published",
        "pending",
        "pending",
    ]


async def test_a_refused_event_is_recorded_for_a_retry(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_factory, "account.opened")
    dispatcher = OutboxDispatcher(uow_factory, _Publisher(refuse="account.opened"))

    assert await dispatcher.dispatch_once() == 0

    row = (await _queued(session_factory))[0]

    assert row.status == "pending"
    assert row.attempts == 1
    assert row.last_error == "consumer refused account.opened"


async def test_one_refusal_does_not_hold_up_the_rest_of_the_batch(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_factory, "account.opened", "account.closed")
    publisher = _Publisher(refuse="account.opened")
    dispatcher = OutboxDispatcher(uow_factory, publisher)

    assert await dispatcher.dispatch_once() == 1
    assert publisher.delivered == ["account.closed"]

    rows = await _queued(session_factory)

    assert [row.status for row in rows] == ["pending", "published"]


async def test_two_dispatchers_never_publish_the_same_event(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_factory, *["account.opened"] * 4)
    first, second = _Publisher(), _Publisher()
    left = OutboxDispatcher(uow_factory, first, worker="left")
    right = OutboxDispatcher(uow_factory, second, worker="right")

    await left.dispatch_once()
    await right.dispatch_once()

    # Four events in, four deliveries out: the lease stops a second dispatcher
    # from republishing what the first one took.
    assert sorted(first.delivered + second.delivered) == ["account.opened"] * 4


async def test_a_batch_is_settled_in_one_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _seed(session_factory, "account.opened", "account.closed")
    opened: list[SqlAlchemyUnitOfWork] = []

    def counting_factory() -> SqlAlchemyUnitOfWork:
        uow = SqlAlchemyUnitOfWork(session_factory)
        opened.append(uow)
        return uow

    dispatcher = OutboxDispatcher(counting_factory, _Publisher(refuse="account.opened"))

    assert await dispatcher.dispatch_once() == 1

    # One transaction to claim, one to settle the whole batch -- a success and a
    # failure cost the same two transactions, not one per event.
    assert len(opened) == 2


async def test_a_stale_claim_is_recovered_and_published(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_ids = await _seed(session_factory, "account.opened")

    # A dispatcher that claimed the event and then vanished, its lease long past.
    async with session_factory() as session:
        record = await session.scalar(
            select(OutboxRecord).where(OutboxRecord.event_id == event_ids[0])
        )
        assert record is not None
        record.status = "claimed"
        record.claimed_by = "gone"
        record.claimed_at = datetime.now(UTC) - timedelta(hours=1)
        record.lease_expires_at = datetime.now(UTC) - timedelta(hours=1)
        await session.commit()

    publisher = _Publisher()
    dispatcher = OutboxDispatcher(uow_factory, publisher, worker="recovery")

    assert await dispatcher.dispatch_once() == 1
    assert publisher.delivered == ["account.opened"]
