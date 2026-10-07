"""Application layer kernel abstractions."""

from .execution.context import (
    Context,
    MessageMetadata,
    current_context,
    current_context_or_none,
    current_metadata,
    current_unit_of_work,
    current_unit_of_work_or_none,
)
from .integration.mapping import DomainEventMapper
from .integration.outbox import IntegrationEvent, Outbox
from .integration.publisher import EventPublisher
from .integration.registry import IntegrationEventRegistry
from .messaging.behavior import Behavior
from .messaging.bus import MessageBus
from .messaging.handler import CommandHandler, EventHandler, Handler, QueryHandler
from .messaging.message import Command, Message, Query
from .messaging.pipeline import Pipeline
from .messaging.registry import (
    BehaviorRegistry,
    EventHandlerRegistry,
    HandlerRegistry,
)
from .ports import Clock, IdGenerator, ReadStore, UnitOfWork
from .support import require_found

__all__ = [
    "Behavior",
    "BehaviorRegistry",
    "Clock",
    "Command",
    "CommandHandler",
    "Context",
    "DomainEventMapper",
    "EventHandler",
    "EventHandlerRegistry",
    "EventPublisher",
    "Handler",
    "HandlerRegistry",
    "IdGenerator",
    "IntegrationEvent",
    "IntegrationEventRegistry",
    "Message",
    "MessageBus",
    "MessageMetadata",
    "Outbox",
    "Pipeline",
    "Query",
    "QueryHandler",
    "ReadStore",
    "UnitOfWork",
    "current_context",
    "current_context_or_none",
    "current_metadata",
    "current_unit_of_work",
    "current_unit_of_work_or_none",
    "require_found",
]
