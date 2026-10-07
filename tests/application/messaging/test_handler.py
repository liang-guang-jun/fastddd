"""Tests for the handler abstractions."""

from __future__ import annotations

import inspect
from dataclasses import dataclass

from fastddd.application.messaging.handler import (
    CommandHandler,
    EventHandler,
    Handler,
    QueryHandler,
)
from fastddd.application.messaging.message import Command, Query


@dataclass(frozen=True, slots=True)
class RenameAccount(Command[None]):
    """Sample command."""

    name: str


@dataclass(frozen=True, slots=True)
class GetAccount(Query[str]):
    """Sample query."""

    account_id: int


class RenameAccountHandler(CommandHandler[RenameAccount, None]):
    """Concrete command handler recording what it handled."""

    def __init__(self) -> None:
        self.seen: list[str] = []

    async def handle(self, message: RenameAccount) -> None:
        self.seen.append(message.name)


class GetAccountHandler(QueryHandler[GetAccount, str]):
    """Concrete query handler returning a projection."""

    async def handle(self, message: GetAccount) -> str:
        return f"account-{message.account_id}"


class RecordingEvents(EventHandler[str]):
    """Concrete event handler recording every event it consumes."""

    def __init__(self) -> None:
        self.events: list[str] = []

    async def handle(self, event: str) -> None:
        self.events.append(event)


def test_handler_abstractions_are_abstract() -> None:
    assert inspect.isabstract(Handler)
    assert inspect.isabstract(CommandHandler)
    assert inspect.isabstract(QueryHandler)
    assert inspect.isabstract(EventHandler)


async def test_a_command_handler_executes_its_use_case() -> None:
    handler = RenameAccountHandler()

    await handler.handle(RenameAccount(name="ada"))

    assert handler.seen == ["ada"]


async def test_a_query_handler_returns_its_result() -> None:
    assert await GetAccountHandler().handle(GetAccount(account_id=7)) == "account-7"


async def test_an_event_handler_consumes_an_event() -> None:
    handler = RecordingEvents()

    await handler.handle("account.renamed")

    assert handler.events == ["account.renamed"]
