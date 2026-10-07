"""Domain layer kernel abstractions."""

from __future__ import annotations

from .aggregate import Aggregate, SoftDeletable, VersionedAggregate
from .entity import Entity, EntityId
from .error import (
    AggregateDeletedError,
    AuthenticationRequiredError,
    AuthorizationDeniedError,
    BusinessRuleViolationError,
    ConflictError,
    DomainError,
    InvariantViolationError,
    NotFoundError,
)
from .event import DomainEvent
from .invariant import require_non_blank, require_timezone_aware
from .pagination import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    InvalidCursorError,
    Page,
    PageRequest,
    decode_cursor,
    encode_cursor,
)
from .repository import AggregateRepository
from .specification import Specification
from .value_object import ValueObject

__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "Aggregate",
    "AggregateDeletedError",
    "AggregateRepository",
    "AuthenticationRequiredError",
    "AuthorizationDeniedError",
    "BusinessRuleViolationError",
    "ConflictError",
    "DomainError",
    "DomainEvent",
    "Entity",
    "EntityId",
    "InvalidCursorError",
    "InvariantViolationError",
    "NotFoundError",
    "Page",
    "PageRequest",
    "SoftDeletable",
    "Specification",
    "ValueObject",
    "VersionedAggregate",
    "decode_cursor",
    "encode_cursor",
    "require_non_blank",
    "require_timezone_aware",
]
