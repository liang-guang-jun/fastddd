"""Identity port: where the application asks for a fresh identifier."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class IdGenerator(Protocol):
    """A source of fresh, unique identifiers.

    Nothing here says how an identifier is shaped beyond being one ``UUID``; an
    implementation is free to derive it however it likes.
    """

    def new(self) -> UUID:
        """Return a new, unique identifier."""
        ...
