"""The counter's HTTP routes: a transport, and nothing else.

No route decides anything. Each one validates its input, turns it into a command
or a query, hands it to the bus and wraps the answer in the standard envelope, so
the rules stay in one place and a test of those rules needs no HTTP client.

The status table is *data*, not a handler: the kernel keeps one exception handler
per application and lets each context contribute the statuses its own failures
travel under.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status
from pydantic import BaseModel, Field

from fastddd.application import MessageBus
from fastddd.domain import InvariantViolationError
from fastddd.interface import ResponseSchemaModel, StatusTable

from .application import CounterView, CreateCounter, GetCounter, IncrementCounter
from .domain import CounterNotFoundError

COUNTER_STATUS_TABLE: StatusTable = (
    # An exact class match outranks an inherited one, so this stays a 404 even
    # though the kernel also maps the base classes these errors derive from.
    (CounterNotFoundError, status.HTTP_404_NOT_FOUND),
    # The domain refused what the transport let through. Both happen: the request
    # model is the cheap first line, the aggregate's invariant is the authority.
    (InvariantViolationError, status.HTTP_400_BAD_REQUEST),
)


class CreateCounterRequest(BaseModel):
    """What a client sends to create a counter.

    The transport has its own shape, validated here, and the command it becomes
    is a separate thing. That separation is what lets the HTTP contract change
    without touching a use case.
    """

    label: str = Field(min_length=1, max_length=50)


class IncrementCounterRequest(BaseModel):
    """What a client sends to advance a counter."""

    by: int = Field(default=1, ge=1)


def create_counter_router(bus: MessageBus) -> APIRouter:
    """Return this context's routes, bound to the application's bus.

    The bus arrives as an argument rather than as an import, so the router can be
    mounted on any application built from the same use cases.
    """
    router = APIRouter(prefix="/counters", tags=["counters"])

    @router.post(
        "",
        response_model=ResponseSchemaModel[CounterView],
        status_code=status.HTTP_201_CREATED,
    )
    async def create_counter(
        payload: CreateCounterRequest,
    ) -> ResponseSchemaModel[CounterView]:
        """Create a counter, returning it at zero."""
        view = await bus.send(CreateCounter(label=payload.label))

        return ResponseSchemaModel[CounterView](data=view)

    @router.post(
        "/{counter_id}/increments",
        response_model=ResponseSchemaModel[CounterView],
    )
    async def increment_counter(
        counter_id: UUID,
        payload: IncrementCounterRequest,
    ) -> ResponseSchemaModel[CounterView]:
        """Advance a counter, returning its new total."""
        view = await bus.send(IncrementCounter(counter_id=counter_id, by=payload.by))

        return ResponseSchemaModel[CounterView](data=view)

    @router.get("/{counter_id}", response_model=ResponseSchemaModel[CounterView])
    async def get_counter(counter_id: UUID) -> ResponseSchemaModel[CounterView]:
        """Return one counter, as the read side sees it."""
        view = await bus.ask(GetCounter(counter_id=counter_id))

        return ResponseSchemaModel[CounterView](data=view)

    return router
