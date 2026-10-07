"""Message-pipeline behavior that logs execution lifecycle and outcome."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from time import perf_counter

from ...application.execution.context import current_context_or_none
from ...application.messaging.behavior import Behavior
from ...application.messaging.message import Message
from .logger import bind_context, get_logger


class LoggingBehavior[TMessage: Message, TResult](Behavior[TMessage, TResult]):
    """Log a message's start, completion status, and elapsed processing time."""

    def __init__(self, name: str = "server.message") -> None:
        """Create a behavior using one stable logger name for message execution."""
        self._logger = get_logger(name)

    async def handle(
        self,
        message: TMessage,
        next_: Callable[[TMessage], Awaitable[TResult]],
    ) -> TResult:
        """Emit lifecycle logs while preserving all caller-bound context variables."""
        context = current_context_or_none()
        metadata = context.metadata if context is not None else None
        message_type = f"{type(message).__module__}.{type(message).__qualname__}"
        with bind_context(
            message_id=metadata.message_id if metadata else None,
            correlation_id=metadata.correlation_id if metadata else None,
            causation_id=metadata.causation_id if metadata else None,
            principal_id=metadata.principal_id if metadata else None,
            tenant_id=metadata.tenant_id if metadata else None,
        ):
            started_at = perf_counter()
            self._logger.info("message.started", message_type=message_type)
            try:
                result = await next_(message)
            except Exception:
                self._logger.exception(
                    "message.finished",
                    message_type=message_type,
                    success=False,
                    duration_ms=round((perf_counter() - started_at) * 1000, 3),
                )
                raise
            self._logger.info(
                "message.finished",
                message_type=message_type,
                success=True,
                duration_ms=round((perf_counter() - started_at) * 1000, 3),
            )
            return result
