"""The identity source: the one place this layer mints new identifiers.

Adapters that create a record of their own -- a dispatcher naming itself, say --
draw the identifier from here, so nothing in this layer reaches for a UUID
library directly and a test can substitute a deterministic source.
"""

from __future__ import annotations

from uuid import UUID, uuid4


class UuidGenerator:
    """Generate a fresh UUID.

    ``new`` is a classmethod so callers need no instance; an instance still
    satisfies the application's ``IdGenerator`` port.
    """

    @classmethod
    def new(cls) -> UUID:
        """Return a new, unique identifier."""
        return uuid4()
