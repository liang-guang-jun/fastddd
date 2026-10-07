"""The counter aggregate: the model, and nothing but the model.

This module imports the kernel's domain vocabulary and the standard library, and
nothing else -- no I/O, no framework, no clock, no identifier source. A domain
that can be read without a database is a domain that can be tested without one,
and it is what makes the layers above it swappable.

Two kernel decisions are visible here: an identifier is its own type (so a
counter's id can never be passed where a customer's is expected), and a fact the
aggregate records carries only what the aggregate knows -- the delivery details
are added by the application layer that publishes it.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from fastddd.domain import (
    Aggregate,
    DomainEvent,
    EntityId,
    InvariantViolationError,
    NotFoundError,
    require_non_blank,
)


class CounterNotFoundError(NotFoundError):
    """Raised when a counter is asked for and does not exist.

    ``NotFoundError`` is the type the application layer's ``require_found`` is
    typed against. Naming a ``code`` is what lets a client act on the failure --
    reload a list, show an empty state -- instead of reading the sentence, which
    is prose and belongs to this context.
    """

    code = "counter_not_found"


class CounterId(EntityId[UUID]):
    """Identity of a counter.

    ``EntityId`` derives equality and hashing from the pair (type, value); this
    class adds the value and its type. Nothing else is needed, so nothing else
    is here.
    """

    def __init__(self, value: UUID) -> None:
        """Wrap one identifier value."""
        self._value = value

    @property
    def value(self) -> UUID:
        """Return the identifier this identity stands for."""
        return self._value


@dataclass(frozen=True, slots=True)
class CounterChanged(DomainEvent):
    """Fact: a counter now reads this total.

    Recorded when a counter is created and whenever it changes, so the read side
    always has a state to fold. The alternative -- a separate creation fact --
    carries the same information under a second name and makes every consumer
    handle both.

    It deliberately carries no timestamp, no event id and no correlation id.
    Those describe the *delivery* of the fact, not the fact, and the aggregate is
    in no position to know them; the application layer's event mapper adds them
    when it turns this into an integration event.
    """

    counter_id: UUID
    label: str
    total: int


class Counter(Aggregate[UUID]):
    """A labelled counter that records one fact per change.

    ``Aggregate`` is the transactional boundary, and it inherits
    ``SoftDeletable``: ``delete(at=...)``, ``is_deleted`` and ``deleted_at`` come
    with it, and ``_require_not_deleted`` is what a behaviour calls to refuse
    work on a deleted instance.

    Every attribute change goes through a method, because a method is where the
    invariant is checked and where the fact gets recorded. A public mutable
    attribute would let a caller change state without leaving a trace, which is
    exactly what the outbox depends on not happening.
    """

    def __init__(
        self,
        id: CounterId,
        label: str,
        total: int = 0,
        deleted_at: datetime | None = None,
    ) -> None:
        """Rebuild a counter, newly created or reconstituted from storage."""
        super().__init__()
        self._id = id
        self.label = require_non_blank(label, field="label")
        self.total = total
        self._deleted_at = deleted_at

    @property
    def id(self) -> CounterId:
        """Return the identity of this aggregate."""
        return self._id

    @classmethod
    def create(cls, id: CounterId, label: str) -> Counter:
        """Start a new counter at zero and record that it now reads that.

        A factory method rather than an event-recording ``__init__``: the
        constructor's job is to rebuild state, from storage or from nothing, and
        reconstitution must never record a fact. Creating something, on the other
        hand, *is* a change the outside world needs to hear about.
        """
        counter = cls(id, label)

        counter._record_event(CounterChanged(id.value, counter.label, counter.total))

        return counter

    def increment(self, *, by: int = 1) -> None:
        """Advance the counter and record the fact.

        Raises:
            AggregateDeletedError: If the counter was soft-deleted.
            InvariantViolationError: If ``by`` is below one, which would make
                "advance" mean two different things.
        """
        self._require_not_deleted(action="increment")
        if by < 1:
            raise InvariantViolationError("a counter advances by at least one")

        self.total += by
        self._record_event(CounterChanged(self._id.value, self.label, self.total))
