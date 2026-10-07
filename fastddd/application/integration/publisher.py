"""EventPublisher abstraction: dispatch domain events to handlers."""

from __future__ import annotations

from abc import ABC, abstractmethod

from .outbox import IntegrationEvent


class EventPublisher(ABC):
    """Publishes domain events to their registered handlers.

    Unlike MessageBus, publishing is fan-out. Failures propagate to the
    dispatcher, which records retry state in the reliable outbox.
    """

    @abstractmethod
    async def publish(self, event: IntegrationEvent) -> None:
        """Publish a single domain event."""
        raise NotImplementedError

    @abstractmethod
    async def publish_all(self, events: list[IntegrationEvent]) -> None:
        """Publish multiple domain events in order."""
        raise NotImplementedError
