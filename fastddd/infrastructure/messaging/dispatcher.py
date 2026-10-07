"""Polling dispatcher for a transactional outbox.

One dispatcher is safe to run alongside others: it leases its batch before
publishing, so no two dispatchers deliver the same event, and a lease that
outlives a stopped dispatcher is recovered by the next claim.
"""

from __future__ import annotations

from collections.abc import Callable

from ...application.integration.outbox import IntegrationEvent
from ...application.integration.publisher import EventPublisher
from ...application.ports import UnitOfWork
from ..identity import UuidGenerator

DEFAULT_LEASE_SECONDS = 300.0
"""How long a claimed event is held before another worker may reclaim it."""


class OutboxDispatcher:
    """Publish ready events outside a transaction and persist delivery outcome."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        publisher: EventPublisher,
        *,
        batch_size: int = 100,
        worker: str | None = None,
        lease_seconds: float = DEFAULT_LEASE_SECONDS,
    ) -> None:
        """Configure the dispatcher, its batch size, and its claim lease."""
        if batch_size < 1:
            raise ValueError("batch_size must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self._uow_factory = uow_factory
        self._publisher = publisher
        self._batch_size = batch_size
        self._worker = worker or f"dispatcher-{UuidGenerator.new()}"
        self._lease = lease_seconds

    @property
    def worker(self) -> str:
        """Return the identity this dispatcher claims events under."""
        return self._worker

    async def dispatch_once(self) -> int:
        """Lease a ready batch, publish it, and settle each event once."""
        async with self._uow_factory() as uow:
            events = await uow.outbox.claim(self._batch_size, self._worker, self._lease)
        if not events:
            return 0

        outcomes = [(event, *(await self._publish(event))) for event in events]
        await self._settle(outcomes)

        return sum(1 for _, published, _ in outcomes if published)

    async def _publish(self, event: IntegrationEvent) -> tuple[bool, str]:
        """Publish one event, reporting success or why it was refused."""
        try:
            await self._publisher.publish(event)
        except Exception as error:
            return False, str(error)

        return True, ""

    async def _settle(self, outcomes: list[tuple[IntegrationEvent, bool, str]]) -> None:
        """Settle a whole batch in one transaction, guarded by the lease.

        Publishing happened before this transaction opened, so no slow work runs
        under the write lock and no other worker holds any of these rows.
        """
        async with self._uow_factory() as uow:
            for event, published, error in outcomes:
                if published:
                    await uow.outbox.mark_as_published(event.event_id, self._worker)
                else:
                    await uow.outbox.mark_failed(event.event_id, error, self._worker)
            await uow.commit()
