"""Tests for the in-process integration-event publisher."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fastddd.application.integration.outbox import IntegrationEvent
from fastddd.application.integration.registry import IntegrationEventRegistry
from fastddd.application.messaging.handler import EventHandler
from fastddd.infrastructure.messaging import InMemoryIntegrationEventPublisher


class _Recorder(EventHandler[IntegrationEvent]):
    """A consumer that remembers everything it was handed."""

    def __init__(self, label: str) -> None:
        self.label = label
        self.seen: list[IntegrationEvent] = []

    async def handle(self, event: IntegrationEvent) -> None:
        self.seen.append(event)


class _Refuser(EventHandler[IntegrationEvent]):
    """A consumer whose delivery always fails."""

    async def handle(self, event: IntegrationEvent) -> None:
        raise RuntimeError("consumer down")


def _event(event_type: str = "account.opened") -> IntegrationEvent:
    """Return an event to publish."""
    return IntegrationEvent(
        event_type=event_type,
        payload={"name": "acme"},
        aggregate_type="Account",
        aggregate_id="1",
        aggregate_version=1,
        event_id=uuid4(),
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def test_an_event_reaches_every_consumer_registered_for_its_type() -> None:
    registry = IntegrationEventRegistry()
    first, second = _Recorder("first"), _Recorder("second")
    registry.register("account.opened", first)
    registry.register("account.opened", second)

    await InMemoryIntegrationEventPublisher(registry).publish(_event())

    assert [len(first.seen), len(second.seen)] == [1, 1]


async def test_an_event_only_reaches_the_consumers_of_its_own_type() -> None:
    registry = IntegrationEventRegistry()
    interested, uninterested = _Recorder("interested"), _Recorder("uninterested")
    registry.register("account.opened", interested)
    registry.register("account.closed", uninterested)

    await InMemoryIntegrationEventPublisher(registry).publish(_event("account.opened"))

    assert len(interested.seen) == 1
    assert uninterested.seen == []


async def test_consumers_are_called_in_the_order_they_were_registered() -> None:
    registry = IntegrationEventRegistry()
    first, second = _Recorder("first"), _Recorder("second")
    registry.register("account.opened", first)
    registry.register("account.opened", second)

    await InMemoryIntegrationEventPublisher(registry).publish(_event())

    assert [recorder.label for recorder in (first, second)] == ["first", "second"]


async def test_an_unrouted_event_reaches_nobody() -> None:
    registry = IntegrationEventRegistry()
    recorder = _Recorder("recorder")
    registry.register("account.closed", recorder)

    await InMemoryIntegrationEventPublisher(registry).publish(_event("account.opened"))

    assert recorder.seen == []


async def test_a_failing_consumer_reaches_the_caller() -> None:
    # The dispatcher is what records retry state, so it has to see the failure.
    registry = IntegrationEventRegistry()
    registry.register("account.opened", _Refuser())

    with pytest.raises(RuntimeError, match="consumer down"):
        await InMemoryIntegrationEventPublisher(registry).publish(_event())


async def test_a_batch_is_published_in_the_order_the_outbox_stored_it() -> None:
    registry = IntegrationEventRegistry()
    recorder = _Recorder("recorder")
    registry.register("account.opened", recorder)
    registry.register("account.closed", recorder)

    await InMemoryIntegrationEventPublisher(registry).publish_all(
        [_event("account.opened"), _event("account.closed")]
    )

    assert [event.event_type for event in recorder.seen] == [
        "account.opened",
        "account.closed",
    ]
