"""Tests for the domain error hierarchy."""

from __future__ import annotations

import pytest

from fastddd.domain.error import (
    AggregateDeletedError,
    AuthenticationRequiredError,
    AuthorizationDeniedError,
    BusinessRuleViolationError,
    ConflictError,
    DomainError,
    InvariantViolationError,
    NotFoundError,
)

CONCRETE_ERRORS: list[type[DomainError]] = [
    InvariantViolationError,
    BusinessRuleViolationError,
    AggregateDeletedError,
    NotFoundError,
    ConflictError,
    AuthenticationRequiredError,
    AuthorizationDeniedError,
]


@pytest.mark.parametrize("error_type", CONCRETE_ERRORS)
def test_every_domain_error_is_a_domain_error_and_an_exception(
    error_type: type[DomainError],
) -> None:
    assert issubclass(error_type, DomainError)
    assert issubclass(error_type, Exception)


def test_a_deleted_aggregate_is_a_business_rule_violation() -> None:
    assert issubclass(AggregateDeletedError, BusinessRuleViolationError)


def test_a_domain_error_carries_no_code_by_default() -> None:
    assert DomainError.code is None
    assert InvariantViolationError("broken").code is None


def test_a_subclass_can_name_the_code_it_travels_under() -> None:
    class StaleWriteError(DomainError):
        """A failure a caller can single out by its code."""

        code = "stale_write"

    assert StaleWriteError.code == "stale_write"


def test_authorization_denied_keeps_the_detail_and_the_reason() -> None:
    error = AuthorizationDeniedError("no grant", reason="missing_grant")

    assert str(error) == "no grant"
    assert error.reason == "missing_grant"
    assert isinstance(error, DomainError)
