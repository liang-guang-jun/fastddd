"""Tests for the public surface of the cli package."""

from __future__ import annotations

from importlib import import_module

import fastddd.interface.cli as cli

EXPECTED = {
    "DbEnvironment",
    "ScaffoldResult",
    "alembic_config",
    "apply_migrations",
    "create_db_app",
    "next_revision_id",
    "scaffold_environment",
}


def test_the_surface_is_exactly_what_the_package_publishes() -> None:
    assert set(cli.__all__) == EXPECTED


def test_every_exported_name_resolves_to_an_attribute() -> None:
    for name in cli.__all__:
        assert getattr(cli, name) is not None


def test_the_unrendered_templates_stay_out_of_the_surface() -> None:
    assert not [name for name in cli.__all__ if name.isupper()]


def test_every_exported_name_is_the_object_its_module_defines() -> None:
    db = import_module("fastddd.interface.cli.db")
    scaffold = import_module("fastddd.interface.cli.scaffold")

    assert cli.create_db_app is db.create_db_app
    assert cli.DbEnvironment is db.DbEnvironment
    assert cli.alembic_config is db.alembic_config
    assert cli.apply_migrations is db.apply_migrations
    assert cli.next_revision_id is db.next_revision_id
    assert cli.scaffold_environment is scaffold.scaffold_environment
    assert cli.ScaffoldResult is scaffold.ScaffoldResult
