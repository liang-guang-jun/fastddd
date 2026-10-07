"""Tests for the messaging adapter's public surface."""

from __future__ import annotations

import fastddd.infrastructure.messaging as messaging
from fastddd.infrastructure.messaging.dispatcher import OutboxDispatcher
from fastddd.infrastructure.messaging.in_memory import (
    InMemoryIntegrationEventPublisher,
)
from fastddd.infrastructure.messaging.transaction import TransactionBehavior
from fastddd.infrastructure.messaging.worker import Dispatcher, OutboxWorker

EXPECTED = {
    "Dispatcher",
    "InMemoryIntegrationEventPublisher",
    "OutboxDispatcher",
    "OutboxWorker",
    "TransactionBehavior",
}


def test_the_surface_is_exactly_what_the_package_publishes() -> None:
    assert set(messaging.__all__) == EXPECTED


def test_every_exported_name_resolves_to_an_attribute() -> None:
    for name in messaging.__all__:
        assert getattr(messaging, name) is not None


def test_every_exported_name_is_the_object_its_module_defines() -> None:
    assert messaging.Dispatcher is Dispatcher
    assert messaging.OutboxDispatcher is OutboxDispatcher
    assert messaging.OutboxWorker is OutboxWorker
    assert messaging.TransactionBehavior is TransactionBehavior
    assert (
        messaging.InMemoryIntegrationEventPublisher is InMemoryIntegrationEventPublisher
    )
