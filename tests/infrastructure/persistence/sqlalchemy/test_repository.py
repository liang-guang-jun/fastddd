"""Tests for the write-side aggregate repository base classes."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fastddd.application.execution.context import Context
from fastddd.application.ports.unit_of_work import UnitOfWork
from fastddd.domain import (
    DomainEvent,
    InvalidCursorError,
    PageRequest,
    encode_cursor,
)
from fastddd.infrastructure.persistence.sqlalchemy.repository import (
    SqlAlchemyMappedRepository,
)
from fastddd.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from tests.infrastructure.persistence._helpers import (
    Counter,
    CounterChanged,
    CounterId,
    CounterRecord,
    CounterRepository,
)


class _ForeignUnitOfWork(UnitOfWork):
    """A transaction that is not the SQLAlchemy one this adapter needs."""

    @property
    def outbox(self) -> Any:
        raise NotImplementedError

    def track(self, aggregate: Any) -> None:
        """Do nothing."""

    def pull_events(self) -> list[DomainEvent]:
        """Return no events."""
        return []

    async def __aenter__(self) -> Self:
        """Enter the scope."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Leave the scope."""

    async def commit(self) -> None:
        """Commit nothing."""

    async def rollback(self) -> None:
        """Roll nothing back."""


async def _stored(session: AsyncSession) -> list[CounterRecord]:
    """Return every row of the sample table, in key order."""
    statement = select(CounterRecord).order_by(CounterRecord.id)

    return list((await session.execute(statement)).scalars())


