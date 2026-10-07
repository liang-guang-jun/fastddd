"""Clock port: where the application asks for the current moment."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class Clock(Protocol):
    """A source of the current moment.

    The moment must be timezone-aware so it can be compared with any other
    timestamp the application handles. Which zone an implementation reports in is
    the implementation's business, so nothing here names one.
    """

    def now(self) -> datetime:
        """Return the current moment, timezone-aware."""
        ...
