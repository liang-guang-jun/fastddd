"""Background driver for the outbox dispatchers.

An outbox is durable but inert: something has to ask a dispatcher to publish. In
a single-process deployment that something is this worker, which drains every
attached context on an interval so events written by a command — or left behind
by a restart — reach their consumers without a caller having to wait for them.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence
from typing import Protocol

from ..logging.logger import get_logger

DEFAULT_INTERVAL_SECONDS = 1.0
DEFAULT_CLEANUP_INTERVAL_SECONDS = 300.0
DEFAULT_RETENTION_SECONDS = 86_400.0
DEFAULT_JITTER = 0.1


class Dispatcher(Protocol):
    """Publish one batch of pending events and report how many were delivered."""

    async def dispatch_once(self) -> int:
        """Publish a ready batch."""
        ...


class Sweeper(Protocol):
    """Delete rows that have outlived their retention window."""

    async def sweep(self, retention_seconds: float) -> int:
        """Delete finished rows older than the retention window."""
        ...


class OutboxWorker:
    """Drain the outbox of every attached context on an interval."""

    def __init__(
        self,
        dispatchers: Sequence[Dispatcher],
        *,
        interval_seconds: float = DEFAULT_INTERVAL_SECONDS,
        sweeper: Sweeper | None = None,
        cleanup_interval_seconds: float = DEFAULT_CLEANUP_INTERVAL_SECONDS,
        retention_seconds: float = DEFAULT_RETENTION_SECONDS,
        jitter: float = DEFAULT_JITTER,
        random_source: random.Random | None = None,
    ) -> None:
        """Store what to poll, how often to drain, and how to clean up.

        Cleanup is opt-in: with no ``sweeper`` the worker only dispatches.
        ``jitter`` spreads the cleanup cadence across workers so they do not all
        sweep at once; ``random_source`` makes that timing deterministic in
        tests.
        """
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        if cleanup_interval_seconds <= 0:
            raise ValueError("cleanup_interval_seconds must be positive")
        if retention_seconds <= 0:
            raise ValueError("retention_seconds must be positive")
        if not 0 <= jitter < 1:
            raise ValueError("jitter must be between 0 and 1")

        self._dispatchers = list(dispatchers)
        self._interval = interval_seconds
        self._sweeper = sweeper
        self._cleanup_interval = cleanup_interval_seconds
        self._retention = retention_seconds
        self._jitter = jitter
        self._random = random_source or random.Random()
        self._cleanup_due_in = self.next_cleanup_delay()
        self._task: asyncio.Task[None] | None = None
        self._logger = get_logger("server.outbox")

    @property
    def dispatchers(self) -> tuple[Dispatcher, ...]:
        """Return the dispatchers this worker drains."""
        return tuple(self._dispatchers)

    @property
    def is_running(self) -> bool:
        """Return whether a polling task is currently alive."""
        return self._task is not None and not self._task.done()

    async def dispatch_pending(self) -> int:
        """Publish one batch per dispatcher and return how many were delivered."""
        delivered = 0
        for dispatcher in self._dispatchers:
            delivered += await dispatcher.dispatch_once()

        return delivered

    async def sweep_once(self) -> int:
        """Delete finished rows past retention, or nothing without a sweeper."""
        if self._sweeper is None:
            return 0

        return await self._sweeper.sweep(self._retention)

    async def run(self) -> None:
        """Drain on an interval until the task is cancelled.

        The first drain waits one interval: an application should finish starting
        before it starts working, and a shutdown that arrives first then costs
        nothing. A failing drain is logged and retried, because the outbox still
        holds the events and the next attempt may well succeed. Cleanup rides a
        slower, jittered cadence so parallel workers do not contend on the same
        delete.
        """
        elapsed = 0.0
        while True:
            await asyncio.sleep(self._interval)
            try:
                await self.dispatch_pending()
            except Exception:
                self._logger.exception("outbox.dispatch.failed")

            if self._sweeper is None:
                continue

            elapsed += self._interval
            if elapsed < self._cleanup_due_in:
                continue

            elapsed = 0.0
            self._cleanup_due_in = self.next_cleanup_delay()
            try:
                await self.sweep_once()
            except Exception:
                self._logger.exception("outbox.cleanup.failed")

    def next_cleanup_delay(self) -> float:
        """Return a jittered wait before the next sweep."""
        if self._jitter == 0:
            return self._cleanup_interval

        return self._cleanup_interval * self._random.uniform(
            1 - self._jitter, 1 + self._jitter
        )

    def start(self) -> None:
        """Start polling in the background.

        Raises:
            RuntimeError: If the worker is already started.
        """
        if self._task is not None:
            raise RuntimeError("the outbox worker is already started")

        self._task = asyncio.create_task(self.run())

    async def stop(self) -> None:
        """Stop polling and wait for the task to finish."""
        task = self._task
        self._task = None
        if task is None:
            return

        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
