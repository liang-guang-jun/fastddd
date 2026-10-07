"""Tests for retention cleanup of the outbox and inbox tables."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastddd.infrastructure.persistence.sqlalchemy.maintenance import (
    SqlAlchemyMaintenance,
)
from fastddd.infrastructure.persistence.sqlalchemy.models import (
    InboxRecord,
    OutboxRecord,
)

NOW = datetime(2026, 6, 1, tzinfo=UTC)
RETENTION = 3600.0


def _clock() -> datetime:
    """Return a fixed moment so retention is measured from a known point."""
    return NOW


def _outbox_row(status: str, finished_at: datetime | None) -> OutboxRecord:
    """Return a stored outbox row finished at the given moment."""
    return OutboxRecord(
        event_id=str(uuid4()),
        event_type="account.opened",
        schema_version=1,
        aggregate_type="Account",
        aggregate_id="1",
        aggregate_version=1,
        occurred_at=NOW,
        payload={},
        status=status,
        next_attempt_at=NOW,
        published_at=finished_at,
    )


async def test_sweep_removes_only_finished_rows_past_retention(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    maintenance = SqlAlchemyMaintenance(session_factory, now=_clock)
    old = NOW - timedelta(hours=2)
    recent = NOW - timedelta(minutes=1)

    async with session_factory() as session:
        session.add_all(
            [
                _outbox_row("published", old),
                _outbox_row("published", recent),
                _outbox_row("dead", old),
                _outbox_row("pending", None),
                InboxRecord(consumer="c", event_id=str(uuid4()), processed_at=old),
                InboxRecord(consumer="c", event_id=str(uuid4()), processed_at=recent),
            ]
        )
        await session.commit()

    # One old published event and one old receipt go.
    assert await maintenance.sweep(RETENTION) == 2

    async with session_factory() as session:
        outbox = list(await session.scalars(select(OutboxRecord)))
        inbox = list(await session.scalars(select(InboxRecord)))

    # The dead event, the recent published event, and the pending event all stay.
    assert sorted(row.status for row in outbox) == ["dead", "pending", "published"]
    assert len(inbox) == 1


async def test_sweep_with_nothing_to_remove_deletes_nothing(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    maintenance = SqlAlchemyMaintenance(session_factory, now=_clock)

    assert await maintenance.sweep(RETENTION) == 0


async def test_a_retention_that_is_not_positive_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    maintenance = SqlAlchemyMaintenance(session_factory, now=_clock)

    with pytest.raises(ValueError, match="retention_seconds must be positive"):
        await maintenance.sweep(0)
