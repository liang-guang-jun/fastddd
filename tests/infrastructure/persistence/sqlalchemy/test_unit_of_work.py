"""Tests for the SQLAlchemy unit of work: one session, one transaction."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastddd.infrastructure.persistence.sqlalchemy.outbox import SqlAlchemyOutbox
from fastddd.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from tests.infrastructure.persistence._helpers import (
    Counter,
    CounterChanged,
    CounterId,
    CounterRecord,
)


def _row(counter_id: int) -> CounterRecord:
    """Return an unsaved row the tests can write."""
    return CounterRecord(id=counter_id, label="acme", total=0, deleted_at=None)


def _unit_of_work(
    session_factory: async_sessionmaker[AsyncSession],
) -> SqlAlchemyUnitOfWork:
    """Return a unit of work bound to the test database."""
    return SqlAlchemyUnitOfWork(session_factory)


async def test_nothing_is_open_before_the_scope_is_entered(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = _unit_of_work(session_factory)

    with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
        _ = uow.session

    with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
        _ = uow.outbox


async def test_entering_opens_the_session_and_its_outbox(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = _unit_of_work(session_factory)

    async with uow as entered:
        assert entered is uow
        assert isinstance(uow.session, AsyncSession)
        assert isinstance(uow.outbox, SqlAlchemyOutbox)


async def test_the_session_is_closed_again_after_leaving(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = _unit_of_work(session_factory)

    async with uow:
        pass

    with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
        _ = uow.session


async def test_a_scope_cannot_be_re_entered(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = _unit_of_work(session_factory)

    async with uow:
        with pytest.raises(RuntimeError, match="UnitOfWork cannot be re-entered"):
            async with uow:
                pass


async def test_leaving_commits_what_the_scope_wrote(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _unit_of_work(session_factory) as uow:
        uow.session.add(_row(1))

    async with session_factory() as session:
        assert await session.get(CounterRecord, 1) is not None


async def test_an_exception_rolls_the_scope_back(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with _unit_of_work(session_factory) as uow:
            uow.session.add(_row(1))
            raise RuntimeError("boom")

    async with session_factory() as session:
        assert await session.get(CounterRecord, 1) is None


async def test_committing_inside_the_scope_persists_and_ends_the_transaction(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = _unit_of_work(session_factory)

    async with uow:
        uow.session.add(_row(1))
        await uow.commit()

        with pytest.raises(RuntimeError, match="No active transaction to commit"):
            await uow.commit()

    async with session_factory() as session:
        assert await session.get(CounterRecord, 1) is not None


async def test_committing_without_a_scope_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = _unit_of_work(session_factory)

    with pytest.raises(RuntimeError, match="No active transaction to commit"):
        await uow.commit()


async def test_rolling_back_inside_the_scope_discards_the_write(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with _unit_of_work(session_factory) as uow:
        uow.session.add(_row(1))
        await uow.rollback()

    async with session_factory() as session:
        assert await session.get(CounterRecord, 1) is None


async def test_rolling_back_without_a_scope_is_a_no_op(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _unit_of_work(session_factory).rollback()


async def test_tracking_before_the_scope_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    uow = _unit_of_work(session_factory)

    with pytest.raises(RuntimeError, match="UnitOfWork is not active"):
        uow.track(Counter(CounterId(1)))


async def test_tracking_the_same_aggregate_twice_pulls_its_events_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    counter = Counter(CounterId(1))
    counter.increment()

    async with _unit_of_work(session_factory) as uow:
        uow.track(counter)
        uow.track(counter)

        assert [type(event) for event in uow.pull_events()] == [CounterChanged]


async def test_pulling_drains_every_tracked_aggregate_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    first = Counter(CounterId(1))
    first.increment()
    second = Counter(CounterId(2))
    second.increment()
    second.increment()

    async with _unit_of_work(session_factory) as uow:
        uow.track(first)
        uow.track(second)

        pulled = uow.pull_events()

        assert len(pulled) == 3
        assert uow.pull_events() == []
