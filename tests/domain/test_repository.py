"""Tests for the aggregate repository contract."""

from __future__ import annotations

import asyncio
import inspect

import pytest

from fastddd.domain.aggregate import Aggregate
from fastddd.domain.entity import EntityId
from fastddd.domain.repository import AggregateRepository


class AccountId(EntityId[int]):
    """Identity of the sample aggregate."""

    def __init__(self, value: int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value


class Account(Aggregate[int]):
    """Sample aggregate stored through the repository."""

    def __init__(self, account_id: AccountId, name: str = "") -> None:
        super().__init__()
        self._account_id = account_id
        self.name = name

    @property
    def id(self) -> EntityId[int]:
        return self._account_id


class InMemoryAccounts(AggregateRepository[Account, int]):
    """Minimal concrete repository used to exercise the contract."""

    def __init__(self) -> None:
        self._by_id: dict[int, Account] = {}

    async def get(self, id: EntityId[int]) -> Account | None:
        await asyncio.sleep(0)
        return self._by_id.get(id.value)

    async def save(self, aggregate: Account) -> None:
        await asyncio.sleep(0)
        self._by_id[aggregate.id.value] = aggregate

    async def purge(self, id: EntityId[int]) -> None:
        await asyncio.sleep(0)
        self._by_id.pop(id.value, None)


def test_the_repository_contract_is_abstract() -> None:
    assert inspect.isabstract(AggregateRepository)


@pytest.mark.parametrize("method", ["get", "save", "purge"])
def test_every_repository_operation_is_asynchronous(method: str) -> None:
    assert inspect.iscoroutinefunction(getattr(AggregateRepository, method))


async def test_get_returns_none_when_nothing_is_stored() -> None:
    accounts = InMemoryAccounts()

    assert await accounts.get(AccountId(1)) is None


async def test_save_then_get_returns_the_aggregate() -> None:
    accounts = InMemoryAccounts()
    account = Account(AccountId(1))

    await accounts.save(account)

    assert await accounts.get(AccountId(1)) is account


async def test_get_uses_the_identity_and_not_the_instance() -> None:
    accounts = InMemoryAccounts()
    await accounts.save(Account(AccountId(1), "one"))

    assert await accounts.get(AccountId(2)) is None


async def test_saving_the_same_identity_again_replaces_the_state() -> None:
    accounts = InMemoryAccounts()
    await accounts.save(Account(AccountId(1), "one"))
    replacement = Account(AccountId(1), "two")

    await accounts.save(replacement)

    assert await accounts.get(AccountId(1)) is replacement


async def test_purge_removes_the_aggregate() -> None:
    accounts = InMemoryAccounts()
    await accounts.save(Account(AccountId(1)))

    await accounts.purge(AccountId(1))

    assert await accounts.get(AccountId(1)) is None


async def test_purging_an_absent_aggregate_is_a_no_op() -> None:
    accounts = InMemoryAccounts()

    await accounts.purge(AccountId(1))

    assert await accounts.get(AccountId(1)) is None
