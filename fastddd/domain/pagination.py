"""What a list query asks for, and what it gets back.

Lists are paged by cursor rather than by offset. An offset answers "skip the first
n rows", and that answer changes while rows are being written: a page read after
an insert repeats a row, a page read after a delete skips one, and reading deep
into a list costs more than reading the start of it. A cursor names the last row a
caller saw, so the next page starts after *that row* however much the table has
moved underneath, and every page costs the same.

The cursor is opaque on purpose. It carries the ordering key the list is written
with — a decision that belongs to the query, not to its caller — and a caller that
assembled one by hand could only get it wrong. A caller that wants another order
wants another list.

A keyword is a case-insensitive "contains" match over whatever columns a context
decides are worth searching. Which columns those are is the context's decision;
the kernel only carries the string.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import datetime

from .error import InvariantViolationError

DEFAULT_PAGE_SIZE = 50
"""How many rows a list returns when the caller does not say."""

MAX_PAGE_SIZE = 200
"""The largest page a caller may ask for, so one request cannot walk a table."""


class InvalidCursorError(InvariantViolationError):
    """Raised when a cursor cannot be read as the position it claims to be.

    A cursor that does not decode, or that carries a different number of ordering
    values than the list it was handed to, is a client error rather than a server
    one: this list never produced it.
    """


def _default_page_size() -> int:
    """Return the current default page size, read when a request is built.

    Reading the module attribute here rather than at class-definition time is what
    lets a caller rebind ``DEFAULT_PAGE_SIZE`` and have the next request pick it up.
    """
    return DEFAULT_PAGE_SIZE


@dataclass(frozen=True, slots=True)
class PageRequest:
    """One page of a list query: how many, resuming where, looking for what."""

    cursor: str | None = None
    size: int = field(default_factory=_default_page_size)
    search: str | None = None

    def __post_init__(self) -> None:
        """Reject a page nobody could serve.

        Raises:
            ValueError: If the page size is outside what a list serves, which is
                caught where the message is built rather than where it is read.
        """
        if self.size < 1:
            raise ValueError("size must be >= 1")

        if self.size > MAX_PAGE_SIZE:
            raise ValueError(f"size must be <= {MAX_PAGE_SIZE}")

    @property
    def limit(self) -> int:
        """Return the number of rows to read for this page."""
        return self.size

    @property
    def needle(self) -> str | None:
        """Return the keyword to look for, or ``None`` when none was asked for.

        Whitespace is not a keyword: a caller that sends it is asking for the whole
        list, and treating it as a search would answer with nothing.
        """
        if self.search is None:
            return None

        text = self.search.strip()

        return text or None


@dataclass(frozen=True, slots=True)
class Page[TItem]:
    """One page of results, and the cursor that resumes after it."""

    items: Sequence[TItem]
    next_cursor: str | None = None

    @property
    def has_next(self) -> bool:
        """Return whether another page is available."""
        return self.next_cursor is not None


def encode_cursor(*values: object) -> str:
    """Return the opaque marker naming one row's position in a list.

    The values are the ordering key of the last row of a page, rendered as the
    primitives JSON knows and wrapped in base64 so a caller reads them as one
    token rather than as a query it could take apart.
    """
    payload = json.dumps([_render(value) for value in values], separators=(",", ":"))

    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str, *, expected: int) -> tuple[str, ...]:
    """Return the ordering values a cursor carries.

    The number of values is checked as well as their shape, so a cursor borrowed
    from another list is refused rather than compared against the wrong columns.

    Raises:
        InvalidCursorError: If the cursor is not one this list produced.
    """
    try:
        raw = base64.urlsafe_b64decode(cursor.encode("ascii"))
        values = json.loads(raw.decode("utf-8"))
    except (
        UnicodeDecodeError,
        UnicodeEncodeError,
        binascii.Error,
        json.JSONDecodeError,
        ValueError,
    ) as error:
        raise InvalidCursorError(
            f"{cursor!r} is not a cursor this list produced"
        ) from error

    if not isinstance(values, list) or len(values) != expected:
        found = len(values) if isinstance(values, list) else "some other shape of"
        raise InvalidCursorError(
            f"a cursor for this list carries {expected} values, not {found}"
        )

    return tuple(str(value) for value in values)


def _render(value: object) -> object:
    """Return a value as a JSON primitive that can be read back as itself.

    Timestamps and identities are rendered as text because the column they are
    compared against stores text in one dialect and a native type in another; what
    matters is that the rendering is the same on the way in and on the way out.
    """
    if isinstance(value, datetime):
        return value.isoformat()

    if value is None or isinstance(value, (bool, int, float, str)):
        return value

    return str(value)
