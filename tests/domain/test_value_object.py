"""Tests for the identity-less immutable value object base."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from fastddd.domain.value_object import ValueObject


@dataclass(frozen=True, slots=True)
class Money(ValueObject):
    """Sample value object compared by its attributes."""

    amount: int
    currency: str


def test_the_base_declares_no_instance_state() -> None:
    assert ValueObject.__slots__ == ()


def test_the_bare_base_rejects_ad_hoc_attributes() -> None:
    value = ValueObject()

    with pytest.raises(AttributeError):
        value.anything = 1  # type: ignore[attr-defined]


def test_concrete_value_objects_compare_by_attributes() -> None:
    assert Money(amount=1, currency="EUR") == Money(amount=1, currency="EUR")
    assert Money(amount=1, currency="EUR") != Money(amount=1, currency="USD")


def test_concrete_value_objects_are_hashable() -> None:
    price = Money(amount=1, currency="EUR")

    assert hash(price) == hash(Money(amount=1, currency="EUR"))
    assert len({price, Money(amount=1, currency="EUR")}) == 1
