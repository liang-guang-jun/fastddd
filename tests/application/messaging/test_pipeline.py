"""Tests for the behavior/handler pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastddd.application.messaging.behavior import Behavior
from fastddd.application.messaging.handler import Handler
from fastddd.application.messaging.message import Command
from fastddd.application.messaging.pipeline import Pipeline


@dataclass(frozen=True, slots=True)
class EchoCommand(Command[str]):
    """Sample command carrying the text to echo."""

    text: str


class EchoHandler(Handler[EchoCommand, str]):
    """Handler returning the upper-cased text."""

    async def handle(self, message: EchoCommand) -> str:
        return message.text.upper()


class Tag(Behavior[EchoCommand, str]):
    """Behavior tagging the result with its label."""

    def __init__(self, log: list[str], tag: str) -> None:
        self._log = log
        self._tag = tag

    async def handle(
        self,
        message: EchoCommand,
        next_: Callable[[EchoCommand], Awaitable[str]],
    ) -> str:
        self._log.append(self._tag)
        return f"[{self._tag}]{await next_(message)}"


async def test_a_pipeline_without_behaviors_runs_the_handler() -> None:
    assert await Pipeline(EchoHandler(), []).execute(EchoCommand(text="hi")) == "HI"


async def test_behaviors_run_outermost_first_and_closest_to_the_handler_last() -> None:
    log: list[str] = []
    pipeline = Pipeline(EchoHandler(), [Tag(log, "outer"), Tag(log, "inner")])

    result = await pipeline.execute(EchoCommand(text="hi"))

    assert result == "[outer][inner]HI"
    assert log == ["outer", "inner"]
