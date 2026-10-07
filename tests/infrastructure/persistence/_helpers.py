"""Sample write model shared by the persistence adapter tests."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    Boolean,
    ColumnElement,
    DateTime,
    Float,
    Integer,
    String,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from fastddd.domain import Aggregate, DomainEvent, EntityId
from fastddd.infrastructure.persistence.sqlalchemy.models import Base
from fastddd.infrastructure.persistence.sqlalchemy.repository import (
    SqlAlchemyMappedRepository,
)


class CounterRecord(Base):
    """Row one sample aggregate is stored in."""

    __tablename__ = "test_counters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(50))
    total: Mapped[int] = mapped_column(Integer)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class TicketRecord(Base):
    """Row ordered by every kind of column a cursor has to restore."""

    __tablename__ = "test_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    label: Mapped[str] = mapped_column(String(50))
    note: Mapped[str | None] = mapped_column(String(50), nullable=True)
    score: Mapped[float] = mapped_column(Float)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    urgent: Mapped[bool] = mapped_column(Boolean)
    token: Mapped[UUID] = mapped_column(Uuid)


class CounterId(EntityId[int]):
    """Identity of the sample aggregate."""

    def __init__(self, value: int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value


@dataclass(frozen=True)
class CounterChanged(DomainEvent):
    """Fact a sample aggregate records whenever it changes."""

    total: int


class Counter(Aggregate[int]):
    """Sample aggregate that records an event on every change."""

    def __init__(
        self,
        id: CounterId,
        label: str = "acme",
        total: int = 0,
        deleted_at: datetime | None = None,
    ) -> None:
        super().__init__()
        self._id = id
        self.label = label
        self.total = total
        self._deleted_at = deleted_at

    @property
    def id(self) -> CounterId:
        return self._id

    def increment(self) -> None:
        """Advance the counter and record the fact.

        Raises:
            AggregateDeletedError: If the counter was already deleted.
        """
        self._require_not_deleted(action="increment")
        self.total += 1
        self._record_event(CounterChanged(self.total))


class CounterMapper:
    """Translate the sample aggregate to and from its row."""

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
        """Return the row to store, patching the loaded one when given."""
        target = record if record is not None else CounterRecord(id=aggregate.id.value)
        target.label = aggregate.label
        target.total = aggregate.total
        target.deleted_at = aggregate.deleted_at

        return target


class CounterRepository(SqlAlchemyMappedRepository[Counter, CounterRecord, int]):
    """Sample write-side repository a context would declare."""

    record_type = CounterRecord
    mapper = CounterMapper()