async def test_a_saved_aggregate_is_loadable_inside_the_same_transaction(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    repository = CounterRepository()

    async with Context(unit_of_work=uow_factory()):
        await repository.save(Counter(CounterId(1), total=7))

        loaded = await repository.get(CounterId(1))

    assert loaded is not None
    assert loaded.total == 7


async def test_a_committed_aggregate_outlives_the_command(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        await CounterRepository().save(Counter(CounterId(1), label="alpha", total=7))

    async with Context(unit_of_work=uow_factory()):
        loaded = await CounterRepository().get(CounterId(1))

    assert loaded is not None
    assert loaded.label == "alpha"


async def test_a_rolled_back_aggregate_is_gone(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    with pytest.raises(RuntimeError, match="boom"):
        async with Context(unit_of_work=uow_factory()):
            await CounterRepository().save(Counter(CounterId(1)))
            raise RuntimeError("boom")

    async with Context(unit_of_work=uow_factory()):
        assert await CounterRepository().get(CounterId(1)) is None


async def test_an_aggregate_that_was_never_stored_loads_as_nothing(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        assert await CounterRepository().get(CounterId(404)) is None


async def test_a_soft_deleted_aggregate_loads_as_nothing(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    counter = Counter(CounterId(1))
    counter.delete(at=datetime(2026, 1, 1, tzinfo=UTC))

    uow = uow_factory()

    async with Context(unit_of_work=uow):
        await CounterRepository().save(counter)
        # The row is still there; the aggregate is simply not live any more.
        assert await _stored(uow.session) != []

    async with Context(unit_of_work=uow_factory()):
        assert await CounterRepository().get(CounterId(1)) is None


async def test_saving_twice_updates_the_one_row(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    counter = Counter(CounterId(1), total=1)
    uow = uow_factory()

    async with Context(unit_of_work=uow):
        repository = CounterRepository()
        await repository.save(counter)
        counter.total = 2
        await repository.save(counter)

        stored = await _stored(uow.session)

    assert len(stored) == 1
    assert stored[0].total == 2


async def test_saving_hands_the_aggregates_events_to_the_transaction(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    counter = Counter(CounterId(1))
    counter.increment()
    uow = uow_factory()

    async with Context(unit_of_work=uow):
        await CounterRepository().save(counter)

        assert [type(event) for event in uow.pull_events()] == [CounterChanged]


async def test_purging_removes_the_row_for_good(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        await CounterRepository().save(Counter(CounterId(1)))

    purging = uow_factory()

    async with Context(unit_of_work=purging):
        await CounterRepository().purge(CounterId(1))
        assert await _stored(purging.session) == []

    after = uow_factory()

    async with Context(unit_of_work=after):
        assert await _stored(after.session) == []


async def test_purging_something_that_is_not_there_is_a_no_op(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        await CounterRepository().purge(CounterId(404))


async def test_purging_one_aggregate_leaves_the_others_alone(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        repository = CounterRepository()
        await repository.save(Counter(CounterId(1)))
        await repository.save(Counter(CounterId(2)))

    uow = uow_factory()

    async with Context(unit_of_work=uow):
        await CounterRepository().purge(CounterId(1))

        assert [row.id for row in await _stored(uow.session)] == [2]


async def test_finding_by_a_natural_key_returns_and_tracks_the_aggregate(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        await CounterRepository().save(Counter(CounterId(1), label="alpha"))
        await CounterRepository().save(Counter(CounterId(2), label="beta"))

    async with Context(unit_of_work=uow_factory()):
        found = await CounterRepository().find_one(CounterRecord.label == "alpha")

    assert found is not None
    assert found.id.value == 1


async def test_finding_never_resolves_to_a_soft_deleted_aggregate(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    counter = Counter(CounterId(1), label="alpha")
    counter.delete(at=datetime(2026, 1, 1, tzinfo=UTC))

    async with Context(unit_of_work=uow_factory()):
        await CounterRepository().save(counter)

    async with Context(unit_of_work=uow_factory()):
        found = await CounterRepository().find_one(CounterRecord.label == "alpha")

    assert found is None


async def test_finding_something_that_is_not_there_returns_nothing(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        assert (
            await CounterRepository().find_one(CounterRecord.label == "absent") is None
        )


async def test_paging_walks_every_row_exactly_once(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        repository = CounterRepository()
        for index in range(1, 6):
            await repository.save(
                Counter(CounterId(index), label=f"c{index}", total=index)
            )

    seen: list[int] = []
    cursor: str | None = None

    async with Context(unit_of_work=uow_factory()):
        repository = CounterRepository()
        for _ in range(5):
            page = await repository.page(
                select(CounterRecord),
                PageRequest(cursor=cursor, size=2),
                order_by=(CounterRecord.total, CounterRecord.id),
            )
            seen.extend(item.id.value for item in page.items)
            cursor = page.next_cursor
            if cursor is None:
                break

    assert seen == [1, 2, 3, 4, 5]
    assert cursor is None


async def test_paging_an_empty_list_returns_no_cursor(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        page = await CounterRepository().page(
            select(CounterRecord),
            PageRequest(),
            order_by=(CounterRecord.total, CounterRecord.id),
        )

    assert page.items == []
    assert page.has_next is False


async def test_a_cursor_from_another_list_is_refused(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=uow_factory()):
        with pytest.raises(InvalidCursorError):
            await CounterRepository().page(
                select(CounterRecord),
                PageRequest(cursor=encode_cursor(1, 2, 3)),
                order_by=(CounterRecord.total, CounterRecord.id),
            )


async def test_a_repository_without_a_mapper_is_refused_when_it_is_defined() -> None:
    with pytest.raises(TypeError, match="must declare record_type, mapper"):

        class Unmapped(SqlAlchemyMappedRepository[Counter, CounterRecord, int]):
            """Declares nothing about what it maps."""


async def test_a_repository_that_declares_only_a_record_is_refused() -> None:
    with pytest.raises(TypeError, match="must declare mapper"):

        class HalfMapped(SqlAlchemyMappedRepository[Counter, CounterRecord, int]):
            """Declares the row but not the translation."""

            record_type = CounterRecord


async def test_a_repository_outside_a_command_has_no_unit_of_work() -> None:
    with pytest.raises(LookupError):
        await CounterRepository().get(CounterId(1))


async def test_a_foreign_unit_of_work_is_refused() -> None:
    with pytest.raises(TypeError, match="not SQLAlchemy-backed"):
        async with Context(unit_of_work=_ForeignUnitOfWork()):
            await CounterRepository().get(CounterId(1))
