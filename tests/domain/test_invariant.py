"""Tests for the shared invariant helpers."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from fastddd.domain.error import InvariantViolationError
from fastddd.domain.invariant import require_non_blank, require_timezone_aware


def test_require_non_blank_returns_stripped_text() -> None:
    assert require_non_blank("  ada  ", field="name") == "ada"


def test_require_non_blank_keeps_text_that_needs_no_stripping() -> None:
    assert require_non_blank("ada", field="name") == "ada"


@pytest.mark.parametrize("value", [None, "", "   ", "\t\n"])
def test_require_non_blank_rejects_missing_and_blank_text(value: str | None) -> None:
    with pytest.raises(InvariantViolationError, match="name must not be blank"):
        require_non_blank(value, field="name")


def test_require_non_blank_names_the_field_it_rejected() -> None:
    with pytest.raises(InvariantViolationError, match="title must not be blank"):
        require_non_blank("  ", field="title")


def test_require_timezone_aware_returns_the_timestamp_unchanged() -> None:
    moment = datetime(2026, 1, 1, tzinfo=UTC)

    assert require_timezone_aware(moment, field="at") is moment


def test_require_timezone_aware_accepts_a_fixed_offset() -> None:
    moment = datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=2)))

    assert require_timezone_aware(moment, field="at") is moment


def test_require_timezone_aware_rejects_naive_timestamps() -> None:
    with pytest.raises(InvariantViolationError, match="at must be timezone-aware"):
        require_timezone_aware(datetime(2026, 1, 1), field="at")
