"""Tests for the SQLAlchemy outbox: append, claim, publish, back off, set aside."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastddd.application.integration.outbox import IntegrationEvent, JsonValue
from fastddd.infrastructure.persistence.sqlalchemy.models import OutboxRecord
from fastddd.infrastructure.persistence.sqlalchemy.outbox import (
    CLAIMED,
    DEAD,
    PENDING,
    PUBLISHED,
    SqlAlchemyOutbox,
)

OCCURRED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
WORKER = "test-worker"
LEASE_SECONDS = 30.0


class _Clock:
    """A clock the test advances by hand, so leases and backoff are testable."""

    def __init__(self) -> None:
        self.now = OCCURRED_AT

    def __call__(self) -> datetime:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)


async def _record(session: AsyncSession, event: IntegrationEvent) -> OutboxRecord:
    """Return the stored row for one event (event_id is unique, not the key)."""
    record = await session.scalar(
        select(OutboxRecord).where(OutboxRecord.event_id == str(event.event_id))
    )
    assert record is not None

    return record


def _event(
    *,
    event_type: str = "account.opened",
    payload: dict[str, JsonValue] | None = None,
    occurred_at: datetime = OCCURRED_AT,
) -> IntegrationEvent:
    """Return an integration event to append."""
    return IntegrationEvent(
        event_type=event_type,
        payload={"name": "acme"} if payload is None else payload,
        aggregate_type="Account",
        aggregate_id="1",
        aggregate_version=1,
        event_id=uuid4(),
        occurred_at=occurred_at,
        correlation_id="correlation-1",
        tenant_id="tenant-1",
    )


async def test_an_appended_event_is_relayed_exactly_as_written(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session)

        await outbox.append(event)

        assert await outbox.claim(10, WORKER, LEASE_SECONDS) == [event]


async def test_appending_leaves_committing_to_the_caller(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        await SqlAlchemyOutbox(session).append(_event())
        # No commit: the command that appended the event still owns the
        # transaction, so nothing is visible outside it yet.
        await session.rollback()

    async with session_factory() as session:
        assert await SqlAlchemyOutbox(session).claim(10, WORKER, LEASE_SECONDS) == []


async def test_claim_returns_events_in_the_order_they_were_appended(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first, second = (
        _event(event_type="account.opened"),
        _event(event_type="account.closed"),
    )

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session)
        await outbox.append(first)
        await outbox.append(second)

        relayed = await outbox.claim(10, WORKER, LEASE_SECONDS)

    assert [event.event_id for event in relayed] == [first.event_id, second.event_id]


async def test_claim_never_returns_more_than_the_limit(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session)
        for _ in range(3):
            await outbox.append(_event())

        assert len(await outbox.claim(2, WORKER, LEASE_SECONDS)) == 2


async def test_claim_refuses_a_limit_below_one(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(ValueError, match="limit must be positive"):
            await SqlAlchemyOutbox(session).claim(0, WORKER, LEASE_SECONDS)


async def test_publishing_removes_the_event_from_the_pending_queue(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session)
        await outbox.append(event)
        await outbox.claim(10, WORKER, LEASE_SECONDS)
        await outbox.mark_as_published(event.event_id, WORKER)

        assert await outbox.claim(10, WORKER, LEASE_SECONDS) == []

        record = await _record(session, event)

    assert record.status == PUBLISHED
    assert record.published_at is not None
    assert record.last_error is None


async def test_a_failed_attempt_backs_off_and_keeps_the_reason(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session, now=clock)
        await outbox.append(event)
        await outbox.claim(10, WORKER, LEASE_SECONDS)
        await outbox.mark_failed(event.event_id, "consumer refused", WORKER)

        record = await _record(session, event)

        # Backed off, so the very next claim finds nothing ready.
        assert await outbox.claim(10, WORKER, LEASE_SECONDS) == []

    assert record.status == PENDING
    assert record.attempts == 1
    assert record.last_error == "consumer refused"
    assert record.claimed_by is None
    # SQLite has no timezone-aware storage, so the value comes back naive.
    due_at = record.next_attempt_at.replace(tzinfo=UTC)
    assert due_at == clock.now + timedelta(seconds=2)


async def test_repeated_failures_keep_retrying_and_stop_growing_the_delay(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()
    event = _event()

    async with session_factory() as session:
        # Unlimited retries: this pins the backoff cap, not the attempt budget.
        outbox = SqlAlchemyOutbox(session, now=clock, max_attempts=None)
        await outbox.append(event)

        for _ in range(20):
            clock.advance(1000)  # past the longest backoff, ready to retry
            assert await outbox.claim(10, WORKER, LEASE_SECONDS) == [event]
            await outbox.mark_failed(event.event_id, "still refused", WORKER)

        record = await _record(session, event)
        # 20 attempts have all backed off; the cap keeps the queue moving.
        due_at = record.next_attempt_at.replace(tzinfo=UTC)

    assert record.attempts == 20
    assert record.status == PENDING
    assert due_at - clock.now <= timedelta(seconds=300)


async def test_a_long_reason_is_truncated(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session)
        await outbox.append(event)
        await outbox.claim(10, WORKER, LEASE_SECONDS)
        await outbox.mark_failed(event.event_id, "x" * 5000, WORKER)

        record = await _record(session, event)

    assert record.last_error is not None
    assert len(record.last_error) == 4000


async def test_failing_an_unknown_event_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(LookupError, match="No outbox event"):
            await SqlAlchemyOutbox(session).mark_failed(uuid4(), "gone", WORKER)


async def test_an_event_dated_for_later_is_not_claimable_yet(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session)
        await outbox.append(event)

        record = await _record(session, event)
        record.next_attempt_at = datetime.now(UTC) + timedelta(minutes=5)

        assert await outbox.claim(10, WORKER, LEASE_SECONDS) == []


async def test_an_event_stored_without_a_timezone_is_read_back_as_utc(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    # An event cannot be built without a timezone, but a row can be written with
    # a naive one -- which is what a driver that drops the offset would hand back.
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session)
        session.add(
            OutboxRecord(
                event_id=str(event.event_id),
                event_type=event.event_type,
                schema_version=event.schema_version,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                aggregate_version=event.aggregate_version,
                occurred_at=OCCURRED_AT.replace(tzinfo=None),
                payload=event.payload,
                next_attempt_at=OCCURRED_AT,
            )
        )

        relayed = await outbox.claim(10, WORKER, LEASE_SECONDS)

    assert len(relayed) == 1
    assert relayed[0].occurred_at == OCCURRED_AT


async def test_claim_marks_the_row_claimed_for_that_worker(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session, now=clock)
        await outbox.append(event)

        assert await outbox.claim(10, WORKER, LEASE_SECONDS) == [event]
        record = await _record(session, event)

    assert record.status == CLAIMED
    assert record.claimed_by == WORKER
    assert record.claimed_at is not None
    assert record.lease_expires_at is not None


async def test_a_claimed_event_is_not_claimed_again_while_the_lease_holds(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session, now=clock)
        await outbox.append(_event())

        assert len(await outbox.claim(10, "first", LEASE_SECONDS)) == 1
        # Neither a different worker nor the same one finds anything to take.
        assert await outbox.claim(10, "second", LEASE_SECONDS) == []
        assert await outbox.claim(10, "first", LEASE_SECONDS) == []


async def test_an_expired_lease_is_reclaimed_by_another_worker(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session, now=clock)
        await outbox.append(event)
        assert await outbox.claim(10, "slow", LEASE_SECONDS) == [event]

        clock.advance(LEASE_SECONDS + 1)
        assert await outbox.claim(10, "recovery", LEASE_SECONDS) == [event]
        record = await _record(session, event)

    assert record.claimed_by == "recovery"


async def test_a_reclaimed_workers_mark_is_ignored(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session, now=clock)
        await outbox.append(event)
        assert await outbox.claim(10, "slow", LEASE_SECONDS) == [event]

        clock.advance(LEASE_SECONDS + 1)
        assert await outbox.claim(10, "recovery", LEASE_SECONDS) == [event]
        await outbox.mark_as_published(event.event_id, "recovery")

        # The slow worker comes back late; its mark must not resurrect the row.
        await outbox.mark_failed(event.event_id, "too late", "slow")
        record = await _record(session, event)

    assert record.status == PUBLISHED
    assert record.attempts == 0
    assert record.last_error is None


async def test_the_attempt_budget_sets_the_event_aside_as_dead(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session, now=clock, max_attempts=3)
        await outbox.append(event)

        for _ in range(3):
            clock.advance(1000)
            assert await outbox.claim(10, WORKER, LEASE_SECONDS) == [event]
            await outbox.mark_failed(event.event_id, "refused", WORKER)

        record = await _record(session, event)

        # Spent: no claim ever sees it again, however long the wait.
        clock.advance(100_000)
        assert await outbox.claim(10, WORKER, LEASE_SECONDS) == []

    assert record.status == DEAD
    assert record.attempts == 3
    assert record.last_error == "refused"


async def test_purge_published_removes_only_published_rows_before_the_cutoff(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()
    published = _event()
    still_pending = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session, now=clock)
        await outbox.append(published)
        await outbox.append(still_pending)
        await outbox.claim(10, WORKER, LEASE_SECONDS)
        await outbox.mark_as_published(published.event_id, WORKER)

        # Nothing has outlived the window yet.
        assert await outbox.purge_published(clock.now) == 0

        clock.advance(60)
        assert await outbox.purge_published(clock.now) == 1

        remaining = list(await session.scalars(select(OutboxRecord)))

    assert [row.event_id for row in remaining] == [str(still_pending.event_id)]


async def test_purge_published_leaves_dead_rows_alone(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    clock = _Clock()
    event = _event()

    async with session_factory() as session:
        outbox = SqlAlchemyOutbox(session, now=clock, max_attempts=1)
        await outbox.append(event)
        await outbox.claim(10, WORKER, LEASE_SECONDS)
        await outbox.mark_failed(event.event_id, "refused", WORKER)

        clock.advance(100_000)
        assert await outbox.purge_published(clock.now) == 0
        record = await _record(session, event)

    assert record.status == DEAD


async def test_a_lease_is_required_to_be_positive(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(ValueError, match="lease_seconds must be positive"):
            await SqlAlchemyOutbox(session).claim(10, WORKER, 0)


async def test_an_attempt_budget_below_one_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(ValueError, match="max_attempts must be positive"):
            SqlAlchemyOutbox(session, max_attempts=0)
