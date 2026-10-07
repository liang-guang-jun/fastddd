"""Routing integration events to the consumers registered for their type."""

from __future__ import annotations

from enum import StrEnum

from ..messaging.handler import EventHandler
from .outbox import IntegrationEvent


class UnroutedEventPolicy(StrEnum):
    """What resolving an event type that nobody consumes does.

    Both answers are defensible because the event is already written down: the
    outbox holds it whether or not a consumer exists.
    """

    IGNORE = "ignore"
    """Resolve to no consumers, so the event is published to nobody.

    The default, and the safe one for a relay: a deployment that legitimately
    does not consume a type must not fail because of it. The cost is that a
    misspelled event type looks exactly like a deliberate one.
    """

    RAISE = "raise"
    """Refuse the resolution with a ``LookupError`` naming the type.

    Choose this where an unrouted event must not pass unnoticed. Mind what the
    outbox does with the failure: a publisher that raises makes the dispatcher
    record the event as failed and retry it, so the event stays pending instead
    of being lost — visible, but it will not leave the outbox on its own.
    """


class IntegrationEventRegistry:
    """Map an integration event's ``event_type`` to the consumers that receive it.

    Routing goes through the event's type *string*, never through its Python
    class. The outbox persists ``event_type`` next to a payload, so a consumer
    reading one back holds the same ``IntegrationEvent`` envelope whichever fact
    it carries: the class cannot tell two events apart, and a registry keyed on
    ``type(event)`` would hand every event to every consumer.

    A type may have several consumers, and they are called in registration order.
    Nothing stops one consumer from serving several types.
    """

    def __init__(
        self,
        *,
        on_unrouted: UnroutedEventPolicy = UnroutedEventPolicy.IGNORE,
    ) -> None:
        """Create a registry that decides what an unrouted event type does."""
        self._on_unrouted = on_unrouted
        self._handlers: dict[str, list[EventHandler[IntegrationEvent]]] = {}

    @property
    def on_unrouted(self) -> UnroutedEventPolicy:
        """Return what an event type nobody consumes resolves to."""
        return self._on_unrouted

    def register(
        self,
        event_type: str,
        handler: EventHandler[IntegrationEvent],
    ) -> None:
        """Add a consumer for the given event type, after the ones already there."""
        self._handlers.setdefault(event_type, []).append(handler)

    def resolve(
        self,
        event: IntegrationEvent,
    ) -> tuple[EventHandler[IntegrationEvent], ...]:
        """Return the consumers of an event, in the order they were registered.

        Raises:
            LookupError: If nobody consumes the event's type and ``on_unrouted``
                is ``UnroutedEventPolicy.RAISE``.
        """
        handlers = tuple(self._handlers.get(event.event_type, ()))
        if not handlers and self._on_unrouted is UnroutedEventPolicy.RAISE:
            raise LookupError(
                f"No consumer registered for integration event: {event.event_type!r}"
            )

        return handlers

    def event_types(self) -> tuple[str, ...]:
        """Return every event type a consumer is registered for."""
        return tuple(self._handlers)

    def __len__(self) -> int:
        """Return how many event types have at least one consumer."""
        return len(self._handlers)
