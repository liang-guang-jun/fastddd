"""The counter's use cases: messages, handlers and the fact-to-event mapper.

Note what the handlers depend on: the **domain's** ``AggregateRepository``
contract and the **application's** ``ReadStore``, ``Clock`` and ``IdGenerator``
ports. No SQLAlchemy import appears in this file, so this context can be tested
against an in-memory repository and a frozen clock, and the same handlers run on
SQLite and on Postgres.

Handlers never commit. The pipeline's transaction behaviour owns the transaction,
which is what makes one command's write and the events it produces leave
together or not at all.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from fastddd.application import (
    Clock,
    Command,
    CommandHandler,
    IdGenerator,
    IntegrationEvent,
    MessageMetadata,
    Query,
    QueryHandler,
    ReadStore,
    require_found,
)
from fastddd.application.integration import UNVERSIONED
from fastddd.domain import AggregateRepository, DomainEvent

from .domain import Counter, CounterChanged, CounterId, CounterNotFoundError

COUNTER_CHANGED = "counter.changed"
"""The type string this context publishes a counter change under.

Routing goes through this string, not through a Python class: the outbox stores
it next to a payload, so a consumer reads every fact back as the same
``IntegrationEvent`` envelope and the class cannot tell two facts apart.
"""


@dataclass(frozen=True, slots=True)
class CounterView:
    """What a counter endpoint answers with.

    A flat projection rather than the aggregate: the read side and the write side
    are allowed to disagree about shape, and a client that depends on the
    aggregate's internals makes every refactor a breaking change.
    """

    counter_id: UUID
    label: str
    total: int


@dataclass(frozen=True, slots=True)
class CreateCounter(Command[CounterView]):
    """Ask for a new counter."""

    label: str


@dataclass(frozen=True, slots=True)
class IncrementCounter(Command[CounterView]):
    """Ask a counter to advance."""

    counter_id: UUID
    by: int = 1


@dataclass(frozen=True, slots=True)
class GetCounter(Query[CounterView]):
    """Ask for one counter, as the read side sees it."""

    counter_id: UUID


class CreateCounterHandler(CommandHandler[CreateCounter, CounterView]):
    """Mint an identity, build the aggregate and store it."""

    def __init__(
        self,
        counters: AggregateRepository[Counter, UUID],
        identifiers: IdGenerator,
    ) -> None:
        """Store the write-side port and the identity source."""
        self._counters = counters
        self._identifiers = identifiers

    async def handle(self, command: CreateCounter) -> CounterView:
        """Create the counter and answer with its first state."""
        counter = Counter.create(CounterId(self._identifiers.new()), command.label)
        await self._counters.save(counter)

        return _view(counter)


class IncrementCounterHandler(CommandHandler[IncrementCounter, CounterView]):
    """Load one aggregate, change it, and store it."""

    def __init__(self, counters: AggregateRepository[Counter, UUID]) -> None:
        """Store the write-side port."""
        self._counters = counters

    async def handle(self, command: IncrementCounter) -> CounterView:
        """Advance the counter named by the command.

        Raises:
            CounterNotFoundError: If no counter has that identity.
        """
        counter = await require_found(
            self._counters.get(CounterId(command.counter_id)),
            subject=f"counter {command.counter_id}",
            error_type=CounterNotFoundError,
        )
        counter.increment(by=command.by)
        await self._counters.save(counter)

        return _view(counter)


class GetCounterHandler(QueryHandler[GetCounter, CounterView]):
    """Answer from the read side, never by loading an aggregate."""

    def __init__(self, read_model: ReadStore[GetCounter, CounterView]) -> None:
        """Store the read-side port."""
        self._read_model = read_model

    async def handle(self, query: GetCounter) -> CounterView:
        """Return the projection the read side holds for this query."""
        return await self._read_model.query(query)


class CounterEventMapper:
    """Turn this context's facts into the events other contexts consume.

    ``DomainEventMapper`` is a ``Protocol``, so having this shape *is* the
    contract -- there is no base class to inherit. The two things a recorded fact
    does not know -- when it happened, and which identifier the delivery carries
    -- come from injected ports instead of ``datetime.now`` and ``uuid4`` in this
    module, which is what lets a test assert on the exact bytes of a published
    event.
    """

    def __init__(self, *, clock: Clock, identifiers: IdGenerator) -> None:
        """Store the moment source and the identifier source."""
        self._clock = clock
        self._identifiers = identifiers

    def map(
        self,
        event: DomainEvent,
        metadata: MessageMetadata | None,
    ) -> Iterable[IntegrationEvent]:
        """Translate one domain event into zero or more integration events.

        Returning nothing for a fact this context does not publish is the normal
        case, not an error: an aggregate may record internal facts nobody outside
        needs.
        """
        if not isinstance(event, CounterChanged):
            return ()

        return (
            IntegrationEvent(
                event_type=COUNTER_CHANGED,
                payload={
                    "counter_id": str(event.counter_id),
                    "label": event.label,
                    "total": event.total,
                },
                aggregate_type="Counter",
                aggregate_id=str(event.counter_id),
                # This aggregate is not versioned, and says so instead of
                # inventing a number: a consumer that needs ordering must not
                # rely on where this fact sits.
                aggregate_version=UNVERSIONED,
                event_id=self._identifiers.new(),
                occurred_at=self._clock.now(),
                correlation_id=None if metadata is None else metadata.correlation_id,
                # The command that changed the aggregate is this fact's cause, so
                # a consumer can walk the chain back to the request.
                causation_id=None if metadata is None else metadata.message_id,
                tenant_id=None if metadata is None else metadata.tenant_id,
            ),
        )


def _view(counter: Counter) -> CounterView:
    """Return the projection of one aggregate."""
    return CounterView(
        counter_id=counter.id.value,
        label=counter.label,
        total=counter.total,
    )
