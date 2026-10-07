"""Tests for the public surface of the persistence package."""

from __future__ import annotations

from importlib import import_module

import fastddd.infrastructure.persistence as persistence


def test_the_public_surface_has_no_duplicates() -> None:
    assert len(persistence.__all__) == len(set(persistence.__all__))


def test_every_exported_name_resolves_to_an_attribute() -> None:
    missing = [name for name in persistence.__all__ if not hasattr(persistence, name)]

    assert missing == []


def test_the_only_engine_adapter_is_re_exported_whole() -> None:
    sqlalchemy = import_module("fastddd.infrastructure.persistence.sqlalchemy")

    assert sorted(persistence.__all__) == sorted(sqlalchemy.__all__)


def test_exports_are_the_objects_their_modules_define() -> None:
    sqlalchemy = import_module("fastddd.infrastructure.persistence.sqlalchemy")

    assert persistence.SqlAlchemyUnitOfWork is sqlalchemy.SqlAlchemyUnitOfWork
    assert persistence.SqlAlchemyOutbox is sqlalchemy.SqlAlchemyOutbox
    assert persistence.create_async_engine is sqlalchemy.create_async_engine
    assert persistence.create_session_factory is sqlalchemy.create_session_factory
