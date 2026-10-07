"""Driver-neutral async SQLAlchemy engine and session construction."""

from __future__ import annotations

from typing import Protocol, cast

from sqlalchemy import event
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.ext.asyncio import (
    create_async_engine as sqlalchemy_create_async_engine,
)


def create_async_engine(
    url: str | URL,
    *,
    echo: bool = False,
    sqlite_busy_timeout_ms: int | None = None,
    pool_size: int | None = None,
    max_overflow: int | None = None,
    pool_timeout: int | None = None,
    pool_recycle: int | None = None,
    async_creator: object | None = None,
) -> AsyncEngine:
    """Build an async engine for any SQLAlchemy-supported async dialect.

    SQLite receives its safe single-node PRAGMAs when selected. Other drivers,
    such as ``postgresql+asyncpg``, are passed directly to SQLAlchemy without
    SQLite-specific validation or connection hooks.
    """
    parsed_url = make_url(url)
    kwargs: dict[str, object] = {"echo": echo}
    if pool_size is not None:
        kwargs["pool_size"] = pool_size
    if max_overflow is not None:
        kwargs["max_overflow"] = max_overflow
    if pool_timeout is not None:
        kwargs["pool_timeout"] = pool_timeout
    if pool_recycle is not None:
        kwargs["pool_recycle"] = pool_recycle
    if async_creator is not None:
        kwargs["async_creator"] = async_creator
    engine = sqlalchemy_create_async_engine(url, **kwargs)
    if parsed_url.get_backend_name() != "sqlite":
        return engine

    class _Cursor(Protocol):
        def close(self) -> None: ...

        def execute(self, statement: str) -> object: ...

    class _CursorConnection(Protocol):
        isolation_level: object

        def cursor(self) -> _Cursor: ...

    class _ExecuteConnection(Protocol):
        def exec_driver_sql(self, statement: str) -> object: ...

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_connection(dbapi_connection: object, _: object) -> None:
        connection = cast(_CursorConnection, dbapi_connection)
        # Take transaction control away from the driver. Left to itself, pysqlite
        # opens the transaction with the first statement it sees, so a savepoint
        # taken as that first statement is released -- committed -- immediately
        # instead of nesting inside a transaction a rollback could undo.
        connection.isolation_level = None
        cursor = connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            if sqlite_busy_timeout_ms is not None:
                cursor.execute(f"PRAGMA busy_timeout={sqlite_busy_timeout_ms}")
        finally:
            cursor.close()

    @event.listens_for(engine.sync_engine, "begin")
    def _begin_transaction(connection: object) -> None:
        # With the driver's own control disabled, the BEGIN has to be emitted
        # here, so a savepoint finally has a transaction to nest inside.
        cast(_ExecuteConnection, connection).exec_driver_sql("BEGIN")

    return engine


def create_session_factory(
    engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    """Create non-expiring sessions appropriate for aggregate reconstitution."""
    return async_sessionmaker(engine, expire_on_commit=False)
