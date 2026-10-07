"""Tests for the event publisher abstraction."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import uuid4

from fastddd.application.integration.outbox import IntegrationEvent
from fastddd.application.integration.publisher import EventPublisher


class RecordingPublisher(EventPublisher):
    """Publisher recording every event type it publishes."""

    def __init__(self) -> None:
        self.published: list[str] = []

    async def publish(self, event: IntegrationEvent) -> None:
        self.published.append(event.event_type)

    async def publish_all(self, events: list[IntegrationEvent]) -> None:
        for event in events:
            await self.publish(event)


def make(event_type: str) -> IntegrationEvent:
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


def test_the_publisher_contract_is_abstract() -> None:
    assert inspect.isabstract(EventPublisher)


async def test_a_publisher_publishes_one_event() -> None:
    publisher = RecordingPublisher()

    await publisher.publish(make("account.renamed"))

    assert publisher.published == ["account.renamed"]


async def test_a_publisher_publishes_several_events_in_order() -> None:
    publisher = RecordingPublisher()

    await publisher.publish_all([make("first"), make("second")])

    assert publisher.published == ["first", "second"]
