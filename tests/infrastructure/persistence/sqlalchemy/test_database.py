"""Tests for the driver-neutral engine and session construction."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from fastddd.infrastructure.persistence.sqlalchemy.database import (
    create_async_engine,
    create_session_factory,
)


def _sqlite_url(tmp_path: Path) -> str:
    """Return a file-backed SQLite URL, where PRAGMAs can actually take hold."""
    return f"sqlite+aiosqlite:///{tmp_path / 'test.db'}"


async def _pragma(engine: AsyncEngine, name: str) -> object:
    """Return the value of one SQLite PRAGMA on a fresh connection."""
    async with engine.connect() as connection:
        return (await connection.execute(text(f"pragma {name}"))).scalar()


async def test_a_sqlite_connection_comes_up_configured(tmp_path: Path) -> None:
    engine = create_async_engine(_sqlite_url(tmp_path))
    try:
        assert await _pragma(engine, "foreign_keys") == 1
        assert str(await _pragma(engine, "journal_mode")).lower() == "wal"
    finally:
        await engine.dispose()


async def test_a_busy_timeout_is_applied_when_one_is_asked_for(tmp_path: Path) -> None:
    engine = create_async_engine(_sqlite_url(tmp_path), sqlite_busy_timeout_ms=1500)
    try:
        assert await _pragma(engine, "busy_timeout") == 1500
    finally:
        await engine.dispose()


async def test_without_a_busy_timeout_the_driver_default_stands(tmp_path: Path) -> None:
    # The aiosqlite dialect already asks SQLite for its own 5-second connect
    # timeout (5000 ms of busy handling); the kernel leaves that alone.
    engine = create_async_engine(_sqlite_url(tmp_path))
    try:
        assert await _pragma(engine, "busy_timeout") == 5000
    finally:
        await engine.dispose()


async def test_echo_is_passed_to_the_engine(tmp_path: Path) -> None:
    engine = create_async_engine(_sqlite_url(tmp_path), echo=True)
    try:
        assert engine.echo is True
    finally:
        await engine.dispose()


async def test_a_non_sqlite_driver_is_handed_to_sqlalchemy_untouched() -> None:
    engine = create_async_engine("postgresql+asyncpg://user@host:5432/db")
    try:
        assert engine.dialect.name == "postgresql"
    finally:
        await engine.dispose()


async def test_pool_settings_reach_a_pooled_driver() -> None:
    async def connect() -> object:
        """Return a connection; the pool never asks for one here."""
        raise AssertionError("the engine is only built, never opened")

    engine = create_async_engine(
        "postgresql+asyncpg://user@host:5432/db",
        pool_size=3,
        max_overflow=1,
        pool_timeout=5,
        pool_recycle=60,
        async_creator=connect,
    )
    try:
        pool = engine.sync_engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.size() == 3
        assert "Pool size: 3" in pool.status()
    finally:
        await engine.dispose()


async def test_sessions_do_not_expire_on_commit(tmp_path: Path) -> None:
    engine = create_async_engine(_sqlite_url(tmp_path))
    try:
        assert create_session_factory(engine).kw["expire_on_commit"] is False
    finally:
        await engine.dispose()
