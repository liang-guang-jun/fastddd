"""Tests for the domain event marker base."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass

import pytest

from fastddd.domain.event import DomainEvent


@dataclass(frozen=True, slots=True)
class Renamed(DomainEvent):
    """Concrete sample event."""

    name: str


def test_a_domain_event_may_be_subclassed() -> None:
    assert isinstance(Renamed(name="a"), DomainEvent)


def test_concrete_events_compare_by_value() -> None:
    assert Renamed(name="a") == Renamed(name="a")
    assert Renamed(name="a") != Renamed(name="b")


def test_frozen_events_reject_mutation() -> None:
    event = Renamed(name="a")

    with pytest.raises(FrozenInstanceError):
        event.name = "b"  # type: ignore[misc]
