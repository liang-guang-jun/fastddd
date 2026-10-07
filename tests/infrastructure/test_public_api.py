"""Tests for the public surface of the infrastructure package."""

from __future__ import annotations

from importlib import import_module

import fastddd.infrastructure as infrastructure

ADAPTERS = ("configuration", "logging", "messaging", "persistence")
OWN_MODULES = {
    "InboxConsumer",
    "SystemClock",
    "UuidGenerator",
    "claim_inbox_message",
    "projection_consumer",
}


def test_the_public_surface_has_no_duplicates() -> None:
    assert len(infrastructure.__all__) == len(set(infrastructure.__all__))


def test_every_exported_name_resolves_to_an_attribute() -> None:
    missing = [
        name for name in infrastructure.__all__ if not hasattr(infrastructure, name)
    ]

    assert missing == []


def test_the_surface_is_what_the_adapters_publish_plus_its_own_modules() -> None:
    published: set[str] = set()
    for adapter in ADAPTERS:
        module = import_module(f"fastddd.infrastructure.{adapter}")
        published |= set(module.__all__)

    assert set(infrastructure.__all__) == published | OWN_MODULES


def test_exports_are_the_objects_their_modules_define() -> None:
    clock = import_module("fastddd.infrastructure.clock")
    identity = import_module("fastddd.infrastructure.identity")
    inbox = import_module("fastddd.infrastructure.inbox")
    ports = import_module("fastddd.application.ports")
    resolver = import_module("fastddd.infrastructure.configuration.resolver")

    assert infrastructure.SystemClock is clock.SystemClock
    assert infrastructure.UuidGenerator is identity.UuidGenerator
    assert infrastructure.InboxConsumer is inbox.InboxConsumer
    assert infrastructure.projection_consumer is inbox.projection_consumer
    assert infrastructure.ConfigResolver is resolver.ConfigResolver
    assert infrastructure.create_database_backend is not ports.Clock
