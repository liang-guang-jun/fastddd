"""Tests for cursor pagination and keyword search over SQLAlchemy statements."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from fastddd.domain import InvalidCursorError, PageRequest, encode_cursor
from fastddd.infrastructure.persistence.sqlalchemy.pagination import (
    _restore,
    fetch_page,
    matches,
    search_pattern,
)
from tests.infrastructure.persistence._helpers import TicketRecord

OPENED_AT = datetime(2026, 1, 1, tzinfo=UTC)


class _UnnamableType:
    """A column type that refuses to name the Python type it holds."""

    @property
    def python_type(self) -> type[object]:
        raise NotImplementedError


class _OpaqueColumn:
    """A column whose dialect cannot name the type it holds."""

    type = _UnnamableType()


def _ticket(ticket_id: int) -> TicketRecord:
    """Return an unsaved ticket, whose columns the test can then adjust."""
    return TicketRecord(
        id=ticket_id,
        label=f"ticket-{ticket_id}",
        note=None,
        score=float(ticket_id),
        opened_at=OPENED_AT + timedelta(days=ticket_id),
        urgent=False,
        token=UUID(int=ticket_id),
    )


async def _store(
    session_factory: async_sessionmaker[AsyncSession], tickets: list[TicketRecord]
) -> None:
    """Write the tickets and commit them."""
    async with session_factory() as session:
        session.add_all(tickets)
        await session.commit()


async def _walk(
    session_factory: async_sessionmaker[AsyncSession],
    column: Any,
    *,
    size: int,
    total: int,
) -> list[int]:
    """Return every id a cursor walks over, one page at a time.

    The loop is bounded so a cursor that fails to advance fails the assertion
    instead of spinning forever.
    """
    seen: list[int] = []
    cursor: str | None = None

    for _ in range(total + 1):
        async with session_factory() as session:
            rows, cursor = await fetch_page(
                session,
                select(TicketRecord),
                PageRequest(cursor=cursor, size=size),
                order_by=(column, TicketRecord.id),
            )
        seen.extend(row.id for row in rows)
        if cursor is None:
            break

    return seen


def test_a_keyword_is_matched_ignoring_case() -> None:
    assert search_pattern("Acme") == "%acme%"


def test_the_characters_like_reads_specially_are_escaped() -> None:
    assert search_pattern("50%_off\\") == r"%50\%\_off\\%"


def test_searching_without_a_column_is_refused() -> None:
    with pytest.raises(ValueError, match="has to be searched for in some column"):
        matches("acme")


async def test_a_keyword_matches_a_row_whatever_its_case(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(
        session_factory,
        [_ticket(1), _ticket(2), _ticket(3)],
    )

    async with session_factory() as session:
        found = (
            await session.execute(
                select(TicketRecord).where(matches("TICKET-2", TicketRecord.label))
            )
        ).scalars()

    assert [row.id for row in found] == [2]


async def test_a_keyword_containing_a_wildcard_searches_for_it_literally(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    literal, other = _ticket(1), _ticket(2)
    literal.label = "100% cotton"
    other.label = "100x cotton"
    await _store(session_factory, [literal, other])

    async with session_factory() as session:
        found = (
            await session.execute(
                select(TicketRecord).where(matches("100%", TicketRecord.label))
            )
        ).scalars()

    assert [row.id for row in found] == [1]


async def test_a_keyword_searches_every_column_it_is_given(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    in_label, in_note, nowhere = _ticket(1), _ticket(2), _ticket(3)
    in_label.label = "acme"
    in_note.note = "acme reported"
    await _store(session_factory, [in_label, in_note, nowhere])

    async with session_factory() as session:
        found = (
            await session.execute(
                select(TicketRecord).where(
                    matches("acme", TicketRecord.label, TicketRecord.note)
                )
            )
        ).scalars()

    assert [row.id for row in found] == [1, 2]


async def test_an_empty_list_hands_back_no_cursor(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        rows, cursor = await fetch_page(
            session,
            select(TicketRecord),
            PageRequest(),
            order_by=(TicketRecord.label, TicketRecord.id),
        )

    assert rows == []
    assert cursor is None


async def test_a_full_page_hands_back_the_cursor_that_resumes_after_it(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(session_factory, [_ticket(1), _ticket(2), _ticket(3)])

    async with session_factory() as session:
        rows, cursor = await fetch_page(
            session,
            select(TicketRecord),
            PageRequest(size=2),
            order_by=(TicketRecord.label, TicketRecord.id),
        )

    assert [row.id for row in rows] == [1, 2]
    assert cursor is not None


async def test_a_last_page_that_is_not_full_hands_back_no_cursor(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(session_factory, [_ticket(1), _ticket(2)])

    async with session_factory() as session:
        rows, cursor = await fetch_page(
            session,
            select(TicketRecord),
            PageRequest(size=5),
            order_by=(TicketRecord.label, TicketRecord.id),
        )

    assert [row.id for row in rows] == [1, 2]
    assert cursor is None


async def test_walking_in_ones_visits_every_row_exactly_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(session_factory, [_ticket(1), _ticket(2), _ticket(3)])

    assert await _walk(session_factory, TicketRecord.label, size=1, total=3) == [
        1,
        2,
        3,
    ]


async def test_walking_in_twos_visits_every_row_exactly_once(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await _store(session_factory, [_ticket(1), _ticket(2), _ticket(3)])

    assert await _walk(session_factory, TicketRecord.label, size=2, total=3) == [
        1,
        2,
        3,
    ]


@pytest.mark.parametrize(
    ("column", "values"),
    [
        pytest.param(TicketRecord.label, ["alpha", "beta", "gamma"], id="text"),
        pytest.param(TicketRecord.score, [1.5, 2.5, 3.5], id="real-number"),
        pytest.param(
            TicketRecord.opened_at,
            [OPENED_AT + timedelta(days=day) for day in (1, 2, 3)],
            id="timestamp",
        ),
        # Two rows share the value, so the identity column has to break the tie.
        pytest.param(TicketRecord.urgent, [False, True, True], id="flag"),
        pytest.param(
            TicketRecord.token,
            [UUID(int=1), UUID(int=2), UUID(int=3)],
            id="identity",
        ),
    ],
)
async def test_a_cursor_resumes_after_a_row_of_any_column_type(
    session_factory: async_sessionmaker[AsyncSession],
    column: Any,
    values: list[Any],
) -> None:
    tickets = []
    for index, value in enumerate(values, start=1):
        ticket = _ticket(index)
        setattr(ticket, column.key, value)
        tickets.append(ticket)
    await _store(session_factory, tickets)

    assert await _walk(session_factory, column, size=1, total=3) == [1, 2, 3]


async def test_a_cursor_carrying_the_wrong_number_of_values_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(InvalidCursorError, match="carries 2 values"):
            await fetch_page(
                session,
                select(TicketRecord),
                PageRequest(cursor=encode_cursor(1, 2, 3)),
                order_by=(TicketRecord.label, TicketRecord.id),
            )


async def test_a_cursor_carrying_a_value_of_the_wrong_type_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(InvalidCursorError, match="is not a value this list"):
            await fetch_page(
                session,
                select(TicketRecord),
                PageRequest(cursor=encode_cursor("half", 1)),
                order_by=(TicketRecord.score, TicketRecord.id),
            )


async def test_something_that_is_not_a_cursor_is_refused(
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with session_factory() as session:
        with pytest.raises(InvalidCursorError):
            await fetch_page(
                session,
                select(TicketRecord),
                PageRequest(cursor="???"),
                order_by=(TicketRecord.label, TicketRecord.id),
            )


def test_a_column_of_an_unnamable_type_is_compared_as_text() -> None:
    # A type the dialect cannot name is treated as the text a cursor carries.
    assert _restore(_OpaqueColumn(), "whatever") == "whatever"
