"""ValueObject abstraction: immutable, identity-less domain objects."""

from __future__ import annotations


class ValueObject:
    """Base class for value objects.

    A value object is immutable, has no identity, and its equality
    is defined by all of its attributes. Concrete implementations
    are recommended to be frozen dataclasses.
    """

    __slots__ = ()
