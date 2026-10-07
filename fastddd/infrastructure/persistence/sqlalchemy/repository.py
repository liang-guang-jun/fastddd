"""Base classes for write-side SQLAlchemy aggregate repositories."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable, Sequence
from typing import Any, ClassVar

from sqlalchemy import ColumnElement, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from ....application.execution.context import current_unit_of_work
from ....domain import Aggregate, AggregateRepository, EntityId, Page, PageRequest
from .mapper import AggregateRecordMapper
from .pagination import fetch_page
from .unit_of_work import SqlAlchemyUnitOfWork


class SqlAlchemyAggregateRepository[TAggregate: Aggregate[Any], TId: Hashable](
    AggregateRepository[TAggregate, TId], ABC
):
    """Attach write-model aggregates to the current SQLAlchemy unit of work.

    Concrete repositories supply the mapping between a domain aggregate and
    their SQLAlchemy model, keeping SQLAlchemy annotations out of the domain.
    """

    @property
    def _uow(self) -> SqlAlchemyUnitOfWork:
        """Return the SQLAlchemy UoW bound to the current command task.

        Raises:
            LookupError: If no command task bound a unit of work.
            TypeError: If the bound unit of work is not SQLAlchemy-backed.
        """
        uow = current_unit_of_work()
        if not isinstance(uow, SqlAlchemyUnitOfWork):
            raise TypeError("Active unit of work is not SQLAlchemy-backed")
        return uow

    async def get(self, id: EntityId[TId]) -> TAggregate | None:
        """Load and track an aggregate when it exists."""
        uow = self._uow
        aggregate = await self._load(uow.session, id)
        if aggregate is not None:
            uow.track(aggregate)
        return aggregate

    async def save(self, aggregate: TAggregate) -> None:
        """Persist the aggregate, including its soft-delete flag, and track it."""
        uow = self._uow
        await self._insert(uow.session, aggregate)
        uow.track(aggregate)

    @abstractmethod
    async def _load(
        self, session: AsyncSession, id: EntityId[TId]
    ) -> TAggregate | None:
        """Reconstitute one aggregate from persistence without emitting events."""
        raise NotImplementedError

    @abstractmethod
    async def _insert(self, session: AsyncSession, aggregate: TAggregate) -> None:
        """Write a new aggregate using persistence models owned by this adapter."""
        raise NotImplementedError


class SqlAlchemyMappedRepository[
    TAggregate: Aggregate[Any],
    TRecord,
    TId: Hashable,
](
    SqlAlchemyAggregateRepository[TAggregate, TId],
    ABC,
):
    """Repository whose row translation is delegated to an ``AggregateRecordMapper``.

    A concrete adapter only declares the record type and the mapper; loading,
    soft-delete filtering, and insert-or-update come from here. Aggregates that own
    child rows, such as one holding a collection entity, override ``_load`` and
    ``_insert`` and reuse their mapper for the aggregate root.
    """

    record_type: ClassVar[type[TRecord]]
    mapper: ClassVar[AggregateRecordMapper[TAggregate, TRecord]]

    @classmethod
    def __init_subclass__(cls, **kwargs: Any) -> None:
        """Refuse an adapter that does not say what it maps.

        An adapter that translates its own rows subclasses
        ``SqlAlchemyAggregateRepository`` instead.

        Raises:
            TypeError: If the subclass leaves ``record_type`` or ``mapper``
                undeclared, so the class is named at import time rather than
                the first query failing with an ``AttributeError``.
        """
        super().__init_subclass__(**kwargs)
        missing = [name for name in ("record_type", "mapper") if not hasattr(cls, name)]
        if missing:
            raise TypeError(f"{cls.__name__} must declare {', '.join(missing)}")

    async def _load(
        self,
        session: AsyncSession,
        id: EntityId[TId],
    ) -> TAggregate | None:
        """Reconstitute a live aggregate through the mapper, if it exists."""
        record = await session.get(self.record_type, id.value)
        if record is None or self.mapper.is_deleted(record):
            return None

        return self.mapper.to_domain(record)

    async def _insert(self, session: AsyncSession, aggregate: TAggregate) -> None:
        """Insert or update the record the mapper returns for the aggregate."""
        record = await session.get(self.record_type, aggregate.id.value)
        session.add(self.mapper.to_record(aggregate, record))

    async def purge(self, id: EntityId[TId]) -> None:
        """Physically remove the aggregate's record, if it is there.

        Physical removal is compliance work, not deletion: an ordinary delete is
        ``aggregate.delete(at=...)`` followed by ``save``. An aggregate that owns
        child rows overrides this to remove them too.
        """
        session = self._uow.session
        record = await session.get(self.record_type, id.value)
        if record is not None:
            await session.delete(record)

    async def find_one(
        self,
        *criteria: ColumnElement[bool],
    ) -> TAggregate | None:
        """Return and track the first live aggregate matching the criteria.

        Deleted rows are skipped through the mapper's predicate, so a lookup by a
        natural key never resolves to a soft-deleted aggregate.
        """
        uow = self._uow
        statement = select(self.record_type).where(*criteria, self.mapper.not_deleted())
        record = (await uow.session.execute(statement)).scalars().first()
        if record is None:
            return None

        aggregate = self.mapper.to_domain(record)
        uow.track(aggregate)

        return aggregate

    async def page(
        self,
        statement: Select[Any],
        request: PageRequest,
        *,
        order_by: Sequence[Any],
    ) -> Page[TAggregate]:
        """Return one page of aggregates, and the cursor that resumes after them.

        The caller builds the filter — a tenant scope, a keyword, a membership —
        and this turns it into a page: which rows the page holds, and how to ask
        for the ones after them. The ordering columns are the cursor, so they must
        name exactly one row each time.

        Raises:
            InvalidCursorError: If the cursor was not produced by this list.
        """
        records, next_cursor = await fetch_page(
            self._uow.session,
            statement,
            request,
            order_by=order_by,
        )

        return Page(
            items=[self.mapper.to_domain(record) for record in records],
            next_cursor=next_cursor,
        )
