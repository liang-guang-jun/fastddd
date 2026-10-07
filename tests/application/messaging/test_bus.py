"""Tests for the message bus."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from fastddd.application.messaging.behavior import Behavior
from fastddd.application.messaging.bus import MessageBus
from fastddd.application.messaging.handler import CommandHandler, QueryHandler
from fastddd.application.messaging.message import Command, Message, Query
from fastddd.application.messaging.registry import (
    BehaviorRegistry,
    HandlerRegistry,
)


@dataclass(frozen=True, slots=True)
class RenameAccount(Command[str]):
    """Sample command returning the new name."""

    name: str


@dataclass(frozen=True, slots=True)
class GetAccount(Query[int]):
    """Sample query returning the account id."""

    account_id: int


class RenameAccountHandler(CommandHandler[RenameAccount, str]):
    """Command handler returning the new name."""

    async def handle(self, message: RenameAccount) -> str:
        return message.name


class GetAccountHandler(QueryHandler[GetAccount, int]):
    """Query handler returning the account id."""

    async def handle(self, message: GetAccount) -> int:
        return message.account_id


class Recording(Behavior[Message, Any]):
    """Behavior recording every message it sees."""

    def __init__(self, log: list[str]) -> None:
        self._log = log

    async def handle(
        self,
        message: Message,
        next_: Callable[[Message], Awaitable[Any]],
    ) -> Any:
        self._log.append(type(message).__name__)
        return await next_(message)


def build_bus(log: list[str]) -> MessageBus:
    """Return a bus with both handlers and one global behavior."""
    handlers = HandlerRegistry()
    handlers.register(RenameAccount, RenameAccountHandler())
    handlers.register(GetAccount, GetAccountHandler())

    behaviors = BehaviorRegistry()
    behaviors.register_global(Recording(log))

    return MessageBus(handlers, behaviors)


async def test_send_dispatches_a_command_to_its_handler() -> None:
    assert await build_bus([]).send(RenameAccount(name="ada")) == "ada"


async def test_ask_dispatches_a_query_to_its_handler() -> None:
    assert await build_bus([]).ask(GetAccount(account_id=7)) == 7


async def test_the_bus_runs_behaviors_around_the_handler() -> None:
    log: list[str] = []

    await build_bus(log).send(RenameAccount(name="ada"))

    assert log == ["RenameAccount"]


async def test_the_bus_reports_an_unregistered_message() -> None:
    bus = MessageBus(HandlerRegistry(), BehaviorRegistry())

    with pytest.raises(LookupError, match="No handler registered"):
        await bus.send(RenameAccount(name="ada"))
