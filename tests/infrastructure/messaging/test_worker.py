"""Tests for the background outbox worker."""

from __future__ import annotations

import asyncio
from random import Random

import pytest

from fastddd.infrastructure.messaging import OutboxWorker
from tests.infrastructure.logging._helpers import captured_logs


class _CountingDispatcher:
    """Report how many events each drain delivered, and optionally fail."""

    def __init__(self, delivered: int = 1, *, fails: bool = False) -> None:
        self.delivered = delivered
        self.fails = fails
        self.drains = 0

    async def dispatch_once(self) -> int:
        self.drains += 1
        if self.fails:
            raise RuntimeError("the outbox is unreachable")

        return self.delivered


def test_an_interval_that_is_not_positive_is_refused() -> None:
    with pytest.raises(ValueError, match="interval_seconds must be positive"):
        OutboxWorker([], interval_seconds=0)


def test_a_worker_reports_the_dispatchers_it_drains() -> None:
    dispatcher = _CountingDispatcher()

    assert OutboxWorker([dispatcher]).dispatchers == (dispatcher,)


def test_a_worker_is_not_running_before_it_is_started() -> None:
    assert OutboxWorker([]).is_running is False


async def test_a_drain_asks_every_dispatcher_once() -> None:
    first, second = _CountingDispatcher(2), _CountingDispatcher(3)
    worker = OutboxWorker([first, second])

    assert await worker.dispatch_pending() == 5
    assert (first.drains, second.drains) == (1, 1)


async def test_a_started_worker_drains_in_the_background() -> None:
    dispatcher = _CountingDispatcher()
    worker = OutboxWorker([dispatcher], interval_seconds=0.01)

    worker.start()
    try:
        running = worker.is_running
        await asyncio.sleep(0.15)
    finally:
        await worker.stop()

    assert running is True
    assert worker.is_running is False
    assert dispatcher.drains >= 2


async def test_a_worker_cannot_be_started_twice() -> None:
    worker = OutboxWorker([], interval_seconds=0.01)
    worker.start()
    try:
        with pytest.raises(RuntimeError, match="already started"):
            worker.start()
    finally:
        await worker.stop()


async def test_stopping_a_worker_that_never_started_is_a_no_op() -> None:
    await OutboxWorker([]).stop()


async def test_a_failing_drain_is_logged_and_retried() -> None:
    dispatcher = _CountingDispatcher(fails=True)

    # The worker is built inside the capture so its logger resolves against it.
    with captured_logs() as entries:
        worker = OutboxWorker([dispatcher], interval_seconds=0.01)
        worker.start()
        await asyncio.sleep(0.15)
        await worker.stop()

    # The outbox still holds the events, so the next attempt is worth making.
    assert dispatcher.drains >= 2
    assert entries
    assert all(entry["event"] == "outbox.dispatch.failed" for entry in entries)


class _CountingSweeper:
    """Record the retention each sweep was asked for, and optionally fail."""

    def __init__(self, *, fails: bool = False) -> None:
        self.fails = fails
        self.retentions: list[float] = []

    async def sweep(self, retention_seconds: float) -> int:
        self.retentions.append(retention_seconds)
        if self.fails:
            raise RuntimeError("the outbox is unreachable")

        return 1


def test_a_cleanup_interval_that_is_not_positive_is_refused() -> None:
    with pytest.raises(ValueError, match="cleanup_interval_seconds must be positive"):
        OutboxWorker([], cleanup_interval_seconds=0)


def test_a_retention_that_is_not_positive_is_refused() -> None:
    with pytest.raises(ValueError, match="retention_seconds must be positive"):
        OutboxWorker([], retention_seconds=0)


def test_a_jitter_outside_the_unit_interval_is_refused() -> None:
    with pytest.raises(ValueError, match="jitter must be between 0 and 1"):
        OutboxWorker([], jitter=1)


def test_jitter_varies_the_cleanup_cadence() -> None:
    worker = OutboxWorker(
        [], cleanup_interval_seconds=100.0, jitter=0.5, random_source=Random(0)
    )

    waits = {worker.next_cleanup_delay() for _ in range(5)}

    assert len(waits) > 1
    assert all(50.0 <= wait <= 150.0 for wait in waits)


def test_without_jitter_the_cadence_is_exact() -> None:
    worker = OutboxWorker([], cleanup_interval_seconds=100.0, jitter=0)

    assert worker.next_cleanup_delay() == 100.0


async def test_a_worker_without_a_sweeper_does_no_cleanup() -> None:
    assert await OutboxWorker([]).sweep_once() == 0


async def test_sweep_once_asks_for_the_retention_it_was_given() -> None:
    sweeper = _CountingSweeper()
    worker = OutboxWorker([], sweeper=sweeper, retention_seconds=123.0)

    assert await worker.sweep_once() == 1
    assert sweeper.retentions == [123.0]


async def test_a_started_worker_cleans_up_on_its_cadence() -> None:
    sweeper = _CountingSweeper()
    worker = OutboxWorker(
        [],
        interval_seconds=0.01,
        sweeper=sweeper,
        cleanup_interval_seconds=0.03,
        jitter=0,
    )

    worker.start()
    try:
        await asyncio.sleep(0.2)
    finally:
        await worker.stop()

    assert len(sweeper.retentions) >= 2


async def test_a_failing_sweep_is_logged_and_retried() -> None:
    sweeper = _CountingSweeper(fails=True)

    # The worker is built inside the capture so its logger resolves against it.
    with captured_logs() as entries:
        worker = OutboxWorker(
            [],
            interval_seconds=0.01,
            sweeper=sweeper,
            cleanup_interval_seconds=0.02,
            jitter=0,
        )
        worker.start()
        await asyncio.sleep(0.2)
        await worker.stop()

    assert len(sweeper.retentions) >= 2
    assert any(entry["event"] == "outbox.cleanup.failed" for entry in entries)
