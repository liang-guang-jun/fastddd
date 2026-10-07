"""Domain error hierarchy: semantic failures within the domain layer."""

from __future__ import annotations

from typing import ClassVar


class DomainError(Exception):
    """Base class for all domain errors.

    Domain errors describe business-level failures. They are raised
    by domain objects and translated into transport-level errors
    (HTTP, gRPC, etc.) by the application or infrastructure layer.
    """

    code: ClassVar[str | None] = None
    """The name this failure travels under, when a caller has to act on it differently.

    Most failures are told apart well enough by their status and their message. One kind is
    not: a write decided against a version somebody else has moved past, where the caller's
    next move is to read the resource again. Those name themselves, so a client refreshes on
    the name instead of reading the sentence the failure happens to carry.
    """


class InvariantViolationError(DomainError):
    """Raised when an aggregate invariant is broken.

    Signals a state that should never be reachable, regardless of
    the operation being performed.
    """


class BusinessRuleViolationError(DomainError):
    """Raised when a business rule forbids the current operation.

    Signals that the operation is not allowed under the current
    state or context.
    """


class NotFoundError(DomainError):
    """Raised when a requested aggregate or entity does not exist."""


class ConflictError(DomainError):
    """Raised on concurrency conflicts or uniqueness violations."""


class AggregateDeletedError(BusinessRuleViolationError):
    """Raised when a soft-deleted aggregate is changed any further."""


class AuthenticationRequiredError(DomainError):
    """Raised when an operation needs a caller and the request carries none.

    Being refused for this reason is not the same as being refused for doing
    something forbidden: the caller can fix it by signing in, which is why the
    interface layer answers 401 for it and 403 for an authorization refusal.
    """


class AuthorizationDeniedError(DomainError):
    """Raised when the caller is known but not allowed to do what it asked.

    The reason the decision gave travels with the error, so the sentence the
    caller reads names the condition that failed: an unusable tenant, a missing
    membership, or an absent grant instead of only "forbidden".
    """

    def __init__(self, detail: str, *, reason: str) -> None:
        """Store what happened and the machine-readable reason for it."""
        super().__init__(detail)
        self.reason = reason
