"""Render domain values as the JSON an integration event carries.

Two things are the same whichever context wrote the fact, which is why this is
shared rather than copied: the shape of a payload (one entry per field of the
domain event) and which Python values are JSON-safe. What is *not* shared is a
context's own value objects — the kernel has no way to know that a principal
reference is worth two strings — so a context passes a converter, and the
converter gets first refusal over the shared vocabulary.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any, cast

from ...domain import DomainEvent
from .outbox import JsonValue

type ValueConverter = Callable[[object], JsonValue | None]
"""Render a context's own value as JSON, or return ``None`` to decline it."""


def event_payload(
    event: DomainEvent,
    *converters: ValueConverter,
) -> dict[str, JsonValue]:
    """Return the payload of a domain event: one JSON-safe entry per field."""
    return {
        field.name: json_value(getattr(event, field.name), *converters)
        for field in dataclasses.fields(cast(Any, event))
    }


def json_value(value: object, *converters: ValueConverter) -> JsonValue:
    """Return a JSON-safe representation of a domain value.

    Every converter is asked first, in order, so a context decides what its own
    value objects are worth; whatever they decline falls through to the vocabulary
    every context shares.
    """
    for convert in converters:
        converted = convert(value)
        if converted is not None:
            return converted

    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return str(value.value)
    if isinstance(value, str):
        return value
    # ``JsonValue`` names lists and mappings as JSON-safe, so a field that holds
    # one is rendered recursively rather than stringified.
    if isinstance(value, (list, tuple)):
        return [json_value(item, *converters) for item in value]
    if isinstance(value, dict):
        return {str(key): json_value(item, *converters) for key, item in value.items()}

    return str(value)
