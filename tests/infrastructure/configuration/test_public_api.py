"""Tests for the public surface of the configuration package."""

from __future__ import annotations

from importlib import import_module

import fastddd.infrastructure.configuration as configuration


def test_the_public_surface_has_no_duplicates() -> None:
    assert len(configuration.__all__) == len(set(configuration.__all__))


def test_every_exported_name_resolves_to_an_attribute() -> None:
    missing = [
        name for name in configuration.__all__ if not hasattr(configuration, name)
    ]

    assert missing == []


def test_the_resolver_is_the_entry_point_of_the_package() -> None:
    assert "ConfigResolver" in configuration.__all__


def test_no_module_level_helper_leaks_into_the_surface() -> None:
    assert not [name for name in configuration.__all__ if name.islower()]


def test_exports_are_the_objects_their_modules_define() -> None:
    resolver = import_module("fastddd.infrastructure.configuration.resolver")
    schemas = import_module("fastddd.infrastructure.configuration.schemas")

    assert configuration.ConfigResolver is resolver.ConfigResolver
    assert configuration.ConfigError is resolver.ConfigError
    assert configuration.AppConfig is schemas.AppConfig
    assert configuration.ProfileConfig is schemas.ProfileConfig
