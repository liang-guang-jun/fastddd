"""Tests for aggregate roots, versioning and soft deletion."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from fastddd.domain.aggregate import Aggregate, SoftDeletable, VersionedAggregate
from fastddd.domain.entity import EntityId
from fastddd.domain.error import AggregateDeletedError, BusinessRuleViolationError
from fastddd.domain.event import DomainEvent


@dataclass(frozen=True, slots=True)
class Renamed(DomainEvent):
    """Domain event recorded by the sample aggregate."""

    name: str


class AccountId(EntityId[int]):
    """Identity of the sample aggregate."""

    def __init__(self, value: int) -> None:
        self._value = value

    @property
    def value(self) -> int:
        return self._value


class Account(Aggregate[int]):
    """Sample aggregate recording an event on every rename."""

    def __init__(self, account_id: AccountId, name: str = "") -> None:
        super().__init__()
        self._account_id = account_id
        self.name = name

    @property
    def id(self) -> EntityId[int]:
        return self._account_id

    def rename(self, name: str) -> None:
        """Rename the account, recording the fact."""
        self.name = name
        self._record_event(Renamed(name=name))


class VersionedAccount(VersionedAggregate[int]):
    """Sample versioned aggregate exposing its bookkeeping."""

    def __init__(self, account_id: AccountId, *, version: int = 0) -> None:
        super().__init__(version=version)
        self._account_id = account_id

    @property
    def id(self) -> EntityId[int]:
        return self._account_id

    def rename(self, name: str) -> None:
        """Rename the account as a versioned state change."""
        self._record_state_change(Renamed(name=name))


class DeletionLog(SoftDeletable):
    """Minimal mixin user that counts how often deletion ran."""

    def __init__(self) -> None:
        self.deletions = 0

    def _on_deleted(self, at: datetime) -> None:
        """Count the deletion."""
        self.deletions += 1


def test_the_aggregate_base_is_abstract() -> None:
    assert inspect.isabstract(Aggregate)


def test_soft_deletable_requires_a_deletion_hook() -> None:
    assert inspect.isabstract(SoftDeletable)


def test_recording_then_pulling_events_drains_exactly_once() -> None:
    account = Account(AccountId(1), "old")

    account.rename("new")

    assert account.pull_events() == [Renamed(name="new")]
    assert account.pull_events() == []


def test_pulling_events_returns_a_fresh_list_each_time() -> None:
    account = Account(AccountId(1))

    first = account.pull_events()
    second = account.pull_events()

    assert first == []
    assert second == []
    assert first is not second


def test_an_aggregate_deletion_records_no_extra_bookkeeping() -> None:
    account = Account(AccountId(1))
    moment = datetime(2026, 1, 1, tzinfo=UTC)

    account.delete(at=moment)

    assert account.is_deleted
    assert account.deleted_at == moment
    assert account.pull_events() == []


def test_deleting_twice_keeps_the_first_moment_only() -> None:
    log = DeletionLog()
    moment = datetime(2026, 1, 1, tzinfo=UTC)

    log.delete(at=moment)
    log.delete(at=moment + timedelta(hours=1))

    assert log.deleted_at == moment
    assert log.deletions == 1


def test_a_live_object_allows_changes() -> None:
    DeletionLog()._require_not_deleted(action="change")


def test_a_deleted_object_rejects_changes() -> None:
    log = DeletionLog()
    log.delete(at=datetime(2026, 1, 1, tzinfo=UTC))

    with pytest.raises(AggregateDeletedError, match="DeletionLog is deleted"):
        log._require_not_deleted(action="change")


def test_a_deleted_error_is_a_business_rule_violation() -> None:
    assert issubclass(AggregateDeletedError, BusinessRuleViolationError)


def test_a_versioned_aggregate_starts_at_the_given_version() -> None:
    assert VersionedAccount(AccountId(1)).version == 0
    assert VersionedAccount(AccountId(1), version=3).version == 3


def test_a_state_change_advances_the_version_and_keeps_the_event() -> None:
    account = VersionedAccount(AccountId(1))

    account.rename("new")

    assert account.version == 1
    assert account.pull_events() == [Renamed(name="new")]


def test_restoring_a_version_sets_it_without_recording_an_event() -> None:
    account = VersionedAccount(AccountId(1))

    account._restore_version(7)

    assert account.version == 7
    assert account.pull_events() == []


def test_restoring_a_negative_version_is_refused() -> None:
    account = VersionedAccount(AccountId(1))

    with pytest.raises(ValueError, match="version must be non-negative"):
        account._restore_version(-1)
