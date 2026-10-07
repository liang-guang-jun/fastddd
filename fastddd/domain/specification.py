"""Specification abstraction: composable domain predicates."""

from __future__ import annotations

from abc import ABC, abstractmethod


class Specification[T](ABC):
    """Base class for specifications.

    Describes whether a candidate satisfies a business condition.
    Supports composition via &, |, and ~.
    """

    @abstractmethod
    def is_satisfied_by(self, candidate: T) -> bool:
        """Return True if the candidate satisfies this specification."""
        raise NotImplementedError

    def __and__(self, other: Specification[T]) -> Specification[T]:
        """Combine two specifications with logical AND."""
        return _AndSpecification(self, other)

    def __or__(self, other: Specification[T]) -> Specification[T]:
        """Combine two specifications with logical OR."""
        return _OrSpecification(self, other)

    def __invert__(self) -> Specification[T]:
        """Negate this specification."""
        return _NotSpecification(self)


class _AndSpecification[T](Specification[T]):
    """Logical AND of two specifications."""

    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        """Store the left and right specifications."""
        self._left = left
        self._right = right

    def is_satisfied_by(self, candidate: T) -> bool:
        """Return True if both specifications are satisfied."""
        return self._left.is_satisfied_by(candidate) and self._right.is_satisfied_by(
            candidate
        )


class _OrSpecification[T](Specification[T]):
    """Logical OR of two specifications."""

    def __init__(self, left: Specification[T], right: Specification[T]) -> None:
        """Store the left and right specifications."""
        self._left = left
        self._right = right

    def is_satisfied_by(self, candidate: T) -> bool:
        """Return True if either specification is satisfied."""
        return self._left.is_satisfied_by(candidate) or self._right.is_satisfied_by(
            candidate
        )


class _NotSpecification[T](Specification[T]):
    """Logical NOT of a specification."""

    def __init__(self, spec: Specification[T]) -> None:
        """Store the specification to negate."""
        self._spec = spec

    def is_satisfied_by(self, candidate: T) -> bool:
        """Return True if the specification is not satisfied."""
        return not self._spec.is_satisfied_by(candidate)
