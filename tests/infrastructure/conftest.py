"""Database fixtures: in-memory SQLite always, PostgreSQL when it answers.

Most tests run on in-memory SQLite, which needs no server and leaves nothing
behind. The tests marked ``integration`` run against a real PostgreSQL -- the
deployment target, where types, cursors, and constraints behave differently -- and
skip themselves when nothing is listening, so a plain ``uv run pytest`` stays
green on a machine with no database. Start one for the whole suite with
``tests/docker-compose.yml``.
"""

from __future__ import annotations

import os
import socket
from collections.abc import AsyncIterator, Callable
from functools import lru_cache

import pytest
from sqlalchemy import text
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from fastddd.infrastructure.persistence.sqlalchemy.database import (
    create_async_engine,
)
from fastddd.infrastructure.persistence.sqlalchemy.models import Base
from fastddd.infrastructure.persistence.sqlalchemy.unit_of_work import (
    SqlAlchemyUnitOfWork,
)

TEST_POSTGRES_DSN = "postgresql://fastddd:fastddd@127.0.0.1:55432/fastddd_test"
"""Where ``tests/docker-compose.yml`` publishes its server."""


def _integration_url() -> URL:
    """Return the integration server's URL, overridable for CI or another host."""
    return make_url(os.environ.get("FASTDDD_TEST_POSTGRES_DSN", TEST_POSTGRES_DSN))


@lru_cache(maxsize=1)
def _somebody_is_listening(host: str, port: int) -> bool:
    """Return whether the port accepts a connection, so absence can skip fast."""
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _empty_every_table() -> str:
    """Return the statement that empties the kernel's tables."""
    names = ", ".join(table.name for table in Base.metadata.sorted_tables)

    return f"TRUNCATE {names} RESTART IDENTITY"


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """Return an in-memory SQLite engine carrying the kernel schema."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with test_engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    try:
        yield test_engine
    finally:
        await test_engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the test engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


@pytest.fixture
def uow_factory(
    session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], SqlAlchemyUnitOfWork]:
    """Return a factory building one unit of work -- one transaction -- per use."""
    return lambda: SqlAlchemyUnitOfWork(session_factory)


@pytest.fixture
def postgres_url() -> URL:
    """Return the integration server's URL, or skip when it is not running."""
    url = _integration_url()
    host, port = url.host or "127.0.0.1", url.port or 5432
    if not _somebody_is_listening(host, port):
        pytest.skip(
            f"no PostgreSQL at {host}:{port} -- "
            "docker compose -f tests/docker-compose.yml up -d --wait"
        )

    return url


@pytest.fixture
async def postgres_engine(postgres_url: URL) -> AsyncIterator[AsyncEngine]:
    """Return an engine over the integration database, with empty tables.

    The tables are created once and emptied before every test, so an integration
    test starts from the same state as a SQLite one and rows left by an
    interrupted run cannot change what it sees.
    """
    integration_engine = create_async_engine(
        postgres_url.set(drivername="postgresql+asyncpg")
    )
    try:
        async with integration_engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.execute(text(_empty_every_table()))
        yield integration_engine
    finally:
        await integration_engine.dispose()


@pytest.fixture
def postgres_session_factory(
    postgres_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to the integration database."""
    return async_sessionmaker(postgres_engine, expire_on_commit=False)


@pytest.fixture
def postgres_uow_factory(
    postgres_session_factory: async_sessionmaker[AsyncSession],
) -> Callable[[], SqlAlchemyUnitOfWork]:
    """Return a unit-of-work factory over the integration database."""
    return lambda: SqlAlchemyUnitOfWork(postgres_session_factory)
