"""Tests for application messages: commands and queries."""

from __future__ import annotations

from dataclasses import dataclass

from fastddd.application.messaging.message import Command, Message, Query


@dataclass(frozen=True, slots=True)
class RenameAccount(Command[None]):
    """Sample command."""

    name: str


@dataclass(frozen=True, slots=True)
class GetAccount(Query[str]):
    """Sample query."""

    account_id: int


def test_commands_and_queries_are_messages() -> None:
    assert issubclass(Command, Message)
    assert issubclass(Query, Message)


def test_a_command_carries_its_payload() -> None:
    command = RenameAccount(name="ada")

    assert isinstance(command, Command)
    assert isinstance(command, Message)
    assert command.name == "ada"


def test_a_query_carries_its_payload() -> None:
    query = GetAccount(account_id=7)

    assert isinstance(query, Query)
    assert isinstance(query, Message)
    assert query.account_id == 7
