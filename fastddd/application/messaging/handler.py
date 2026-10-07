"""Handler abstractions for commands and queries."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .message import Command, Message, Query


class Handler[TMessage: Message, TResult](ABC):
    """Base class for application message handlers."""

    @abstractmethod
    async def handle(self, message: TMessage) -> TResult:
        """Execute the use case for the given message."""
        raise NotImplementedError


class CommandHandler[TCommand: Command[Any], TResult](
    Handler[TCommand, TResult],
    ABC,
):
    """Base class for command handlers."""


class QueryHandler[TQuery: Query[Any], TResult](
    Handler[TQuery, TResult],
    ABC,
):
    """Base class for query handlers."""


class EventHandler[TEvent](ABC):
    """Consumer of an event delivered by an event publisher."""

    @abstractmethod
    async def handle(self, event: TEvent) -> None:
        """Handle a single event."""
        raise NotImplementedError
