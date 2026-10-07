"""Tests for the public surface of the interface package."""

from __future__ import annotations

from importlib import import_module

import fastddd.interface as interface

DRIVERS = ("cli", "http")


def test_the_public_surface_has_no_duplicates() -> None:
    assert len(interface.__all__) == len(set(interface.__all__))


def test_every_exported_name_resolves_to_an_attribute() -> None:
    missing = [name for name in interface.__all__ if not hasattr(interface, name)]

    assert missing == []


def test_the_surface_is_what_the_drivers_publish() -> None:
    published: set[str] = set()
    for driver in DRIVERS:
        module = import_module(f"fastddd.interface.{driver}")
        published |= set(module.__all__)

    assert set(interface.__all__) == published


def test_exports_are_the_objects_their_modules_define() -> None:
    cli = import_module("fastddd.interface.cli")
    http = import_module("fastddd.interface.http")
    error = import_module("fastddd.interface.http.error")

    assert interface.create_db_app is cli.create_db_app
    assert interface.scaffold_environment is cli.scaffold_environment
    assert (
        interface.register_domain_error_handler is error.register_domain_error_handler
    )
    assert interface.StandardResponseCode is http.StandardResponseCode
    assert interface.RequestLoggingMiddleware is http.RequestLoggingMiddleware
