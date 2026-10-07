"""One bounded context: the counter's model, use cases, adapters and routes.

A context owns its whole vertical slice. Nothing in here imports another
context's internals -- contexts talk to each other through integration events,
which is why ``CounterEventMapper`` is the only thing in this package that knows
what leaves it.
"""

from .application import (
    COUNTER_CHANGED,
    CounterEventMapper,
    CounterView,
    CreateCounter,
    CreateCounterHandler,
    GetCounter,
    GetCounterHandler,
    IncrementCounter,
    IncrementCounterHandler,
)
from .domain import Counter, CounterChanged, CounterId, CounterNotFoundError
from .interface import COUNTER_STATUS_TABLE, create_counter_router
from .persistence import (
    CounterChangedPayload,
    CounterMapper,
    CounterProjectionRecord,
    CounterReadStore,
    CounterRecord,
    CounterRepository,
    CounterTotalsProjection,
)

__all__ = [
    "COUNTER_CHANGED",
    "COUNTER_STATUS_TABLE",
    "Counter",
    "CounterChanged",
    "CounterChangedPayload",
    "CounterEventMapper",
    "CounterId",
    "CounterMapper",
    "CounterNotFoundError",
    "CounterProjectionRecord",
    "CounterReadStore",
    "CounterRecord",
    "CounterRepository",
    "CounterTotalsProjection",
    "CounterView",
    "CreateCounter",
    "CreateCounterHandler",
    "GetCounter",
    "GetCounterHandler",
    "IncrementCounter",
    "IncrementCounterHandler",
    "create_counter_router",
]
