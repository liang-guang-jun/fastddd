"""Integration kernel: event mapping, outbox, publisher, and serialization."""

from .mapping import DomainEventMapper
from .outbox import UNVERSIONED, IntegrationEvent, JsonValue, Outbox
from .publisher import EventPublisher
from .registry import IntegrationEventRegistry, UnroutedEventPolicy
from .serialization import ValueConverter, event_payload, json_value

__all__ = [
    "UNVERSIONED",
    "DomainEventMapper",
    "EventPublisher",
    "IntegrationEvent",
    "IntegrationEventRegistry",
    "JsonValue",
    "Outbox",
    "UnroutedEventPolicy",
    "ValueConverter",
    "event_payload",
    "json_value",
]
