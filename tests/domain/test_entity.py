"""Tests for entity identity and identity-based equality."""

from __future__ import annotations

import inspect

from fastddd.domain.entity import Entity, EntityId


class AccountId(EntityId[int]):
    """Identity of the sample account."""

    def __init__(self, value: int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value


class OtherId(EntityId[int]):
    """A different identity type carrying the same underlying value."""

    def __init__(self, value: int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value


class Account(Entity[int]):
    """Sample entity whose equality must follow its identity."""

    def __init__(self, account_id: AccountId, name: str) -> None:
        self._account_id = account_id
        self.name = name

    @property
    def id(self) -> EntityId[int]:
        return self._account_id


def test_entity_and_entity_id_are_abstract() -> None:
    assert inspect.isabstract(Entity)
    assert inspect.isabstract(EntityId)


def test_entity_id_equality_uses_type_and_value() -> None:
    assert AccountId(1) == AccountId(1)
    assert AccountId(1) != AccountId(2)
    assert AccountId(1) != OtherId(1)
    assert AccountId(1) != 1


def test_entity_id_hashes_by_type_and_value() -> None:
    assert hash(AccountId(7)) == hash(AccountId(7))
    assert len({AccountId(7), AccountId(7), AccountId(8)}) == 2


def test_entity_id_renders_its_value_as_text() -> None:
    assert str(AccountId(5)) == "5"


def test_entity_equality_follows_identity_not_attributes() -> None:
    first = Account(AccountId(1), "one")
    same_identity = Account(AccountId(1), "two")
    other = Account(AccountId(2), "one")

    assert first == first
    assert first == same_identity
    assert first != other
    assert first != object()


def test_entities_with_equal_identity_hash_equally() -> None:
    first = Account(AccountId(1), "one")
    same_identity = Account(AccountId(1), "two")

    assert hash(first) == hash(same_identity)
    assert len({first, same_identity}) == 1
