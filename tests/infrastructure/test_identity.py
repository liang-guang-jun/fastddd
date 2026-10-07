"""Tests for the one identity source the infrastructure layer uses."""

from __future__ import annotations

from uuid import UUID

from fastddd.application.ports import IdGenerator
from fastddd.infrastructure.identity import UuidGenerator


def test_the_generator_returns_a_fresh_uuid_each_time() -> None:
    first = UuidGenerator.new()
    second = UuidGenerator.new()

    assert isinstance(first, UUID)
    assert first != second


def test_an_instance_satisfies_the_application_identity_port() -> None:
    generator: IdGenerator = UuidGenerator()

    assert isinstance(generator.new(), UUID)
