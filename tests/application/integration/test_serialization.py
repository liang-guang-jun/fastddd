"""Tests for rendering domain events as JSON payloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from fastddd.application.integration.outbox import JsonValue
from fastddd.application.integration.serialization import (
    ValueConverter,
    event_payload,
    json_value,
)
from fastddd.domain import DomainEvent, EntityId


class Currency(Enum):
    """Sample enum value."""

    EUR = "eur"


class AccountId(EntityId[int]):
    """Sample entity identity."""

    def __init__(self, value: int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value


@dataclass(frozen=True, slots=True)
class Price:
    """A value object the context knows how to render."""

    cents: int


@dataclass(frozen=True, slots=True)
class AccountRenamed(DomainEvent):
    """Sample domain event mixing the shapes a payload can carry."""

    name: str
    amount: float
    currency: Currency
    account_id: AccountId
    tags: list[str]


def sample_event() -> AccountRenamed:
    """Return a populated sample event."""
    return AccountRenamed(
        name="ada",
        amount=1.5,
        currency=Currency.EUR,
        account_id=AccountId(7),
        tags=["a", "b"],
    )


def test_event_payload_renders_one_entry_per_field() -> None:
    assert event_payload(sample_event()) == {
        "name": "ada",
        "amount": 1.5,
        "currency": "eur",
        "account_id": "7",
        "tags": ["a", "b"],
    }


def test_json_value_passes_through_the_shared_vocabulary() -> None:
    assert json_value(None) is None
    assert json_value(True) is True
    assert json_value(7) == 7
    assert json_value(1.5) == 1.5
    assert json_value("ada") == "ada"


def test_json_value_renders_temporal_and_identity_values_as_text() -> None:
    moment = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)

    assert json_value(moment) == moment.isoformat()
    assert json_value(Currency.EUR) == "eur"
    assert json_value(AccountId(7)) == "7"
    assert json_value(UUID(int=7)) == str(UUID(int=7))


def test_json_value_renders_sequences_and_mappings_recursively() -> None:
    assert json_value([AccountId(1), "a"]) == ["1", "a"]
    assert json_value((1, 2)) == [1, 2]
    assert json_value({"a": AccountId(1)}) == {"a": "1"}


def test_json_value_falls_back_to_text_for_unknown_objects() -> None:
    assert json_value(Price(cents=5)) == str(Price(cents=5))


def test_a_converter_gets_first_refusal_over_the_shared_vocabulary() -> None:
    def render_price(value: object) -> JsonValue | None:
        if isinstance(value, Price):
            return value.cents
        return None

    assert json_value(Price(cents=5), render_price) == 5
    assert event_payload(sample_event(), render_price)["currency"] == "eur"


def test_a_converter_that_declines_falls_through_to_the_shared_vocabulary() -> None:
    def decline(value: object) -> JsonValue | None:
        return None

    converter: ValueConverter = decline

    assert json_value(AccountId(7), converter) == "7"
