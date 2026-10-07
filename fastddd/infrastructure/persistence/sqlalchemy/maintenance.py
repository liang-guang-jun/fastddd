"""Retention cleanup for the kernel's outbox and inbox tables."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, cast

from sqlalchemy import CursorResult, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ...clock import SystemClock
from .models import InboxRecord
from .outbox import SqlAlchemyOutbox


async def purge_inbox(session: AsyncSession, before: datetime) -> int:
    """Delete inbox receipts processed before ``before``."""
    result = await session.execute(
        delete(InboxRecord).where(InboxRecord.processed_at < before)
    )

    return cast(CursorResult[Any], result).rowcount or 0


class SqlAlchemyMaintenance:
    """Delete finished outbox and inbox rows that outlived their retention.

    Only rows that finished successfully are removed: published events and
    processed receipts. Events set aside as ``dead`` are kept so an operator can
    inspect, and eventually requeue, what could not be delivered.
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        now: Callable[[], datetime] = SystemClock.now,
    ) -> None:
        """Store the session factory and the clock retention is measured from."""
        self._session_factory = session_factory
        self._now = now

    async def sweep(self, retention_seconds: float) -> int:
        """Delete rows finished before the window and return how many went."""
        if retention_seconds <= 0:
            raise ValueError("retention_seconds must be positive")

        before = self._now() - timedelta(seconds=retention_seconds)
        async with self._session_factory() as session:
            published = await SqlAlchemyOutbox(session, now=self._now).purge_published(
                before
            )
            processed = await purge_inbox(session, before)
            await session.commit()

        return published + processed
