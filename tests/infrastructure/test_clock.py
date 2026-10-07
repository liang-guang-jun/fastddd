"""Tests for the one system clock the infrastructure layer reads."""

from __future__ import annotations

from datetime import UTC, datetime

from fastddd.application.ports import Clock
from fastddd.infrastructure.clock import SystemClock


def test_the_clock_reports_an_aware_utc_moment() -> None:
    now = SystemClock.now()

    assert isinstance(now, datetime)
    assert now.tzinfo is UTC


def test_the_clock_reports_the_current_moment() -> None:
    before = datetime.now(UTC)
    now = SystemClock.now()
    after = datetime.now(UTC)

    assert before <= now <= after


def test_an_instance_satisfies_the_application_clock_port() -> None:
    clock: Clock = SystemClock()

    assert isinstance(clock.now(), datetime)
