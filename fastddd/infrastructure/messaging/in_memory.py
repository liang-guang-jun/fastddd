"""In-process publisher for the single-node SQLite deployment."""

from __future__ import annotations

from ...application.integration.outbox import IntegrationEvent
from ...application.integration.publisher import EventPublisher
from ...application.integration.registry import IntegrationEventRegistry


class InMemoryIntegrationEventPublisher(EventPublisher):
    """Deliver each event to the consumers its registry holds for the type.

    A failing consumer reaches the dispatcher, which records retry state in the
    reliable outbox; the registry decides what an unrouted type does instead.
    """

    def __init__(self, registry: IntegrationEventRegistry) -> None:
        """Route every event through the registry the composition root filled."""
        self._registry = registry

    async def publish(self, event: IntegrationEvent) -> None:
        """Deliver to each consumer of the event's type, in registration order."""
        for handler in self._registry.resolve(event):
            await handler.handle(event)

    async def publish_all(self, events: list[IntegrationEvent]) -> None:
        """Publish events in their durable outbox order."""
        for event in events:
            await self.publish(event)
