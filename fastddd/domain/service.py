"""Domain service abstraction: stateless logic spanning multiple aggregates."""

from __future__ import annotations


class DomainService:
    """Base class for domain services.

    A domain service holds stateless, side-effect-free logic that
    does not naturally belong to a single aggregate or value object.
    It must not touch external systems such as databases, message
    brokers, or remote APIs; those belong to the application or
    infrastructure layer.
    """
