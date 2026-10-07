"""Tests for the read-side store port."""

from __future__ import annotations

import inspect
from dataclasses import dataclass

from fastddd.application.ports.read_store import ReadStore


@dataclass(frozen=True, slots=True)
class GetAccount:
    """Sample read query."""

    account_id: int


class InMemoryReadStore(ReadStore[GetAccount, str]):
    """Concrete read store returning a projection."""

    async def query(self, query: GetAccount) -> str:
        return f"account-{query.account_id}"


def test_the_read_store_contract_is_abstract() -> None:
    assert inspect.isabstract(ReadStore)


async def test_a_read_store_returns_a_projection() -> None:
    assert await InMemoryReadStore().query(GetAccount(account_id=7)) == "account-7"
