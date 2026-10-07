"""Transaction behavior for command pipelines backed by a unit of work."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from ...application.execution.context import (
    Context,
    current_context_or_none,
    current_unit_of_work_or_none,
)
from ...application.integration.mapping import DomainEventMapper
from ...application.messaging.behavior import Behavior
from ...application.messaging.message import Command
from ...application.ports import UnitOfWork
from ...application.support import enqueue_integration_events


class TransactionBehavior[TResult](Behavior[Command[TResult], TResult]):
    """Commit a command's write model and integration outbox atomically."""

    def __init__(
        self,
        uow_factory: Callable[[], UnitOfWork],
        mapper: DomainEventMapper,
        *,
        after_commit: Callable[[], Awaitable[object]] | None = None,
    ) -> None:
        """Store the transactional UoW factory, event mapper, and delivery hook.

        ``after_commit`` is how a single-process deployment delivers what a
        command just wrote before answering its caller: it runs once the
        transaction is closed, so a consumer writes through its own unit of work
        instead of joining a transaction that is already committing. A context
        that publishes to an external broker leaves it unset and relies on the
        outbox worker alone.
        """
        self._uow_factory = uow_factory
        self._mapper = mapper
        self._after_commit = after_commit

    async def handle(
        self,
        message: Command[TResult],
        next_: Callable[[Command[TResult]], Awaitable[TResult]],
    ) -> TResult:
        """Run the handler, enqueue integration events, and commit once.

        Raises:
            RuntimeError: If a unit of work is already bound. This behavior owns
                the outermost transaction, so a nested one would commit twice.
        """
        if current_unit_of_work_or_none() is not None:
            raise RuntimeError(
                "TransactionBehavior must be the outermost transaction owner"
            )

        # Entering a scope replaces whatever was bound, so the caller's metadata
        # has to be carried into this one explicitly.
        ambient = current_context_or_none()
        metadata = ambient.metadata if ambient is not None else None

        uow = self._uow_factory()
        async with Context(metadata, uow):
            result = await next_(message)
            await enqueue_integration_events(uow, self._mapper, metadata)
        # Leaving the scope committed the transaction, so delivery happens
        # outside it and a consumer writes through its own unit of work.

        if self._after_commit is not None and isinstance(message, Command):
            await self._after_commit()

        return result
