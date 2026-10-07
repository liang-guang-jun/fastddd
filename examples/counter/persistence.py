"""The counter's adapters: its rows, its write model, its read model, its consumer.

Everything SQLAlchemy lives here, below the port the handlers were written
against. The tables hang off the kernel's ``Base``, so one ``create_all`` -- and
one Alembic autogenerate -- sees the kernel's outbox and inbox tables and this
context's tables together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import ColumnElement, DateTime, Integer, String, Uuid
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Mapped, mapped_column

from fastddd.application import (
    EventHandler,
    IntegrationEvent,
    ReadStore,
    current_unit_of_work,
)
from fastddd.infrastructure import SqlAlchemyMappedRepository, SqlAlchemyUnitOfWork
from fastddd.infrastructure.persistence.sqlalchemy.models import Base

from .application import CounterView, GetCounter
from .domain import Counter, CounterId, CounterNotFoundError


class CounterRecord(Base):
    """Row one counter is stored in.

    Named ``example_counters`` because an application shares one database with
    whatever else is in it; a table called ``counters`` would eventually collide.
    """

    __tablename__ = "example_counters"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    label: Mapped[str] = mapped_column(String(50))
    total: Mapped[int] = mapped_column(Integer)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CounterProjectionRecord(Base):
    """Row the read model is stored in.

    The read model is allowed to be shaped for the query instead of for the
    aggregate: it is a cache of what queries need, and it is rebuilt from events
    rather than from the write model.
    """

    __tablename__ = "example_counter_totals"

    counter_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    label: Mapped[str] = mapped_column(String(50))
    total: Mapped[int] = mapped_column(Integer)


class CounterMapper:
    """Translate the counter to and from its row.

    ``AggregateRecordMapper`` is a ``Protocol``, so this class declares no base:
    its four methods are the whole contract. Liveness appears twice on purpose --
    ``is_deleted`` inspects a row already loaded, ``not_deleted`` is the predicate
    a query needs to skip deleted rows -- and both answer from the same column.
    """

    def is_deleted(self, record: CounterRecord) -> bool:
        """Return whether the row stands for a soft-deleted aggregate."""
        return record.deleted_at is not None

    def not_deleted(self) -> ColumnElement[bool]:
        """Return the predicate selecting rows that are still live."""
        return CounterRecord.deleted_at.is_(None)

    def to_domain(self, record: CounterRecord) -> Counter:
        """Rebuild the aggregate from its row, without emitting events."""
        return Counter(
            CounterId(record.id),
            label=record.label,
            total=record.total,
            deleted_at=record.deleted_at,
        )

    def to_record(
        self, aggregate: Counter, record: CounterRecord | None
    ) -> CounterRecord:
        """Return the row to store, patching the loaded one when there is one."""
        target = record if record is not None else CounterRecord(id=aggregate.id.value)
        target.label = aggregate.label
        target.total = aggregate.total
        target.deleted_at = aggregate.deleted_at

        return target


class CounterRepository(SqlAlchemyMappedRepository[Counter, CounterRecord, UUID]):
    """Write side: bind the aggregate to the ambient unit of work.

    Declaring the two class variables is the whole adapter; loading,
    soft-delete filtering and insert-or-update come from the base class. The
    repository holds no session -- it resolves the unit of work bound to the
    current command on every call -- so one instance can serve every request and
    it is safe to register as a singleton.
    """

    record_type = CounterRecord
    mapper = CounterMapper()


class CounterReadStore(ReadStore[GetCounter, CounterView]):
    """Read side: answer from the projection table, not from the write model.

    This is a separate session from the command's transaction, and that is the
    point: the read side reads committed state, so it never blocks on, or sees
    half of, a write in flight.
    """

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        """Store the factory this read side opens its own session with."""
        self._session_factory = session_factory

    async def query(self, query: GetCounter) -> CounterView:
        """Return the projected counter.

        Raises:
            CounterNotFoundError: If the read model holds no row for it. A
                projection that has not caught up yet is indistinguishable from a
                counter that never existed, which is what eventual consistency
                costs the read side.
        """
        async with self._session_factory() as session:
            record = await session.get(CounterProjectionRecord, query.counter_id)
            if record is None:
                raise CounterNotFoundError(f"counter {query.counter_id} does not exist")

            return CounterView(
                counter_id=record.counter_id,
                label=record.label,
                total=record.total,
            )


@dataclass(frozen=True, slots=True)
class CounterChangedPayload:
    """The part of a ``counter.changed`` fact this consumer understands.

    An integration event arrives as a string next to a JSON payload, so a
    consumer validates the shape it is about to act on instead of trusting a type
    it cannot see. This is where the producer's promise becomes the consumer's
    assumption, checked.
    """

    counter_id: UUID
    label: str
    total: int

    @classmethod
    def of(cls, event: IntegrationEvent) -> CounterChangedPayload:
        """Read the payload, refusing one this consumer cannot apply.

        Raises:
            ValueError: If a field is missing or is not the type the read model
                stores.
        """
        counter_id = event.payload.get("counter_id")
        label = event.payload.get("label")
        total = event.payload.get("total")
        if not isinstance(counter_id, str):
            raise ValueError(f"{event.event_type} has no counter_id")
        if not isinstance(label, str):
            raise ValueError(f"{event.event_type} has no label")
        if not isinstance(total, int) or isinstance(total, bool):
            raise ValueError(f"{event.event_type} has no integer total")

        return cls(UUID(counter_id), label, total)


class CounterTotalsProjection(EventHandler[IntegrationEvent]):
    """Rebuild the read model from the events the outbox delivers.

    The handler is deliberately not defensive about redelivery: the receipt the
    inbox consumer takes makes a redelivery a no-op, and a rollback drops the
    receipt so the event is delivered again. Doing that work here as well would
    be a second, weaker copy of a guarantee the kernel already gives.
    """

    async def handle(self, event: IntegrationEvent) -> None:
        """Apply one ``counter.changed`` fact to the read model."""
        changed = CounterChangedPayload.of(event)
        session = _ambient_session()
        record = await session.get(CounterProjectionRecord, changed.counter_id)
        if record is None:
            session.add(
                CounterProjectionRecord(
                    counter_id=changed.counter_id,
                    label=changed.label,
                    total=changed.total,
                )
            )
            return

        record.label = changed.label
        record.total = changed.total


def _ambient_session() -> AsyncSession:
    """Return the session of the unit of work the consumer is running in.

    A projection must write through the transaction its consumer already opened,
    not through one of its own: that is what makes the receipt and the update
    commit together, and a failure leave neither behind.

    Raises:
        LookupError: If this runs outside a SQLAlchemy unit of work, which means
            the consumer was wired with something else.
    """
    uow = current_unit_of_work()
    if not isinstance(uow, SqlAlchemyUnitOfWork):
        raise LookupError("the projection runs outside a SQLAlchemy unit of work")

    return uow.session
