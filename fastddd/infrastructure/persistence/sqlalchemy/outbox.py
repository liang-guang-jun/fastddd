"""SQLAlchemy persistence adapter for the transactional integration outbox."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from sqlalchemy import (
    ColumnElement,
    CursorResult,
    and_,
    delete,
    or_,
    select,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession

from ....application.integration.outbox import IntegrationEvent, Outbox
from ...clock import SystemClock
from .models import OutboxRecord

PENDING = "pending"
CLAIMED = "claimed"
PUBLISHED = "published"
DEAD = "dead"

DEFAULT_MAX_ATTEMPTS = 10
"""Failed deliveries an event is given before it is set aside as ``dead``."""

BACKOFF_CAP_SECONDS = 300


class SqlAlchemyOutbox(Outbox):
    """Store integration events in the session's current database transaction."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        max_attempts: int | None = DEFAULT_MAX_ATTEMPTS,
        now: Callable[[], datetime] = SystemClock.now,
    ) -> None:
        """Bind this adapter to a session, a retry budget, and a clock.

        ``max_attempts`` is how many failed deliveries an event is given before
        it is set aside as ``dead`` rather than retried; ``None`` retries it
        forever. ``now`` is injectable so lease and backoff timing can be driven
        deterministically in tests.
        """
        if max_attempts is not None and max_attempts < 1:
            raise ValueError("max_attempts must be positive or None")
        self._session = session
        self._max_attempts = max_attempts
        self._now = now

    async def append(self, event: IntegrationEvent) -> None:
        """Add an event without committing the caller's transaction."""
        self._session.add(
            OutboxRecord(
                event_id=str(event.event_id),
                event_type=event.event_type,
                schema_version=event.schema_version,
                aggregate_type=event.aggregate_type,
                aggregate_id=event.aggregate_id,
                aggregate_version=event.aggregate_version,
                occurred_at=event.occurred_at,
                correlation_id=event.correlation_id,
                causation_id=event.causation_id,
                tenant_id=event.tenant_id,
                payload=event.payload,
                next_attempt_at=self._now(),
            )
        )

    async def claim(
        self,
        limit: int,
        worker: str,
        lease_seconds: float,
    ) -> list[IntegrationEvent]:
        """Lease ready records to one worker, reclaiming expired leases.

        One statement does the select and the write, so two workers racing for
        the same row cannot both win: the outer condition is re-checked after any
        lock wait, and the loser matches no rows.
        """
        if limit < 1:
            raise ValueError("limit must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")

        now = self._now()
        claimable = or_(
            (OutboxRecord.status == PENDING) & (OutboxRecord.next_attempt_at <= now),
            (OutboxRecord.status == CLAIMED) & (OutboxRecord.lease_expires_at < now),
        )
        candidates = (
            select(OutboxRecord.id)
            .where(claimable)
            .order_by(OutboxRecord.id)
            .limit(limit)
            .scalar_subquery()
        )
        statement = (
            update(OutboxRecord)
            .where(OutboxRecord.id.in_(candidates), claimable)
            .values(
                status=CLAIMED,
                claimed_by=worker,
                claimed_at=now,
                lease_expires_at=now + timedelta(seconds=lease_seconds),
            )
            .returning(OutboxRecord)
        )
        claimed = await self._session.scalars(statement)

        return [self._to_event(record) for record in claimed]

    async def mark_as_published(self, event_id: UUID, worker: str) -> None:
        """Publish an event, if the claiming worker still holds its lease."""
        await self._session.execute(
            update(OutboxRecord)
            .where(self._held_by(event_id, worker))
            .values(
                status=PUBLISHED,
                published_at=self._now(),
                last_error=None,
                claimed_by=None,
                claimed_at=None,
                lease_expires_at=None,
            )
        )

    async def mark_failed(self, event_id: UUID, error: str, worker: str) -> None:
        """Back off, or set the event aside once its attempt budget is spent."""
        held = await self._session.scalar(
            select(OutboxRecord).where(self._held_by(event_id, worker))
        )
        if held is None:
            if not await self._exists(event_id):
                raise LookupError(f"No outbox event: {event_id}")
            # The lease was reclaimed by another worker: leave its work alone.
            return

        held.attempts += 1
        held.last_error = error[:4000]
        held.claimed_by = None
        held.claimed_at = None
        held.lease_expires_at = None
        if self._max_attempts is not None and held.attempts >= self._max_attempts:
            held.status = DEAD
        else:
            held.status = PENDING
            held.next_attempt_at = self._now() + timedelta(
                seconds=min(BACKOFF_CAP_SECONDS, 2 ** min(held.attempts, 8))
            )

    async def purge_published(self, before: datetime) -> int:
        """Delete records published before ``before`` and return how many went."""
        result = await self._session.execute(
            delete(OutboxRecord).where(
                OutboxRecord.status == PUBLISHED,
                OutboxRecord.published_at < before,
            )
        )

        return cast(CursorResult[Any], result).rowcount or 0

    @staticmethod
    def _held_by(event_id: UUID, worker: str) -> ColumnElement[bool]:
        """Return the condition that makes ``worker`` the current lease holder."""
        return and_(
            OutboxRecord.event_id == str(event_id),
            OutboxRecord.claimed_by == worker,
            OutboxRecord.status == CLAIMED,
        )

    async def _exists(self, event_id: UUID) -> bool:
        """Return whether any record carries this event id."""
        found = await self._session.scalar(
            select(OutboxRecord.id).where(OutboxRecord.event_id == str(event_id))
        )

        return found is not None

    @staticmethod
    def _to_event(record: OutboxRecord) -> IntegrationEvent:
        occurred_at = (
            record.occurred_at.replace(tzinfo=UTC)
            if record.occurred_at.tzinfo is None
            else record.occurred_at
        )
        return IntegrationEvent(
            event_id=UUID(record.event_id),
            event_type=record.event_type,
            schema_version=record.schema_version,
            aggregate_type=record.aggregate_type,
            aggregate_id=record.aggregate_id,
            aggregate_version=record.aggregate_version,
            occurred_at=occurred_at,
            correlation_id=record.correlation_id,
            causation_id=record.causation_id,
            tenant_id=record.tenant_id,
            payload=record.payload,
        )
