"""Reusable event-id deduplication primitive for idempotent consumers.

An integration event is delivered at least once, so a consumer that must not
apply the same fact twice records every event it handled in the inbox, under an
explicit consumer name. Recording the receipt inside the consumer's own
transaction makes the effect idempotent: a redelivery finds the receipt and does
nothing, while a rollback takes the receipt back with the work it guarded.

The consumer name is what makes the key unique. It cannot be the event type: one
type fans out to several consumers, and one consumer may serve several types, so
keying on the type would let a consumer that succeeded suppress the retry of a
sibling that failed.

The receipt is written as a savepoint inside the caller's transaction, so it
survives only if the work around it does: a consumer that fails rolls the receipt
back and sees the event again on the retry.

A read model is one kind of consumer. It needs everything above and one thing
more: a name that cannot collide with another kind of consumer's, because a
projection and a handler that happen to share a name would share a receipt and
suppress each other. ``projection_consumer`` is the only place that namespace is
spelled.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..application.execution.context import Context
from ..application.integration.outbox import IntegrationEvent
from ..application.messaging.handler import EventHandler
from .clock import SystemClock
from .persistence.sqlalchemy.models import InboxRecord
from .persistence.sqlalchemy.unit_of_work import SqlAlchemyUnitOfWork


async def claim_inbox_message(
    session: AsyncSession,
    consumer: str,
    event_id: object,
    *,
    now: Callable[[], datetime] = SystemClock.now,
) -> bool:
    """Record a consumer's receipt of an event; return false for a duplicate.

    The receipt is written in the caller's transaction, so a consumer that
    handles the event and a consumer that rolls back both stay consistent: the
    claim survives only if the work it guards does.
    """
    exists = await session.scalar(
        select(InboxRecord.id).where(
            InboxRecord.consumer == consumer,
            InboxRecord.event_id == str(event_id),
        )
    )
    if exists is not None:
        return False

    try:
        async with session.begin_nested():
            session.add(
                InboxRecord(
                    consumer=consumer,
                    event_id=str(event_id),
                    processed_at=now(),
                )
            )
            await session.flush()
    except IntegrityError:
        # Another writer claimed the same event first; the constraint settles it.
        return False

    return True


class InboxConsumer(EventHandler[IntegrationEvent]):
    """Handle an event at most once, under an explicit consumer name.

    The name is what makes a receipt unique, so two consumers of one event type
    each get their own receipt and a redelivery to one of them is a no-op for
    that one alone. The consumer owns its transaction, so a receipt and the work
    it guards commit together, and a failure leaves neither behind.
    """

    def __init__(
        self,
        name: str,
        handler: EventHandler[IntegrationEvent],
        uow_factory: Callable[[], SqlAlchemyUnitOfWork],
    ) -> None:
        """Name this consumer and give it the handler and transactions it runs."""
        self._name = name
        self._handler = handler
        self._uow_factory = uow_factory

    @property
    def name(self) -> str:
        """Return the name this consumer's receipts are keyed under."""
        return self._name

    async def handle(self, event: IntegrationEvent) -> None:
        """Claim the event, run the consumer, and commit the two together."""
        uow = self._uow_factory()
        async with Context(unit_of_work=uow):
            claimed = await claim_inbox_message(uow.session, self._name, event.event_id)
            if claimed:
                await self._handler.handle(event)


_PROJECTION_PREFIX = "projection:"


def projection_consumer(
    name: str,
    handler: EventHandler[IntegrationEvent],
    uow_factory: Callable[[], SqlAlchemyUnitOfWork],
) -> InboxConsumer:
    """Return a consumer whose receipts live in the projection namespace.

    A projection is what ``InboxConsumer`` already describes -- handle the event
    once, in a transaction of its own -- plus a name that cannot collide with
    another kind of consumer's.
    """
    return InboxConsumer(f"{_PROJECTION_PREFIX}{name}", handler, uow_factory)
