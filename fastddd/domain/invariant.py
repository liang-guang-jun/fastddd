"""Invariant helpers shared by every domain model."""

from __future__ import annotations

from datetime import datetime

from .error import InvariantViolationError


def require_non_blank(value: str | None, *, field: str) -> str:
    """Return the stripped text, rejecting ``None`` and blank values.

    A missing value and a blank value are the same violation from the domain's
    point of view: neither names anything. Both raise
    :class:`InvariantViolationError` so callers can catch one exception type.

    Args:
        value: The text to validate. ``None`` is treated as blank.
        field: The field name, used only to build the error message.

    Returns:
        The text with surrounding whitespace removed.

    Raises:
        InvariantViolationError: If ``value`` is ``None`` or blank.
    """
    if value is None:
        raise InvariantViolationError(f"{field} must not be blank")

    stripped = value.strip()
    if not stripped:
        raise InvariantViolationError(f"{field} must not be blank")

    return stripped


def require_timezone_aware(value: datetime, *, field: str) -> datetime:
    """Return the timestamp unchanged, rejecting naive datetimes.

    Comparing a naive datetime with an aware one raises ``TypeError``, so every
    timestamp that takes part in a comparison is validated at construction.

    The timestamp is returned as given; normalizing to a specific zone (for
    example UTC) is the caller's decision, not this helper's.

    Args:
        value: The timestamp to validate.
        field: The field name, used only to build the error message.

    Returns:
        The same timestamp, unchanged.

    Raises:
        InvariantViolationError: If ``value`` is naive.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise InvariantViolationError(f"{field} must be timezone-aware")

    return value
