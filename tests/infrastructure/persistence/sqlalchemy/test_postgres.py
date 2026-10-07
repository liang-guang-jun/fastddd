"""Tests that need a real PostgreSQL server: ``tests/docker-compose.yml``.

SQLite is where most of the suite runs, but PostgreSQL is what the kernel is
deployed on, and that is where the differences live: a native ``uuid`` column, a
``timestamptz`` that comes back aware, row-value comparison for cursor paging, and
credentials handed to asyncpg per connection rather than to the engine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import SecretStr
from sqlalchemy import select, text
from sqlalchemy.engine import URL
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastddd.application.execution.context import Context
from fastddd.application.integration.outbox import IntegrationEvent
from fastddd.domain import PageRequest
from fastddd.infrastructure.configuration.schemas import (
    DatabaseConfig,
    DatabasePasswordAuthConfig,
)
from fastddd.infrastructure.persistence.sqlalchemy.backend import (
    create_database_backend,
)
from fastddd.infrastructure.persistence.sqlalchemy.outbox import SqlAlchemyOutbox
from fastddd.infrastructure.persistence.sqlalchemy.pagination import fetch_page
from fastddd.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SqlAlchemyUnitOfWork,
)
from tests.infrastructure.persistence._helpers import (
    Counter,
    CounterId,
    CounterRecord,
    CounterRepository,
    TicketRecord,
)

pytestmark = pytest.mark.integration

OCCURRED_AT = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def _config(url: URL) -> DatabaseConfig:
    """Return a database configuration for the server the URL points at."""
    return DatabaseConfig(
        provider="postgresql",
        driver="asyncpg",
        auth=DatabasePasswordAuthConfig(
            username=url.username or "postgres",
            password=SecretStr(url.password or ""),
            database=url.database or "postgres",
        ),
    )


def _event() -> IntegrationEvent:
    """Return an integration event to append."""
    return IntegrationEvent(
        event_type="account.opened",
        payload={"name": "acme"},
        aggregate_type="Account",
        aggregate_id="1",
        aggregate_version=1,
        event_id=uuid4(),
        occurred_at=OCCURRED_AT,
        correlation_id="correlation-1",
        tenant_id="tenant-1",
    )


def _ticket(ticket_id: int) -> TicketRecord:
    """Return an unsaved ticket, whose ordering column a test then sets."""
    return TicketRecord(
        id=ticket_id,
        label=f"ticket-{ticket_id}",
        note=None,
        score=float(ticket_id),
        opened_at=OCCURRED_AT + timedelta(days=ticket_id),
        urgent=False,
        token=UUID(int=ticket_id),
    )


async def test_the_engine_connects_with_the_configured_credentials(
    postgres_url: URL,
) -> None:
    backend = create_database_backend(
        _config(postgres_url),
        environment={
            "DATABASE_HOST": postgres_url.host or "127.0.0.1",
            "DATABASE_PORT": str(postgres_url.port or 5432),
            # The test server speaks plain TCP; asking for TLS would fail here.
            "PGSSLMODE": "disable",
        },
    )

    engine = backend.create_engine()
    try:
        async with engine.connect() as connection:
            assert (await connection.execute(text("select 1"))).scalar() == 1
    finally:
        await engine.dispose()


async def test_the_outbox_round_trips_on_postgres(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    event = _event()

    async with postgres_session_factory() as session:
        outbox = SqlAlchemyOutbox(session)
        await outbox.append(event)
        await session.commit()

    async with postgres_session_factory() as session:
        outbox = SqlAlchemyOutbox(session)
        relayed = await outbox.claim(10, "postgres-worker", 30.0)

        assert relayed == [event]
        # Unlike SQLite, PostgreSQL hands a timestamptz back with its offset, so
        # the event needs no repairing on the way out of the outbox.
        assert relayed[0].occurred_at.tzinfo is not None

        await outbox.mark_as_published(event.event_id, "postgres-worker")
        await session.commit()

    async with postgres_session_factory() as session:
        assert await SqlAlchemyOutbox(session).claim(10, "postgres-worker", 30.0) == []


async def test_the_unit_of_work_commits_and_rolls_back_on_postgres(
    postgres_uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with Context(unit_of_work=postgres_uow_factory()):
        await CounterRepository().save(Counter(CounterId(1), label="alpha"))

    async with postgres_session_factory() as session:
        assert (await session.execute(select(CounterRecord))).scalars().all() != []

    with pytest.raises(RuntimeError, match="boom"):
        async with Context(unit_of_work=postgres_uow_factory()):
            await CounterRepository().save(Counter(CounterId(2), label="beta"))
            raise RuntimeError("boom")

    async with postgres_session_factory() as session:
        stored = (await session.execute(select(CounterRecord))).scalars().all()

    assert [row.id for row in stored] == [1]


async def test_cursor_paging_walks_every_row_on_postgres(
    postgres_uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    async with Context(unit_of_work=postgres_uow_factory()):
        repository = CounterRepository()
        for index in range(1, 6):
            await repository.save(
                Counter(CounterId(index), label=f"c{index}", total=index)
            )

    seen: list[int] = []
    cursor: str | None = None

    async with Context(unit_of_work=postgres_uow_factory()):
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


async def test_finding_never_resolves_to_a_soft_deleted_aggregate_on_postgres(
    postgres_uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> None:
    counter = Counter(CounterId(1), label="alpha")
    counter.delete(at=OCCURRED_AT)

    async with Context(unit_of_work=postgres_uow_factory()):
        await CounterRepository().save(counter)

    async with Context(unit_of_work=postgres_uow_factory()):
        found = await CounterRepository().find_one(CounterRecord.label == "alpha")

    assert found is None


@pytest.mark.parametrize(
    ("column", "values"),
    [
        pytest.param(
            TicketRecord.opened_at,
            [OCCURRED_AT + timedelta(days=day) for day in (1, 2, 3)],
            id="timestamp",
        ),
        pytest.param(
            TicketRecord.token,
            [UUID(int=1), UUID(int=2), UUID(int=3)],
            id="identity",
        ),
        pytest.param(TicketRecord.urgent, [False, True, True], id="flag"),
    ],
)
async def test_a_cursor_resumes_after_a_row_of_any_kind_on_postgres(
    postgres_session_factory: async_sessionmaker[AsyncSession],
    column: Any,
    values: list[Any],
) -> None:
    async with postgres_session_factory() as session:
        for index, value in enumerate(values, start=1):
            ticket = _ticket(index)
            setattr(ticket, column.key, value)
            session.add(ticket)
        await session.commit()

    seen: list[int] = []
    cursor: str | None = None

    for _ in range(len(values) + 1):
        async with postgres_session_factory() as session:
            rows, cursor = await fetch_page(
                session,
                select(TicketRecord),
                PageRequest(cursor=cursor, size=1),
                order_by=(column, TicketRecord.id),
            )
        seen.extend(row.id for row in rows)
        if cursor is None:
            break

    assert seen == [1, 2, 3]
    assert cursor is None


@pytest.mark.integration
async def test_two_workers_claiming_at_once_never_share_an_event(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """The re-asserted claim condition is what settles a race on PostgreSQL.

    Both workers run the same claim at the same time; whichever loses the lock
    wait finds its rows already leased and matches none of them, so the two
    batches partition the queue instead of overlapping.
    """
    events = [_event() for _ in range(4)]

    async with postgres_session_factory() as session:
        seed = SqlAlchemyOutbox(session)
        for event in events:
            await seed.append(event)
        await session.commit()

    async def claim_as(worker: str) -> list[IntegrationEvent]:
        async with postgres_session_factory() as session:
            claimed = await SqlAlchemyOutbox(session).claim(4, worker, 30.0)
            await session.commit()

            return claimed

    left, right = await asyncio.gather(claim_as("left"), claim_as("right"))

    claimed = [event.event_id for event in [*left, *right]]

    assert sorted(claimed) == sorted(event.event_id for event in events)
