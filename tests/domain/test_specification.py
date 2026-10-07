"""Tests for composable domain predicates."""

from __future__ import annotations

import inspect

from fastddd.domain.specification import Specification


class Positive(Specification[int]):
    """Candidate must be greater than zero."""

    def is_satisfied_by(self, candidate: int) -> bool:
        return candidate > 0


class Even(Specification[int]):
    """Candidate must be even."""

    def is_satisfied_by(self, candidate: int) -> bool:
        return candidate % 2 == 0


def test_specification_is_abstract() -> None:
    assert inspect.isabstract(Specification)


def test_a_specification_decides_a_single_candidate() -> None:
    assert Positive().is_satisfied_by(1)
    assert not Positive().is_satisfied_by(0)


def test_and_requires_both_conditions() -> None:
    both = Positive() & Even()

    assert both.is_satisfied_by(4)
    assert not both.is_satisfied_by(3)
    assert not both.is_satisfied_by(-2)


def test_or_requires_either_condition() -> None:
    either = Positive() | Even()

    assert either.is_satisfied_by(3)
    assert either.is_satisfied_by(-2)
    assert not either.is_satisfied_by(-3)


def test_not_negates_a_condition() -> None:
    assert (~Positive()).is_satisfied_by(-1)
    assert not (~Positive()).is_satisfied_by(1)


def test_composition_is_nestable() -> None:
    combined = (Positive() & Even()) | (~Positive())

    assert combined.is_satisfied_by(4)
    assert combined.is_satisfied_by(-1)
    assert not combined.is_satisfied_by(3)


def test_every_composition_returns_a_specification() -> None:
    assert isinstance(Positive() & Even(), Specification)
    assert isinstance(Positive() | Even(), Specification)
    assert isinstance(~Positive(), Specification)
