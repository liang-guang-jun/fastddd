"""Behavior abstraction: middleware for the handler pipeline."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable


class Behavior[TMessage, TResult](ABC):
    """Middleware for the handler pipeline.

    A behavior wraps the next step in the chain, allowing it to
    perform work before and after the handler executes.
    """

    @abstractmethod
    async def handle(
        self,
        message: TMessage,
        next_: Callable[[TMessage], Awaitable[TResult]],
    ) -> TResult:
        """Process the message and optionally delegate to ``next_``."""
        raise NotImplementedError
