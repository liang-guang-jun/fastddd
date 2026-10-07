"""Tests for the cursor and page vocabulary every list is written in."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from fastddd.domain.error import InvariantViolationError
from fastddd.domain.pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    InvalidCursorError,
    Page,
    PageRequest,
    decode_cursor,
    encode_cursor,
)


def test_a_page_defaults_to_what_a_list_serves_without_being_asked() -> None:
    request = PageRequest()

    assert request.size == DEFAULT_PAGE_SIZE
    assert request.limit == DEFAULT_PAGE_SIZE
    assert request.cursor is None
    assert request.search is None
    assert request.needle is None


def test_an_explicit_size_is_served_up_to_the_limit() -> None:
    request = PageRequest(size=MAX_PAGE_SIZE)

    assert request.size == MAX_PAGE_SIZE
    assert request.limit == MAX_PAGE_SIZE


@pytest.mark.parametrize("size", [0, -1, MAX_PAGE_SIZE + 1])
def test_a_page_nobody_could_serve_is_refused(size: int) -> None:
    with pytest.raises(ValueError, match="size"):
        PageRequest(size=size)


def test_whitespace_is_not_a_keyword() -> None:
    assert PageRequest(search="   ").needle is None
    assert PageRequest(search="  acme ").needle == "acme"


def test_a_page_knows_whether_another_one_follows() -> None:
    assert not Page(items=[1, 2]).has_next
    assert Page(items=[1, 2], next_cursor="cursor").has_next


def test_a_page_defaults_to_having_no_next_cursor() -> None:
    assert Page(items=[]).next_cursor is None


def test_a_cursor_carries_what_the_next_page_resumes_after() -> None:
    moment = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    identifier = uuid4()

    values = decode_cursor(encode_cursor(moment, identifier), expected=2)

    assert values == (moment.isoformat(), str(identifier))


@pytest.mark.parametrize("value", ["acme", 7, True, 1.5, None])
def test_every_sort_key_a_list_uses_can_be_carried(value: object) -> None:
    cursor = encode_cursor(value)

    assert decode_cursor(cursor, expected=1) == (str(value),)


def test_a_cursor_is_not_readable_as_the_query_behind_it() -> None:
    cursor = encode_cursor("acme", uuid4())

    assert "acme" not in cursor


def test_a_cursor_is_url_safe() -> None:
    cursor = encode_cursor("a b/c+d", "搜索")

    assert "+" not in cursor
    assert "/" not in cursor


def test_a_cursor_from_another_list_is_refused() -> None:
    cursor = encode_cursor("acme", 3)

    with pytest.raises(InvalidCursorError, match="carries 3 values, not 2"):
        decode_cursor(cursor, expected=3)


@pytest.mark.parametrize(
    "cursor",
    ["", "not-base64!!", "YWNtZQ", "WzEs", "e30", "bnVsbA"],
)
def test_something_that_is_not_a_cursor_is_refused(cursor: str) -> None:
    with pytest.raises(InvalidCursorError):
        decode_cursor(cursor, expected=1)


def test_a_cursor_that_is_not_a_json_array_is_refused() -> None:
    payload = base64.urlsafe_b64encode(b'{"a": 1}').decode("ascii")

    with pytest.raises(InvalidCursorError):
        decode_cursor(payload, expected=1)


def test_a_unicode_value_survives_the_round_trip() -> None:
    cursor = encode_cursor("搜索")

    assert decode_cursor(cursor, expected=1) == ("搜索",)


def test_an_identity_is_carried_as_text_and_not_as_something_else() -> None:
    identifier = UUID(int=7)

    assert decode_cursor(encode_cursor(identifier), expected=1) == (str(identifier),)


def test_a_cursor_with_no_values_is_valid_for_a_list_with_no_key() -> None:
    assert decode_cursor(encode_cursor(), expected=0) == ()


def test_an_invalid_cursor_is_an_invariant_violation() -> None:
    assert issubclass(InvalidCursorError, InvariantViolationError)
