"""Message abstractions for commands and queries."""

from __future__ import annotations

from abc import ABC
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Message(ABC):  # noqa: B024
    """Base class for application messages."""


class Command[TResult](Message, ABC):
    """Base class for commands: write operations returning TResult."""


class Query[TResult](Message, ABC):
    """Base class for queries: read operations returning TResult."""
