"""Entity abstraction: a domain object with identity and mutable state."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Hashable


class EntityId[T: Hashable](ABC):
    """Base class for entity identity values.

    Two IDs of the same type with equal underlying values refer to
    the same identity.
    """

    @property
    @abstractmethod
    def value(self) -> T:
        """Return the underlying value of this identity."""
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        """Compare equality by type and underlying value."""
        if not isinstance(other, EntityId):
            return NotImplemented
        return type(self) is type(other) and self.value == other.value

    def __hash__(self) -> int:
        """Hash by type and underlying value."""
        return hash((type(self), self.value))

    def __str__(self) -> str:
        """Return the string representation of this identity."""
        return str(self.value)


class Entity[TId: Hashable](ABC):
    """Base class for domain entities.

    An entity's equality is determined by its identity, not by its
    attribute values.
    """

    @property
    @abstractmethod
    def id(self) -> EntityId[TId]:
        """Return the identity of this entity."""
        raise NotImplementedError

    def __eq__(self, other: object) -> bool:
        """Compare equality by type and identity."""
        if self is other:
            return True
        if type(self) is not type(other):
            return False
        return self.id == other.id

    def __hash__(self) -> int:
        """Hash by type and identity."""
        return hash((type(self), self.id))
