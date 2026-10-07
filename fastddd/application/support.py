"""Shared helpers for application handlers.

These are vocabulary rather than adapters: every bounded context that
orchestrates aggregates needs a typed not-found guard and one place that turns
recorded domain events into the outbox, so they live in the kernel instead of
being copied into each context.
"""

from __future__ import annotations

from collections.abc import Awaitable

from ..domain.error import NotFoundError
from .execution.context import MessageMetadata
from .integration import DomainEventMapper
from .ports import UnitOfWork


async def require_found[TAggregate](
    load: Awaitable[TAggregate | None],
    *,
    subject: str,
    error_type: type[NotFoundError],
) -> TAggregate:
    """Return the loaded aggregate, or raise ``error_type`` naming the subject.

    Repositories stay plain lookups that return ``None``; the application decides
    here which not-found error a use case raises, so the persistence port needs no
    ``required`` flag and the transport layer keeps its typed error mapping.
    """
    aggregate = await load
    if aggregate is None:
        raise error_type(f"{subject} does not exist")

    return aggregate


async def enqueue_integration_events(
    uow: UnitOfWork,
    mapper: DomainEventMapper,
    metadata: MessageMetadata | None = None,
) -> None:
    """Translate everything the unit of work collected and append it to the outbox.

    A use case records domain events on the aggregates it changed, and this is what
    turns them into the facts other contexts consume. The two steps belong together
    — the translation, and the append that joins the same transaction — so the
    command pipeline and anything else that writes through a unit of work do both
    through one function instead of each keeping its own copy.
    """
    for domain_event in uow.pull_events():
        for integration_event in mapper.map(domain_event, metadata):
            await uow.outbox.append(integration_event)
