"""Tests for the handler and behavior registries."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import pytest

from fastddd.application.messaging.behavior import Behavior
from fastddd.application.messaging.handler import EventHandler, Handler
from fastddd.application.messaging.message import Command, Message
from fastddd.application.messaging.registry import (
    BehaviorRegistry,
    EventHandlerRegistry,
    HandlerRegistry,
    TypeRegistry,
)
from fastddd.domain import DomainEvent


@dataclass(frozen=True, slots=True)
class RenameAccount(Command[None]):
    """Sample command."""

    name: str


@dataclass(frozen=True, slots=True)
class AccountRenamed(DomainEvent):
    """Sample domain event."""

    name: str


class RenameAccountHandler(Handler[RenameAccount, str]):
    """Handler answering with the new name."""

    async def handle(self, message: RenameAccount) -> str:
        return message.name


class OtherRenameHandler(Handler[RenameAccount, str]):
    """Second handler for the same message, used to prove duplicates are refused."""

    async def handle(self, message: RenameAccount) -> str:
        return "other"


class RecordingEvents(EventHandler[AccountRenamed]):
    """Event handler carrying a label."""

    def __init__(self, label: str) -> None:
        self.label = label

    async def handle(self, event: AccountRenamed) -> None:
        pass


class Tagged[TMessage, TResult](Behavior[TMessage, TResult]):
    """Behavior that merely delegates, carrying a tag."""

    def __init__(self, tag: str) -> None:
        self.tag = tag

    async def handle(
        self,
        message: TMessage,
        next_: Callable[[TMessage], Awaitable[TResult]],
    ) -> TResult:
        return await next_(message)


def test_type_registry_resolves_by_concrete_type_in_registration_order() -> None:
    registry: TypeRegistry[str, int] = TypeRegistry()
    registry.register(str, 1)
    registry.register(str, 2)

    assert registry.resolve("a") == (1, 2)
    assert registry.resolve_type(str) == (1, 2)
    assert registry.contains(str)
    assert registry.key_types() == (str,)


def test_type_registry_returns_nothing_for_an_unregistered_type() -> None:
    registry: TypeRegistry[str, int] = TypeRegistry()

    assert registry.resolve("a") == ()
    assert not registry.contains(str)
    assert registry.key_types() == ()


def test_handler_registry_resolves_the_single_handler() -> None:
    registry = HandlerRegistry()
    handler = RenameAccountHandler()
    registry.register(RenameAccount, handler)

    assert registry.resolve(RenameAccount(name="ada")) is handler
    assert registry.message_types() == (RenameAccount,)


def test_handler_registry_refuses_a_second_handler_for_the_same_message() -> None:
    registry = HandlerRegistry()
    registry.register(RenameAccount, RenameAccountHandler())

    with pytest.raises(ValueError, match="already registered"):
        registry.register(RenameAccount, OtherRenameHandler())


def test_handler_registry_reports_an_unregistered_message() -> None:
    registry = HandlerRegistry()

    with pytest.raises(LookupError, match="No handler registered"):
        registry.resolve(RenameAccount(name="ada"))


def test_event_handler_registry_resolves_every_handler_for_the_type() -> None:
    registry = EventHandlerRegistry()
    first = RecordingEvents("first")
    second = RecordingEvents("second")
    registry.register(AccountRenamed, first)
    registry.register(AccountRenamed, second)

    handlers = list(registry.resolve(AccountRenamed(name="ada")))

    assert len(handlers) == 2
    assert handlers[0] is first
    assert handlers[1] is second


def test_event_handler_registry_returns_nothing_when_unregistered() -> None:
    assert list(EventHandlerRegistry().resolve(AccountRenamed(name="ada"))) == []


def test_behavior_registry_runs_globals_before_message_specifics() -> None:
    registry = BehaviorRegistry()
    glob = Tagged[Message, Any]("global")
    specific = Tagged[RenameAccount, Any]("specific")
    registry.register_global(glob)
    registry.register_for(RenameAccount, specific)

    behaviors: list[Behavior[Message, Any]] = registry.for_message(
        RenameAccount(name="ada")
    )

    assert len(behaviors) == 2
    assert behaviors[0] is glob
    assert behaviors[1] is specific


def test_behavior_registry_returns_only_globals_when_none_are_specific() -> None:
    registry = BehaviorRegistry()
    glob = Tagged[Message, Any]("global")
    registry.register_global(glob)

    behaviors: list[Behavior[Message, Any]] = registry.for_message(
        RenameAccount(name="ada")
    )

    assert len(behaviors) == 1
    assert behaviors[0] is glob
