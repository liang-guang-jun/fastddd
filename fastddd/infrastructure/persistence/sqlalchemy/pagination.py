"""Cursor pagination and keyword search over SQLAlchemy statements.

Two reusable pieces live here. ``fetch_page`` turns a filtered statement into one
page plus the cursor that resumes after it, and ``matches`` turns a keyword into
the predicate a context applies over the columns it decided are worth searching.

Both are written once because every list in every context wants exactly this. A
list that built its own would be the one that got the boundary wrong — reading a
row twice at a page edge, or comparing a cursor against columns the cursor was not
made of.

How a list is ordered is what makes a cursor possible, so it is not free: the
ordering key must name exactly one row, which is why the second column is always
the identity of the aggregate rather than another sort key that can repeat.

The columns a caller passes are typed loosely on purpose: the attributes an
ORM class declares are column expressions to SQLAlchemy but not to its type
stubs, so naming them precisely here would mean either importing a private alias
or asking every repository to wrap them. What is typed is what comes back — a
predicate a statement can be filtered with.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import ColumnElement, Select, func, or_, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from ....domain.pagination import (
    InvalidCursorError,
    PageRequest,
    decode_cursor,
    encode_cursor,
)

ESCAPE = "\\"
"""The character the keyword pattern protects its wildcards with."""


def search_pattern(needle: str) -> str:
    """Return the case-insensitive contains-pattern a keyword is matched with.

    The characters a caller could type that mean something to ``LIKE`` are
    escaped, so a keyword searches for itself instead of matching everything.
    """
    escaped = needle.replace(ESCAPE, ESCAPE * 2)
    escaped = escaped.replace("%", f"{ESCAPE}%").replace("_", f"{ESCAPE}_")

    return f"%{escaped.lower()}%"


def matches(needle: str, *columns: Any) -> ColumnElement[bool]:
    """Return the predicate selecting rows where any column contains the keyword.

    Comparison goes through ``lower`` rather than ``ILIKE`` so one spelling works
    on every dialect this project runs: ``lower(name) LIKE '%acme%'`` means the
    same thing on SQLite and on PostgreSQL.

    At least one column is required: a keyword nobody searches for would match
    nothing, which is never what the caller meant.
    """
    if not columns:
        raise ValueError("a keyword has to be searched for in some column")

    pattern = search_pattern(needle)

    return or_(*(func.lower(column).like(pattern, escape=ESCAPE) for column in columns))


async def fetch_page(
    session: AsyncSession,
    statement: Select[Any],
    request: PageRequest,
    *,
    order_by: Sequence[Any],
) -> tuple[list[Any], str | None]:
    """Return one page of rows and the cursor that resumes after them.

    One row more than the page holds is read: its presence is what says another
    page exists, so no count is taken and the cost of a page does not depend on how
    far into the list it is.

    The ordering columns are the cursor. Every list here orders by a sort key that
    can repeat followed by the identity that breaks the tie, because a cursor has
    to resume at exactly one row and a key that can repeat cannot say which one.

    Raises:
        InvalidCursorError: If the cursor was not produced by this list.
    """
    columns = tuple(order_by)
    if request.cursor is not None:
        keys = decode_cursor(request.cursor, expected=len(columns))
        statement = statement.where(
            tuple_(*columns)
            > tuple_(
                *(
                    _restore(column, key)
                    for column, key in zip(columns, keys, strict=True)
                )
            )
        )

    rows = (
        (await session.execute(statement.order_by(*columns).limit(request.limit + 1)))
        .scalars()
        .all()
    )
    items = list(rows[: request.limit])
    if len(rows) <= request.limit:
        return items, None

    last = items[-1]

    return items, encode_cursor(*[getattr(last, column.key) for column in columns])


def _restore(column: Any, key: str) -> object:
    """Return a cursor value as the type of the column it is compared with.

    A cursor carries text; the comparison needs whatever the column holds. The
    column itself says which that is, so a list only has to name the columns it
    orders by.

    Raises:
        InvalidCursorError: If the text cannot be read as that type.
    """
    python_type = _python_type(column)
    try:
        if python_type is datetime:
            return datetime.fromisoformat(key)
        if python_type is UUID:
            return UUID(key)
        if python_type is int:
            return int(key)
        if python_type is float:
            return float(key)
        if python_type is bool:
            # A cursor carries text, and a bool renders as ``True``; reading it
            # back case-insensitively is what keeps the cursor moving off the
            # row it names instead of handing that row out again.
            return key.lower() == "true"
    except ValueError as error:
        raise InvalidCursorError(
            f"{key!r} is not a value this list is ordered by"
        ) from error

    return key


def _python_type(column: Any) -> type[Any]:
    """Return the Python type a column holds, or ``str`` when it will not say.

    A type the dialect cannot name is treated as text, which is what a cursor
    carries anyway.
    """
    try:
        declared: type[Any] = column.type.python_type
    except NotImplementedError:
        return str

    return declared
