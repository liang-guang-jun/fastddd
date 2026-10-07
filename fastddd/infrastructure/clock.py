"""The system clock: the one place this layer reads the wall clock.

Every adapter that needs "now" takes it from here, so a deployment that must run
on a fixed or shifted time has a single place to change, and a test can hand the
adapter a clock of its own instead.
"""

from __future__ import annotations

from datetime import UTC, datetime


class SystemClock:
    """Report the current moment in UTC.

    ``now`` is a classmethod so the rest of this layer can take the moment without
    holding an object -- ``SystemClock.now`` is already the callable an injected
    clock is. An instance satisfies the application's ``Clock`` port.
    """

    @classmethod
    def now(cls) -> datetime:
        """Return the current moment, in UTC."""
        return datetime.now(UTC)
