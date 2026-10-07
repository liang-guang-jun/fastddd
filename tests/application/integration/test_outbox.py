"""Tests for the integration-event outbox."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from fastddd.application.integration.outbox import (
    UNVERSIONED,
    IntegrationEvent,
    Outbox,
)


def test_an_event_keeps_the_identity_and_timestamp_it_was_given() -> None:
    event_id = uuid4()
    occurred_at = datetime(2026, 1, 1, tzinfo=UTC)
    event = IntegrationEvent(
        event_type="account.renamed",
        payload={"name": "ada"},
        aggregate_type="Account",
        aggregate_id="1",
        aggregate_version=UNVERSIONED,
        event_id=event_id,
        occurred_at=occurred_at,
    )

    assert event.event_id == event_id
    assert event.occurred_at == occurred_at
    assert event.schema_version == 1
    assert event.correlation_id is None
    assert event.causation_id is None
    assert event.tenant_id is None
    assert event.payload == {"name": "ada"}


def test_an_unversioned_event_makes_no_ordering_claim() -> None:
    assert UNVERSIONED == 0


def test_an_event_rejects_a_missing_type() -> None:
    with pytest.raises(ValueError, match="event_type is required"):
        IntegrationEvent(
            event_type="",
            payload={},
            aggregate_type="Account",
            aggregate_id="1",
            aggregate_version=0,
            event_id=uuid4(),
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_an_event_rejects_a_schema_version_below_one() -> None:
    with pytest.raises(ValueError, match="schema_version must be >= 1"):
        IntegrationEvent(
            event_type="account.renamed",
            payload={},
            aggregate_type="Account",
            aggregate_id="1",
            aggregate_version=0,
            schema_version=0,
            event_id=uuid4(),
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_an_event_rejects_a_negative_aggregate_version() -> None:
    with pytest.raises(ValueError, match="aggregate_version must be >= 0"):
        IntegrationEvent(
            event_type="account.renamed",
            payload={},
            aggregate_type="Account",
            aggregate_id="1",
            aggregate_version=-1,
            event_id=uuid4(),
            occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
        )


def test_an_event_rejects_a_naive_timestamp() -> None:
    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        IntegrationEvent(
            event_type="account.renamed",
            payload={},
            aggregate_type="Account",
            aggregate_id="1",
            aggregate_version=0,
            event_id=uuid4(),
            occurred_at=datetime(2026, 1, 1),
        )


def test_the_outbox_contract_is_abstract() -> None:
    assert inspect.isabstract(Outbox)
