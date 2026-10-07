"""Tests for the domain-event mapper port."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from fastddd.application.execution.context import MessageMetadata
from fastddd.application.integration.mapping import DomainEventMapper
from fastddd.application.integration.outbox import IntegrationEvent
from fastddd.domain import DomainEvent


@dataclass(frozen=True, slots=True)
class AccountRenamed(DomainEvent):
    """Sample domain event."""

    name: str


class RenamedMapper:
    """Concrete mapper turning the sample event into one integration event."""

    def map(
        self,
        event: DomainEvent,
        metadata: MessageMetadata | None,
    ) -> list[IntegrationEvent]:
        name = event.name if isinstance(event, AccountRenamed) else ""
        return [
            IntegrationEvent(
                event_type="account.renamed",
                payload={"name": name},
                aggregate_type="Account",
                aggregate_id="1",
                aggregate_version=0,
                event_id=uuid4(),
                occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ]


def test_a_mapper_shaped_like_the_port_is_usable_structurally() -> None:
    mapper: DomainEventMapper = RenamedMapper()

    events = list(mapper.map(AccountRenamed(name="ada"), None))

    assert len(events) == 1
    assert events[0].event_type == "account.renamed"
    assert events[0].payload == {"name": "ada"}
