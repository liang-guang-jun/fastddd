"""Ambient execution context: what a request is about, and its transaction.

The context is carried in a single context variable rather than threaded down the
call chain, so a behavior or handler can read it — and the unit of work bound to
it — without being handed either. Entering a :class:`Context` binds it for the
current task and opens the transaction when it carries a unit of work; leaving
commits on a clean exit and rolls back on an exception.

Reading the ambient state with nothing bound raises the built-in ``LookupError``:
a missing scope is an infrastructure/programming error, not a violated domain
rule, so it is deliberately not reported as a domain error.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass, replace
from datetime import datetime
from types import TracebackType
from typing import TYPE_CHECKING, Any

from ...domain import require_timezone_aware

if TYPE_CHECKING:
    from ..ports.unit_of_work import UnitOfWork


@dataclass(frozen=True, slots=True)
class MessageMetadata:
    """Metadata attached to every message execution."""

    message_id: str
    correlation_id: str | None
    causation_id: str | None
    principal_id: str | None
    tenant_id: str | None
    occurred_at: datetime

    def __post_init__(self) -> None:
        """Reject a timestamp that cannot be compared with another.

        Raises:
            InvariantViolationError: If ``occurred_at`` is naive.
        """
        require_timezone_aware(self.occurred_at, field="occurred_at")


class Context:
    """The ambient scope of one execution: its metadata, and its transaction.

    One object is both the value and the async scope. Entering it binds the scope
    for the current task and opens the unit of work when one is supplied; leaving
    commits on a clean exit, rolls back on an exception, and restores whatever
    scope was bound before. Because it remembers what to restore, an instance is
    entered once rather than reused.
    """

    def __init__(
        self,
        metadata: MessageMetadata | None = None,
        unit_of_work: UnitOfWork | None = None,
    ) -> None:
        """Store what this scope is about and the transaction it runs in."""
        self.metadata = metadata
        self.unit_of_work = unit_of_work
        self._token: Token[Context | None] | None = None

    def with_metadata(self, **changes: Any) -> Context:
        """Return a sibling scope with updated metadata and the same transaction.

        Raises:
            LookupError: If this scope carries no metadata to update.
        """
        metadata = self.metadata
        if metadata is None:
            raise LookupError("The scope carries no message metadata")

        return Context(
            metadata=replace(metadata, **changes),
            unit_of_work=self.unit_of_work,
        )

    async def __aenter__(self) -> Context:
        """Bind this scope for the current task and open its transaction."""
        token = _current.set(self)
        self._token = token
        try:
            if self.unit_of_work is not None:
                await self.unit_of_work.__aenter__()
        except BaseException:
            _current.reset(token)
            self._token = None
            raise
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        """Commit or roll back the transaction, then restore the previous scope."""
        token = self._token
        self._token = None
        try:
            if self.unit_of_work is not None:
                await self.unit_of_work.__aexit__(exc_type, exc, tb)
        finally:
            if token is not None:
                _current.reset(token)


_current: ContextVar[Context | None] = ContextVar("application_context", default=None)


def current_context() -> Context:
    """Return the ambient scope, or raise when none is active.

    Raises:
        LookupError: If no context is active. A missing ambient scope is a
            programming error, not a domain rule violation.
    """
    ctx = _current.get()
    if ctx is None:
        raise LookupError("No active context")
    return ctx


def current_context_or_none() -> Context | None:
    """Return the ambient scope, or None if none is active."""
    return _current.get()


def current_metadata() -> MessageMetadata:
    """Return the metadata of the ambient scope.

    Raises:
        LookupError: If no metadata is bound — either because no scope is active
            or because the active scope carries none.
    """
    ctx = _current.get()
    metadata = None if ctx is None else ctx.metadata
    if metadata is None:
        raise LookupError("No active message metadata")
    return metadata


def current_unit_of_work() -> UnitOfWork:
    """Return the unit of work bound to the ambient scope.

    Raises:
        LookupError: If no unit of work is bound — either because no scope is
            active or because the active scope carries none. A missing ambient
            binding is a programming error, not a domain rule violation.
    """
    ctx = _current.get()
    uow = None if ctx is None else ctx.unit_of_work
    if uow is None:
        raise LookupError("No active unit of work")
    return uow


def current_unit_of_work_or_none() -> UnitOfWork | None:
    """Return the ambient unit of work, or None if none is bound."""
    ctx = _current.get()
    return None if ctx is None else ctx.unit_of_work
