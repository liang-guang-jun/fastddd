"""Tests for the public surface of the application package."""

from __future__ import annotations

from importlib import import_module

import fastddd.application as application


def test_the_public_surface_has_no_duplicates() -> None:
    assert len(application.__all__) == len(set(application.__all__))


def test_every_exported_name_resolves_to_an_attribute() -> None:
    missing = [name for name in application.__all__ if not hasattr(application, name)]

    assert missing == []


def test_the_repository_abstraction_is_owned_by_the_domain() -> None:
    assert "AggregateRepository" not in application.__all__


def test_exports_are_the_objects_their_subpackages_define() -> None:
    messaging = import_module("fastddd.application.messaging")
    execution = import_module("fastddd.application.execution")
    integration = import_module("fastddd.application.integration")
    ports = import_module("fastddd.application.ports")
    support = import_module("fastddd.application.support")

    assert application.MessageBus is messaging.MessageBus
    assert application.Context is execution.Context
    assert application.UnitOfWork is ports.UnitOfWork
    assert application.IntegrationEvent is integration.IntegrationEvent
    assert application.DomainEventMapper is integration.DomainEventMapper
    assert application.ReadStore is ports.ReadStore
    assert application.require_found is support.require_found


def test_the_ambient_readers_are_reachable_from_the_facade() -> None:
    # A command handler, a read-model projection and the transaction behavior all
    # reach the current transaction through these readers, so they have to be
    # nameable from the layer instead of from `application.execution.context`.
    execution = import_module("fastddd.application.execution")

    assert application.current_context is execution.current_context
    assert application.current_context_or_none is execution.current_context_or_none
    assert application.current_metadata is execution.current_metadata
    assert application.current_unit_of_work is execution.current_unit_of_work
    assert (
        application.current_unit_of_work_or_none
        is execution.current_unit_of_work_or_none
    )
