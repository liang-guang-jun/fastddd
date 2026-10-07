"""Tests for logging configuration, context binding, and console rendering."""

from __future__ import annotations

import logging
import re
from typing import cast

import pytest
import structlog

from fastddd.infrastructure.configuration.schemas import LoggingConfig
from fastddd.infrastructure.logging import (
    bind_context,
    configure_logging,
    get_logger,
)
from fastddd.infrastructure.logging.logger import (
    _attribute,
    _console_renderer,
    _log_level,
    _prefix,
    _SilencedLoggerFilter,
)
from tests.infrastructure.logging._helpers import captured_logs


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("debug", logging.DEBUG),
        ("INFO", logging.INFO),
        ("Warning", logging.WARNING),
        ("error", logging.ERROR),
        ("critical", logging.CRITICAL),
    ],
)
def test_an_approved_level_name_resolves_whatever_its_case(
    name: str, expected: int
) -> None:
    assert _log_level(name) == expected


def test_an_unknown_level_is_refused() -> None:
    with pytest.raises(ValueError, match="Unknown logging level: chatty"):
        _log_level("chatty")


def test_plain_output_is_rendered_for_a_person_to_read() -> None:
    configure_logging(LoggingConfig(level="INFO"))
    renderer = structlog.get_config()["processors"][-1]

    line = renderer(None, "info", {"event": "started", "name": "app"})

    assert re.fullmatch(
        r"\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\]\[INFO\]\[app\] started", line
    )


def test_json_output_is_selected_when_it_is_asked_for() -> None:
    configure_logging(LoggingConfig(level="INFO", json_output=True))

    renderer = structlog.get_config()["processors"][-1]

    assert isinstance(renderer, structlog.processors.JSONRenderer)


def test_the_configuration_sets_the_root_logger_level() -> None:
    configure_logging(LoggingConfig(level="WARNING"))

    assert logging.getLogger().level == logging.WARNING


@pytest.mark.parametrize(
    ("prefix", "logger_name", "kept"),
    [
        ("sqlalchemy", "sqlalchemy", False),
        ("sqlalchemy", "sqlalchemy.engine.Engine", False),
        ("sqlalchemy", "sqlalchemyx", True),
        ("sqlalchemy", "app", True),
    ],
)
def test_a_silenced_prefix_hides_its_logger_and_its_children(
    prefix: str, logger_name: str, kept: bool
) -> None:
    record = logging.LogRecord(
        logger_name, logging.WARNING, "test", 1, "msg", None, None
    )

    assert _SilencedLoggerFilter([prefix]).filter(record) is kept


def test_configuring_installs_the_filter_on_every_root_handler() -> None:
    configure_logging(LoggingConfig(level="INFO", silenced_loggers=["noisy"]))
    record = logging.LogRecord(
        "noisy.child", logging.INFO, "test", 1, "msg", None, None
    )

    handlers = logging.getLogger().handlers

    assert handlers
    assert all(not handler.filter(record) for handler in handlers)


def test_a_logger_carries_the_name_it_was_given() -> None:
    with captured_logs() as entries:
        get_logger("server.message").info("started")

    assert entries[0]["name"] == "server.message"
    assert entries[0]["event"] == "started"


def test_a_logger_without_a_name_is_the_root_logger() -> None:
    with captured_logs() as entries:
        get_logger().info("started")

    assert entries[0]["name"] == "root"


def test_binding_drops_null_values_and_restores_the_context_afterward() -> None:
    with bind_context(tenant_id="tenant-1", correlation_id=None):
        assert structlog.contextvars.get_contextvars() == {"tenant_id": "tenant-1"}

    assert structlog.contextvars.get_contextvars() == {}


def test_a_bound_value_reaches_the_log_entry() -> None:
    with captured_logs() as entries:
        with bind_context(tenant_id="tenant-1"):
            get_logger("app").info("started")

    assert entries[0]["tenant_id"] == "tenant-1"


def test_a_plain_prefix_names_the_moment_the_level_and_the_logger() -> None:
    assert (
        _prefix("2026-01-01 00:00:00", "INFO", "app", colors=False)
        == "[2026-01-01 00:00:00][INFO][app]"
    )


def test_a_colored_prefix_colors_each_segment() -> None:
    prefix = _prefix("12:00:00", "WARNING", "app", colors=True)

    assert prefix.startswith("\x1b[90m[12:00:00]\x1b[0m")
    assert "\x1b[33m[WARNING]\x1b[0m" in prefix
    assert prefix.endswith("\x1b[35m[app]\x1b[0m")


def test_a_level_the_console_does_not_know_is_colored_as_info() -> None:
    assert "\x1b[32m[NOTSET]\x1b[0m" in _prefix("ts", "NOTSET", "app", colors=True)


def test_an_attribute_is_rendered_with_or_without_colors() -> None:
    assert _attribute("count", 3, colors=False) == "count=3"
    assert _attribute("count", 3, colors=True) == "\x1b[33mcount\x1b[0m=3"


def test_a_console_line_lists_its_attributes_in_a_stable_order() -> None:
    render = _console_renderer(colors=False)

    line = cast(
        str,
        render(
            None,
            "info",
            {"event": "started", "name": "app", "total": 2, "label": "acme"},
        ),
    )

    assert line.endswith("started  label='acme' total=2")


def test_a_console_line_without_attributes_stops_after_the_event() -> None:
    render = _console_renderer(colors=False)

    assert cast(str, render(None, "info", {"event": "started"})).endswith("] started")


def test_a_console_line_prefers_the_logger_name_over_the_bound_one() -> None:
    render = _console_renderer(colors=False)

    line = render(None, "info", {"event": "started", "logger": "app", "name": "cloud"})

    assert "[app]" in line
    assert "name=" not in line
