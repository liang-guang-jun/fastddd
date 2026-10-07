"""Tests for the handler-pipeline middleware abstraction."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable

from fastddd.application.messaging.behavior import Behavior


class Recording(Behavior[str, str]):
    """Behavior that logs around the next step."""

    def __init__(self, log: list[str], label: str) -> None:
        self._log = log
        self._label = label

    async def handle(
        self,
        message: str,
        next_: Callable[[str], Awaitable[str]],
    ) -> str:
        self._log.append(f"{self._label}:before")
        result = await next_(message)
        self._log.append(f"{self._label}:after")
        return result


class ShortCircuit(Behavior[str, str]):
    """Behavior that never delegates to the next step."""

    async def handle(
        self,
        message: str,
        next_: Callable[[str], Awaitable[str]],
    ) -> str:
        return "short"


def test_behavior_is_abstract() -> None:
    assert inspect.isabstract(Behavior)


async def test_a_behavior_wraps_the_next_step() -> None:
    log: list[str] = []

    async def tail(message: str) -> str:
        log.append("handler")
        return message.upper()

    result = await Recording(log, "outer").handle("x", tail)

    assert result == "X"
    assert log == ["outer:before", "handler", "outer:after"]


async def test_a_behavior_may_short_circuit_the_chain() -> None:
    async def tail(message: str) -> str:
        raise AssertionError("the tail must not run")

    assert await ShortCircuit().handle("x", tail) == "short"
