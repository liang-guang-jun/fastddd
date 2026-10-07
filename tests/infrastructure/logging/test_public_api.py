"""Tests for the logging adapter's public surface."""

from __future__ import annotations

import fastddd.infrastructure.logging as logging_adapter
from fastddd.infrastructure.logging.behavior import LoggingBehavior
from fastddd.infrastructure.logging.logger import (
    bind_context,
    configure_logging,
    get_logger,
)

EXPECTED = {"LoggingBehavior", "bind_context", "configure_logging", "get_logger"}


def test_the_surface_is_exactly_what_the_package_publishes() -> None:
    assert set(logging_adapter.__all__) == EXPECTED


def test_every_exported_name_resolves_to_an_attribute() -> None:
    for name in logging_adapter.__all__:
        assert getattr(logging_adapter, name) is not None


def test_every_exported_name_is_the_object_its_module_defines() -> None:
    assert logging_adapter.LoggingBehavior is LoggingBehavior
    assert logging_adapter.bind_context is bind_context
    assert logging_adapter.configure_logging is configure_logging
    assert logging_adapter.get_logger is get_logger
