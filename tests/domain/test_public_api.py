"""Tests for the public surface of the domain package."""

from __future__ import annotations

from importlib import import_module

import fastddd.domain as domain


def test_the_public_surface_has_no_duplicates() -> None:
    assert len(domain.__all__) == len(set(domain.__all__))


def test_every_exported_name_resolves_to_an_attribute() -> None:
    missing = [name for name in domain.__all__ if not hasattr(domain, name)]

    assert missing == []


def test_exports_are_the_objects_their_modules_define() -> None:
    aggregate = import_module("fastddd.domain.aggregate")
    entity = import_module("fastddd.domain.entity")
    pagination = import_module("fastddd.domain.pagination")
    repository = import_module("fastddd.domain.repository")

    assert domain.Aggregate is aggregate.Aggregate
    assert domain.SoftDeletable is aggregate.SoftDeletable
    assert domain.Entity is entity.Entity
    assert domain.PageRequest is pagination.PageRequest
    assert domain.AggregateRepository is repository.AggregateRepository


def test_the_error_vocabulary_the_other_layers_ask_for_is_reachable() -> None:
    # `application.support.require_found` is typed against `NotFoundError`, and
    # `ConflictError` is what an optimistic-locking failure raises, so both have to
    # be nameable from the facade rather than from the module path.
    error = import_module("fastddd.domain.error")

    assert domain.NotFoundError is error.NotFoundError
    assert domain.ConflictError is error.ConflictError
    assert domain.AuthenticationRequiredError is error.AuthenticationRequiredError
    assert domain.AuthorizationDeniedError is error.AuthorizationDeniedError
