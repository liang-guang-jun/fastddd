"""Tests for the shared inbox receipt primitive and the consumer that uses it."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastddd.application.integration.outbox import IntegrationEvent
from fastddd.application.messaging.handler import EventHandler
from fastddd.infrastructure.inbox import (
    InboxConsumer,
    claim_inbox_message,
    projection_consumer,
)
from fastddd.infrastructure.persistence.sqlalchemy.maintenance import purge_inbox
from fastddd.infrastructure.persistence.sqlalchemy.models import InboxRecord
from fastddd.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from tests.infrastructure.persistence._helpers import (
    Counter,
    CounterId,
    CounterRecord,
    CounterRepository,
)


async def test_a_receipt_is_recorded_only_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = uuid4()

    async with session_factory() as session:
        assert await claim_inbox_message(session, "counters", event_id) is True
        await session.commit()

    async with session_factory() as session:
        assert await claim_inbox_message(session, "counters", event_id) is False


async def test_each_consumer_gets_its_own_receipt(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event_id = uuid4()

    async with session_factory() as session:
        assert await claim_inbox_message(session, "counters", event_id) is True
        assert await claim_inbox_message(session, "totals", event_id) is True


async def test_purge_inbox_removes_only_old_receipts(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    cutoff = datetime(2026, 1, 1, tzinfo=UTC)
    fresh = cutoff + timedelta(days=1)

    async with session_factory() as session:
        session.add_all(
            [
                InboxRecord(
                    consumer="counters",
                    event_id=str(uuid4()),
                    processed_at=cutoff - timedelta(days=1),
                ),
                InboxRecord(
                    consumer="counters",
                    event_id=str(uuid4()),
                    processed_at=fresh,
                ),
            ]
        )
        await session.commit()

        assert await purge_inbox(session, cutoff) == 1

        remaining = list(await session.scalars(select(InboxRecord)))

    assert [row.processed_at.replace(tzinfo=UTC) for row in remaining] == [fresh]


async def test_a_receipt_taken_before_any_write_is_taken_back_by_a_rollback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # The engine emits BEGIN itself, so a receipt taken as the first statement
    # still nests in a transaction a rollback can undo. Without that, a consumer
    # that claimed and then failed would never see the event again.
    event_id = uuid4()

    async with session_factory() as session:
        assert await claim_inbox_message(session, "counters", event_id) is True
        await session.rollback()

    async with session_factory() as session:
        assert await claim_inbox_message(session, "counters", event_id) is True


async def test_a_receipt_taken_after_a_write_is_taken_back_by_a_rollback(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # The same claim, one statement later, after the caller's own write: the
    # savepoint still nests, so the rollback takes the receipt back with it.
    event_id = uuid4()
    other_id = uuid4()

    async with session_factory() as session:
        assert await claim_inbox_message(session, "totals", other_id) is True
        assert await claim_inbox_message(session, "counters", event_id) is True
        await session.rollback()

    async with session_factory() as session:
        assert await claim_inbox_message(session, "counters", event_id) is True


@pytest.mark.integration
async def test_a_writer_racing_an_uncommitted_claim_is_told_no(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The constraint, not the read, is what makes a claim safe.

    The second writer checks while the first has still not committed, so its read
    cannot see the row and what settles the race is its insert against the unique
    constraint -- the branch a single-connection test can never reach.
    """
    event_id = uuid4()

    async with (
        postgres_session_factory() as first,
        postgres_session_factory() as second,
    ):
        assert await claim_inbox_message(first, "counters", event_id) is True

        racing = asyncio.create_task(claim_inbox_message(second, "counters", event_id))
        # Long enough for the second writer to pass its read and block on the
        # uncommitted row; the outcome does not depend on the exact moment.
        await asyncio.sleep(0.1)
        await first.commit()

        assert await racing is False

    async with postgres_session_factory() as session:
        claims = list(
            await session.scalars(
                select(InboxRecord.id).where(
                    InboxRecord.consumer == "counters",
                    InboxRecord.event_id == str(event_id),
                )
            )
        )

    assert len(claims) == 1


def _event() -> IntegrationEvent:
    """Return an integration event to deliver."""
    return IntegrationEvent(
        event_type="counter.changed",
        payload={"total": 2},
        aggregate_type="Counter",
        aggregate_id="1",
        aggregate_version=1,
        event_id=uuid4(),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class _Consumer(EventHandler[IntegrationEvent]):
    """A consumer that writes a counter and can be told to fail."""

    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.handled: list[str] = []

    async def handle(self, event: IntegrationEvent) -> None:
        """Write a counter, record the delivery, and fail when asked to."""
        self.handled.append(str(event.event_id))
        counter = Counter(CounterId(1), total=1)
        counter.increment()
        await CounterRepository().save(counter)
        if self.fails:
            raise RuntimeError("consumer failed")


async def test_a_consumer_handles_a_redelivery_once(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    handler = _Consumer()
    consumer = InboxConsumer("counters", handler, uow_factory)
    event = _event()

    await consumer.handle(event)
    await consumer.handle(event)

    assert handler.handled == [str(event.event_id)]
    async with session_factory() as session:
        counters = list(await session.scalars(select(CounterRecord)))

    assert [row.total for row in counters] == [2]


async def test_a_failing_consumer_leaves_no_receipt_and_can_retry(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    handler = _Consumer(fails=True)
    consumer = InboxConsumer("counters", handler, uow_factory)
    event = _event()

    with pytest.raises(RuntimeError, match="consumer failed"):
        await consumer.handle(event)

    # Nothing committed: neither the write nor the receipt, so a retry is allowed.
    async with session_factory() as session:
        assert list(await session.scalars(select(CounterRecord))) == []
        assert list(await session.scalars(select(InboxRecord))) == []

    handler.fails = False
    await consumer.handle(event)

    assert handler.handled == [str(event.event_id), str(event.event_id)]
    async with session_factory() as session:
        counters = list(await session.scalars(select(CounterRecord)))

    assert [row.total for row in counters] == [2]


def test_the_consumer_reports_its_name(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    consumer = InboxConsumer("counters", _Consumer(), uow_factory)

    assert consumer.name == "counters"


def test_the_projection_consumer_names_its_receipts_under_the_prefix(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    projection = projection_consumer("counters", _Consumer(), uow_factory)

    # Pinned on purpose: the name is the receipt key, so changing the prefix
    # would orphan every receipt already written.
    assert projection.name == "projection:counters"


async def test_a_projection_handles_a_redelivery_once(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    handler = _Consumer()
    projection = projection_consumer("counters", handler, uow_factory)
    event = _event()

    await projection.handle(event)
    await projection.handle(event)

    assert handler.handled == [str(event.event_id)]
    async with session_factory() as session:
        counters = list(await session.scalars(select(CounterRecord)))

    assert [row.total for row in counters] == [2]


async def test_a_projection_and_a_consumer_sharing_a_name_never_collide(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    # The reason a projection is namespaced: sharing a name would make the two
    # share -- and therefore suppress -- each other's receipts.
    projection = _Consumer()
    consumer = _Consumer()
    event = _event()

    await projection_consumer("counters", projection, uow_factory).handle(event)
    await InboxConsumer("counters", consumer, uow_factory).handle(event)

    assert projection.handled == [str(event.event_id)]
    assert consumer.handled == [str(event.event_id)]
