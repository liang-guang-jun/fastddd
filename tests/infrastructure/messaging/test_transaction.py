"""Tests for the transaction behavior that wraps a command."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastddd.application.execution.context import (
    Context,
    MessageMetadata,
    current_unit_of_work_or_none,
)
from fastddd.application.integration.outbox import IntegrationEvent
from fastddd.application.messaging.message import Command, Query
from fastddd.domain import DomainEvent
from fastddd.infrastructure.messaging import TransactionBehavior
from fastddd.infrastructure.persistence.sqlalchemy.models import OutboxRecord
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


class _Ping(Command[str]):
    """A command that writes one counter."""


class _Question(Query[str]):
    """A read message, which this behavior is not typed for."""


class _Mapper:
    """Map the sample domain event to one integration event."""

    def map(
        self,
        event: DomainEvent,
        metadata: MessageMetadata | None,
    ) -> Iterable[IntegrationEvent]:
        changed = cast(CounterChanged, event)

        return [
            IntegrationEvent(
                event_type="counter.changed",
                payload={"total": changed.total},
                aggregate_type="Counter",
                aggregate_id="1",
                aggregate_version=1,
                event_id=uuid4(),
                occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
                correlation_id=metadata.correlation_id
                if metadata is not None
                else None,
                tenant_id=metadata.tenant_id if metadata is not None else None,
            )
        ]


def _metadata() -> MessageMetadata:
    """Return the metadata a caller would have bound."""
    return MessageMetadata(
        message_id="message-1",
        correlation_id="correlation-1",
        causation_id=None,
        principal_id=None,
        tenant_id="tenant-1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def _writes_a_counter(message: Command[str]) -> str:
    """Write one counter and record its event."""
    counter = Counter(CounterId(1), total=1)
    counter.increment()
    await CounterRepository().save(counter)

    return "ok"


async def test_a_command_commits_what_its_handler_wrote(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    behavior: TransactionBehavior[str] = TransactionBehavior(uow_factory, _Mapper())

    assert await behavior.handle(_Ping(), _writes_a_counter) == "ok"

    async with session_factory() as session:
        counters = (await session.execute(select(CounterRecord))).scalars().all()

    assert [row.total for row in counters] == [2]


async def test_the_events_of_what_was_written_land_in_the_outbox(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    behavior: TransactionBehavior[str] = TransactionBehavior(uow_factory, _Mapper())

    await behavior.handle(_Ping(), _writes_a_counter)

    async with session_factory() as session:
        queued = (await session.execute(select(OutboxRecord))).scalars().all()

    assert [row.event_type for row in queued] == ["counter.changed"]


async def test_a_failing_handler_leaves_nothing_behind(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async def fails(message: Command[str]) -> str:
        await _writes_a_counter(message)
        raise RuntimeError("nope")

    behavior: TransactionBehavior[str] = TransactionBehavior(uow_factory, _Mapper())

    with pytest.raises(RuntimeError, match="nope"):
        await behavior.handle(_Ping(), fails)

    async with session_factory() as session:
        counters = (await session.execute(select(CounterRecord))).scalars().all()
        queued = (await session.execute(select(OutboxRecord))).scalars().all()

    assert counters == []
    assert queued == []


async def test_a_transaction_inside_a_transaction_is_refused(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    behavior: TransactionBehavior[str] = TransactionBehavior(uow_factory, _Mapper())

    async with Context(unit_of_work=uow_factory()):
        with pytest.raises(RuntimeError, match="outermost transaction owner"):
            await behavior.handle(_Ping(), _writes_a_counter)


async def test_the_delivery_hook_runs_once_the_transaction_is_closed(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    bound_while_delivering: list[bool] = []

    async def after_commit() -> None:
        bound_while_delivering.append(current_unit_of_work_or_none() is not None)

    behavior: TransactionBehavior[str] = TransactionBehavior(
        uow_factory, _Mapper(), after_commit=after_commit
    )

    await behavior.handle(_Ping(), _writes_a_counter)

    # Nothing is bound: a consumer writes through its own unit of work rather
    # than joining a transaction that has already committed.
    assert bound_while_delivering == [False]


async def test_the_delivery_hook_is_not_run_for_a_read(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    calls: list[bool] = []

    async def after_commit() -> None:
        calls.append(True)

    behavior: TransactionBehavior[str] = TransactionBehavior(
        uow_factory, _Mapper(), after_commit=after_commit
    )

    # The behavior is typed for commands; this pins the runtime guard around the
    # hook, which must not fire when a read reaches it.
    await behavior.handle(cast(Command[str], _Question()), _writes_a_counter)

    assert calls == []


async def test_the_callers_metadata_reaches_what_the_command_wrote(
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    behavior: TransactionBehavior[str] = TransactionBehavior(uow_factory, _Mapper())

    async with Context(_metadata()):
        await behavior.handle(_Ping(), _writes_a_counter)

    async with session_factory() as session:
        queued = (await session.execute(select(OutboxRecord))).scalars().one()

    assert queued.correlation_id == "correlation-1"
    assert queued.tenant_id == "tenant-1"
