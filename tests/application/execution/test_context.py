"""Tests for the ambient context and the transaction scope it opens."""

from __future__ import annotations

from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Self
from uuid import UUID

import pytest

from fastddd.application.execution.context import (
    Context,
    MessageMetadata,
    current_context,
    current_context_or_none,
    current_metadata,
    current_unit_of_work,
    current_unit_of_work_or_none,
)
from fastddd.application.integration.outbox import IntegrationEvent, Outbox
from fastddd.application.ports.unit_of_work import UnitOfWork
from fastddd.domain import Aggregate, DomainEvent, InvariantViolationError


class FakeOutbox(Outbox):
    """Outbox that records what was appended."""

    def __init__(self) -> None:
        self.appended: list[IntegrationEvent] = []

    async def append(self, event: IntegrationEvent) -> None:
        self.appended.append(event)

    async def claim(
        self,
        limit: int,
        worker: str,
        lease_seconds: float,
    ) -> list[IntegrationEvent]:
        return self.appended[:limit]

    async def mark_as_published(self, event_id: UUID, worker: str) -> None:
        pass

    async def mark_failed(self, event_id: UUID, error: str, worker: str) -> None:
        pass

    async def purge_published(self, before: datetime) -> int:
        return 0


class FakeUnitOfWork(UnitOfWork):
    """Unit of work recording the transaction lifecycle it went through."""

    def __init__(self) -> None:
        self._outbox = FakeOutbox()
        self.opened = 0
        self.outcomes: list[type[BaseException] | None] = []

    @property
    def outbox(self) -> Outbox:
        return self._outbox

    def track(self, aggregate: Aggregate[Any]) -> None:
        pass

    def pull_events(self) -> list[DomainEvent]:
        return []

    async def __aenter__(self) -> Self:
        """Open the transaction."""
        self.opened += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Record how the transaction ended."""
        self.outcomes.append(exc_type)

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FailingUnitOfWork(FakeUnitOfWork):
    """Unit of work that cannot be opened."""

    async def __aenter__(self) -> Self:
        """Refuse to open the transaction."""
        raise RuntimeError("cannot open the transaction")


def metadata() -> MessageMetadata:
    """Return metadata for a sample request."""
    return MessageMetadata(
        message_id="message-1",
        correlation_id=None,
        causation_id=None,
        principal_id=None,
        tenant_id=None,
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


def test_nothing_is_bound_by_default() -> None:
    assert current_context_or_none() is None
    assert current_unit_of_work_or_none() is None


def test_reading_the_scope_without_one_is_refused() -> None:
    with pytest.raises(LookupError, match="No active context"):
        current_context()

    with pytest.raises(LookupError, match="No active message metadata"):
        current_metadata()

    with pytest.raises(LookupError, match="No active unit of work"):
        current_unit_of_work()


async def test_entering_a_scope_binds_it_until_it_exits() -> None:
    ctx = Context(metadata=metadata())

    async with ctx as entered:
        assert entered is ctx
        assert current_context() is ctx
        assert current_metadata() is ctx.metadata
        assert current_context_or_none() is ctx

    assert current_context_or_none() is None


async def test_a_metadata_only_scope_binds_no_unit_of_work() -> None:
    async with Context(metadata=metadata()):
        assert current_unit_of_work_or_none() is None

        with pytest.raises(LookupError, match="No active unit of work"):
            current_unit_of_work()


async def test_a_transaction_only_scope_carries_no_metadata() -> None:
    uow = FakeUnitOfWork()

    async with Context(unit_of_work=uow):
        assert current_unit_of_work() is uow

        with pytest.raises(LookupError, match="No active message metadata"):
            current_metadata()


async def test_entering_opens_the_transaction_and_leaving_commits() -> None:
    uow = FakeUnitOfWork()

    async with Context(metadata=metadata(), unit_of_work=uow):
        assert uow.opened == 1
        assert uow.outcomes == []
        assert current_unit_of_work() is uow

    assert uow.outcomes == [None]


async def test_an_exception_rolls_the_transaction_back() -> None:
    uow = FakeUnitOfWork()

    with pytest.raises(RuntimeError, match="boom"):
        async with Context(metadata=metadata(), unit_of_work=uow):
            raise RuntimeError("boom")

    assert uow.outcomes == [RuntimeError]


async def test_a_failed_transaction_open_leaves_no_scope_bound() -> None:
    with pytest.raises(RuntimeError, match="cannot open"):
        async with Context(metadata=metadata(), unit_of_work=FailingUnitOfWork()):
            pass

    assert current_context_or_none() is None


async def test_a_scope_restores_the_one_it_replaced() -> None:
    outer = Context(metadata=metadata())
    inner = Context(metadata=metadata())

    async with outer:
        async with inner:
            assert current_context() is inner

        assert current_context() is outer


async def test_leaving_a_scope_that_was_never_entered_is_a_no_op() -> None:
    ctx = Context(metadata=metadata())

    await ctx.__aexit__(None, None, None)

    assert current_context_or_none() is None


async def test_with_metadata_derives_a_sibling_scope() -> None:
    uow = FakeUnitOfWork()
    ctx = Context(metadata=metadata(), unit_of_work=uow)

    derived = ctx.with_metadata(tenant_id="acme")

    assert derived is not ctx
    assert derived.metadata is not None
    assert derived.metadata.tenant_id == "acme"
    assert derived.unit_of_work is uow
    assert ctx.metadata is not None
    assert ctx.metadata.tenant_id is None


def test_with_metadata_without_metadata_is_refused() -> None:
    with pytest.raises(LookupError, match="carries no message metadata"):
        Context().with_metadata(tenant_id="acme")


def test_message_metadata_rejects_a_naive_timestamp() -> None:
    naive = datetime(2026, 1, 1)

    with pytest.raises(InvariantViolationError, match="must be timezone-aware"):
        MessageMetadata(
            message_id="message-1",
            correlation_id=None,
            causation_id=None,
            principal_id=None,
            tenant_id=None,
            occurred_at=naive,
        )


def test_message_metadata_accepts_an_aware_timestamp() -> None:
    assert metadata().occurred_at == datetime(2026, 1, 1, tzinfo=UTC)
