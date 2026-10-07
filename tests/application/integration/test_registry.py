"""Tests for routing integration events to the consumers that want them."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fastddd.application.integration import (
    IntegrationEvent,
    IntegrationEventRegistry,
    UnroutedEventPolicy,
)
from fastddd.application.messaging.handler import EventHandler


class _Consumer(EventHandler[IntegrationEvent]):
    """Record what one consumer was handed, so tests can tell them apart."""

    def __init__(self) -> None:
        self.seen: list[IntegrationEvent] = []

    async def handle(self, event: IntegrationEvent) -> None:
        self.seen.append(event)


def _event(event_type: str) -> IntegrationEvent:
    """Return a minimal event of the given type."""
    return IntegrationEvent(
        event_type=event_type,
        payload={},
        aggregate_type="Account",
        aggregate_id="1",
        aggregate_version=0,
        event_id=uuid4(),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_nothing_is_routed_before_a_consumer_is_registered() -> None:
    registry = IntegrationEventRegistry()

    assert len(registry) == 0
    assert registry.event_types() == ()
    assert registry.resolve(_event("account.opened")) == ()


def test_a_consumer_is_returned_for_the_type_it_was_registered_for() -> None:
    registry = IntegrationEventRegistry()
    consumer = _Consumer()

    registry.register("account.opened", consumer)

    assert registry.resolve(_event("account.opened")) == (consumer,)
    assert registry.resolve(_event("account.closed")) == ()


def test_every_consumer_of_a_type_is_returned_in_registration_order() -> None:
    registry = IntegrationEventRegistry()
    first, second = _Consumer(), _Consumer()

    registry.register("account.opened", first)
    registry.register("account.opened", second)

    assert registry.resolve(_event("account.opened")) == (first, second)


def test_one_consumer_may_serve_several_types() -> None:
    registry = IntegrationEventRegistry()
    consumer = _Consumer()

    registry.register("account.opened", consumer)
    registry.register("account.closed", consumer)

    assert registry.resolve(_event("account.closed")) == (consumer,)


def test_routing_looks_only_at_the_event_type() -> None:
    registry = IntegrationEventRegistry()
    consumer = _Consumer()
    registry.register("account.opened", consumer)

    same_type_other_payload = IntegrationEvent(
        event_type="account.opened",
        payload={"name": "acme"},
        aggregate_type="Workspace",
        aggregate_id="42",
        aggregate_version=7,
        event_id=uuid4(),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert registry.resolve(same_type_other_payload) == (consumer,)


def test_the_registry_reports_the_types_it_routes() -> None:
    registry = IntegrationEventRegistry()

    registry.register("account.opened", _Consumer())
    registry.register("account.closed", _Consumer())
    registry.register("account.closed", _Consumer())

    assert len(registry) == 2
    assert registry.event_types() == ("account.opened", "account.closed")


def test_an_unrouted_type_is_ignored_by_default() -> None:
    registry = IntegrationEventRegistry()

    assert registry.on_unrouted is UnroutedEventPolicy.IGNORE
    assert registry.resolve(_event("nobody.wants.this")) == ()


def test_the_raising_policy_refuses_an_unrouted_type() -> None:
    registry = IntegrationEventRegistry(on_unrouted=UnroutedEventPolicy.RAISE)

    with pytest.raises(LookupError, match=r"nobody\.wants\.this"):
        registry.resolve(_event("nobody.wants.this"))


def test_the_raising_policy_still_resolves_a_routed_type() -> None:
    registry = IntegrationEventRegistry(on_unrouted=UnroutedEventPolicy.RAISE)
    consumer = _Consumer()

    registry.register("account.opened", consumer)

    assert registry.resolve(_event("account.opened")) == (consumer,)
    assert registry.on_unrouted is UnroutedEventPolicy.RAISE
