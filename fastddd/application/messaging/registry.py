"""Registries for handlers and behaviors."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, TypeVar, cast

from ...domain.event import DomainEvent
from .behavior import Behavior
from .handler import EventHandler, Handler
from .message import Message

TKey = TypeVar("TKey")
TValue = TypeVar("TValue")


class TypeRegistry[TKey, TValue]:
    """Map concrete key types to zero or more registered values."""

    def __init__(self) -> None:
        """Initialize an empty registry."""
        self._items: dict[type[TKey], list[TValue]] = {}

    def register(
        self,
        key_type: type[TKey],
        value: TValue,
    ) -> None:
        """Register a value for the given key type."""
        self._items.setdefault(key_type, []).append(value)

    def resolve(
        self,
        key: TKey,
    ) -> tuple[TValue, ...]:
        """Resolve values registered for the key's concrete type."""
        return self.resolve_type(type(key))

    def resolve_type(
        self,
        key_type: type[TKey],
    ) -> tuple[TValue, ...]:
        """Resolve values registered for the given key type."""
        return tuple(self._items.get(key_type, ()))

    def contains(
        self,
        key_type: type[TKey],
    ) -> bool:
        """Return whether values are registered for the given key type."""
        return bool(self._items.get(key_type))

    def key_types(self) -> tuple[type[TKey], ...]:
        """Return the key types something is registered for."""
        return tuple(self._items)


class HandlerRegistry:
    """Map each application message type to exactly one handler."""

    def __init__(self) -> None:
        """Initialize an empty handler registry."""
        self._registry: TypeRegistry[
            Message,
            Handler[Message, Any],
        ] = TypeRegistry()

    def register[TMessage: Message, TResult](
        self,
        message_type: type[TMessage],
        handler: Handler[TMessage, TResult],
    ) -> None:
        """Register the sole handler for the given message type."""
        if self._registry.contains(message_type):
            raise ValueError(f"Handler already registered: {message_type!r}")

        self._registry.register(
            message_type,
            cast(Handler[Message, Any], handler),
        )

    def resolve[TResult](
        self,
        message: Message,
    ) -> Handler[Message, TResult]:
        """Return the handler registered for the message's concrete type."""
        handlers = self._registry.resolve(message)

        if not handlers:
            raise LookupError(f"No handler registered: {type(message)!r}")

        return cast(
            Handler[Message, TResult],
            handlers[0],
        )

    def message_types(self) -> tuple[type[Message], ...]:
        """Return every message type a handler is registered for.

        A context compares this with its authorization rules, so a use case cannot be
        added without somebody deciding who may send it.
        """
        return self._registry.key_types()


class EventHandlerRegistry:
    """Map each domain event type to zero or more handlers."""

    def __init__(self) -> None:
        """Initialize an empty event handler registry."""
        self._registry: TypeRegistry[
            DomainEvent,
            EventHandler[DomainEvent],
        ] = TypeRegistry()

    def register[TDomainEvent: DomainEvent](
        self,
        event_type: type[TDomainEvent],
        handler: EventHandler[TDomainEvent],
    ) -> None:
        """Register a handler for the given domain event type."""
        self._registry.register(
            event_type,
            cast(EventHandler[DomainEvent], handler),
        )

    def resolve(
        self,
        event: DomainEvent,
    ) -> Sequence[EventHandler[DomainEvent]]:
        """Return all handlers registered for the event's concrete type."""
        return self._registry.resolve(event)


class BehaviorRegistry:
    """Store global and message-specific behavior chains.

    Global behaviors are applied before message-specific behaviors.
    """

    def __init__(self) -> None:
        """Initialize empty global and per-message behavior registries."""
        self._global: list[Behavior[Message, Any]] = []

        self._per_message: TypeRegistry[
            Message,
            Behavior[Message, Any],
        ] = TypeRegistry()

    def register_global[TMessage: Message, TResult](
        self,
        behavior: Behavior[TMessage, TResult],
    ) -> None:
        """Append a behavior to the global behavior chain."""
        self._global.append(cast(Behavior[Message, Any], behavior))

    def register_for[TMessage: Message, TResult](
        self,
        message_type: type[TMessage],
        behavior: Behavior[TMessage, TResult],
    ) -> None:
        """Append a behavior to a message-specific behavior chain."""
        self._per_message.register(
            message_type,
            cast(Behavior[Message, Any], behavior),
        )

    def for_message[TResult](
        self,
        message: Message,
    ) -> list[Behavior[Message, TResult]]:
        """Return the composed behavior chain for the message."""
        specific = self._per_message.resolve(message)

        return [
            cast(Behavior[Message, TResult], behavior)
            for behavior in (*self._global, *specific)
        ]
