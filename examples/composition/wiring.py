"""The object graph: who serves which message, and who consumes which event.

This is plain Python that reads the container, and it is the shape a kernel
integration is supposed to take. ``MessageBus``, ``HandlerRegistry`` and
``BehaviorRegistry`` are values, not services: they exist to hold registrations,
they are built once, and writing them out here makes the order visible instead of
hiding it inside a provider.

The same goes for the *callables*. ``TransactionBehavior(uow_factory, mapper)``,
``OutboxDispatcher(uow_factory, publisher)`` and ``projection_consumer(name,
handler, uow_factory)`` all take a factory rather than a unit of work, because
each of them needs to open more than one transaction over its life. Handing them
``container.uow`` -- a provider, which is a callable -- is the whole trick.
"""

from __future__ import annotations

from dataclasses import dataclass

from fastddd.application import (
    BehaviorRegistry,
    HandlerRegistry,
    IntegrationEventRegistry,
    MessageBus,
)
from fastddd.infrastructure import (
    InMemoryIntegrationEventPublisher,
    LoggingBehavior,
    OutboxDispatcher,
    OutboxWorker,
    TransactionBehavior,
    projection_consumer,
)

from ..counter.application import (
    COUNTER_CHANGED,
    CreateCounter,
    CreateCounterHandler,
    GetCounter,
    GetCounterHandler,
    IncrementCounter,
    IncrementCounterHandler,
)
from ..counter.persistence import CounterTotalsProjection
from .container import AppContainer


@dataclass(frozen=True, slots=True)
class AppState:
    """What the process holds for its lifetime, assembled once at startup."""

    message_bus: MessageBus
    dispatcher: OutboxDispatcher
    worker: OutboxWorker


def build_handlers(container: AppContainer) -> HandlerRegistry:
    """Register exactly one handler per message type.

    The registry refuses a second handler for the same message, so a use case
    cannot be given two implementations by accident.
    """
    handlers = HandlerRegistry()
    handlers.register(
        CreateCounter,
        CreateCounterHandler(container.counter_repository(), container.identifiers()),
    )
    handlers.register(
        IncrementCounter,
        IncrementCounterHandler(container.counter_repository()),
    )
    handlers.register(GetCounter, GetCounterHandler(container.counter_read_model()))

    return handlers


def build_behaviors(container: AppContainer) -> BehaviorRegistry:
    """Register the middleware every message runs through.

    Order matters, and the reason is concrete rather than aesthetic: the
    transaction behaviour is the one that enters the execution context, so it has
    to be outermost for the behaviors inside it to see that context. Register the
    logging behaviour first and every log line loses the request it belongs to.
    """
    behaviors = BehaviorRegistry()
    behaviors.register_global(
        TransactionBehavior(container.uow, container.counter_event_mapper())
    )
    behaviors.register_global(LoggingBehavior("example.message"))

    return behaviors


def build_consumers(container: AppContainer) -> IntegrationEventRegistry:
    """Route each integration event type to the consumers of it.

    Routing goes by the event's type *string*, because the outbox stores the type
    next to a payload and every event is read back as the same
    ``IntegrationEvent``: the class cannot tell two facts apart.
    """
    consumers = IntegrationEventRegistry()
    consumers.register(
        COUNTER_CHANGED,
        # A projection is a consumer whose receipts live in their own namespace,
        # so it can never collide with -- and therefore never suppress -- a
        # handler that happens to share its name.
        projection_consumer(
            "counter_totals",
            CounterTotalsProjection(),
            container.uow,
        ),
    )

    return consumers


def build_state(container: AppContainer) -> AppState:
    """Assemble the object graph the process runs on."""
    behaviors = build_behaviors(container)
    handlers = build_handlers(container)
    publisher = InMemoryIntegrationEventPublisher(build_consumers(container))
    dispatcher = OutboxDispatcher(
        container.uow,
        publisher,
        batch_size=100,
        lease_seconds=300.0,
    )
    worker = OutboxWorker(
        [dispatcher],
        interval_seconds=1.0,
        # The sweeper is what keeps the outbox and the inbox from growing without
        # bound; without it they are a leak with a schema.
        sweeper=container.maintenance(),
        cleanup_interval_seconds=300.0,
        retention_seconds=86_400.0,
    )

    return AppState(
        message_bus=MessageBus(handlers, behaviors),
        dispatcher=dispatcher,
        worker=worker,
    )
