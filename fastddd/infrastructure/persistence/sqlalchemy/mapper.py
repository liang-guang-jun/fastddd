"""Mapping contract between aggregates and their persistence records.

Mapping is infrastructure work: the domain never learns about records, and each
adapter decides how a record is rebuilt, written, and whether it is deleted.
"""

from __future__ import annotations

from typing import Any, Protocol

from sqlalchemy import ColumnElement

from ....domain import Aggregate


class AggregateRecordMapper[TAggregate: Aggregate[Any], TRecord](Protocol):
    """Translate one aggregate type to and from its persistence record.

    Implementations must not perform I/O: they receive loaded records and return
    aggregates or records, so the generic repository stays in charge of sessions.

    An aggregate that owns child rows needs no extra hook: model the children as a
    relationship on the record and map them inside ``to_domain`` and ``to_record``,
    letting the ORM load and cascade them.

    Liveness appears twice on purpose: ``is_deleted`` inspects a record that was
    already loaded, while ``not_deleted`` is the SQL predicate a query needs to skip
    deleted rows. Implementations must keep the two consistent.
    """

    def is_deleted(self, record: TRecord) -> bool:
        """Return whether the record represents a soft-deleted aggregate."""
        ...

    def not_deleted(self) -> ColumnElement[bool]:
        """Return the predicate selecting records that are not soft-deleted."""
        ...

    def to_domain(self, record: TRecord) -> TAggregate:
        """Rebuild the aggregate from its record, without emitting events."""
        ...

    def to_record(self, aggregate: TAggregate, record: TRecord | None) -> TRecord:
        """Return the record to store, patching the existing one when given."""
        ...
