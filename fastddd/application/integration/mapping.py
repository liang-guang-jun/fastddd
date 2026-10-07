"""Port mapping domain facts to integration events."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, Protocol

from ...domain.event import DomainEvent
from .outbox import IntegrationEvent

if TYPE_CHECKING:
    from ..execution.context import MessageMetadata


class DomainEventMapper(Protocol):
    """Map domain facts to integration events suitable for the outbox."""

    def map(
        self,
        event: DomainEvent,
        metadata: MessageMetadata | None,
    ) -> Iterable[IntegrationEvent]:
        """Map one domain event to zero or more integration events."""
