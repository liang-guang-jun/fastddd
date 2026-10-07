"""MessageBus abstraction: entry point for commands and queries."""

from __future__ import annotations

from .behavior import Behavior
from .handler import Handler
from .message import Command, Message, Query
from .pipeline import Pipeline
from .registry import BehaviorRegistry, HandlerRegistry


class MessageBus:
    """Resolves handlers and behaviors, builds a pipeline, runs it."""

    def __init__(
        self,
        handlers: HandlerRegistry,
        behaviors: BehaviorRegistry,
    ) -> None:
        """Store the resolvers. Registration happens elsewhere."""
        self._handlers = handlers
        self._behaviors = behaviors

    async def send[TResult](self, command: Command[TResult]) -> TResult:
        """Dispatch a command through the behavior pipeline."""
        return await self._dispatch(command)

    async def ask[TResult](self, query: Query[TResult]) -> TResult:
        """Dispatch a query through the behavior pipeline."""
        return await self._dispatch(query)

    async def _dispatch[TResult](self, message: Message) -> TResult:
        """Resolve, compose, and execute the pipeline."""
        handler: Handler[Message, TResult] = self._handlers.resolve(message)
        behaviors: list[Behavior[Message, TResult]] = self._behaviors.for_message(
            message
        )
        pipeline = Pipeline(handler, behaviors)
        return await pipeline.execute(message)
