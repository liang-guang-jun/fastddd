"""Application logging setup, context binding, and named logger access."""

from __future__ import annotations

import logging
from collections.abc import Generator, Mapping, Sequence
from contextlib import contextmanager
from typing import Any, cast

import structlog

from ..clock import SystemClock
from ..configuration.schemas import LoggingConfig

_LEVEL_COLORS = {
    "critical": "\x1b[1;97;41m",
    "error": "\x1b[31m",
    "warning": "\x1b[33m",
    "info": "\x1b[32m",
    "debug": "\x1b[36m",
}
_RESET = "\x1b[0m"
_TIMESTAMP_COLOR = "\x1b[90m"
_NAME_COLOR = "\x1b[35m"
_KEY_COLOR = "\x1b[33m"


class _SilencedLoggerFilter(logging.Filter):
    """Drop stdlib records whose logger name matches a configured prefix."""

    def __init__(self, prefixes: Sequence[str]) -> None:
        """Store normalized logger-name prefixes configured for suppression."""
        super().__init__()
        self._prefixes = prefixes

    def filter(self, record: logging.LogRecord) -> bool:
        """Allow records unless their logger is the configured prefix or child."""
        return not any(
            record.name == prefix or record.name.startswith(f"{prefix}.")
            for prefix in self._prefixes
        )


def configure_logging(config: LoggingConfig) -> None:
    """Configure structlog and standard-library logger suppression once per process."""
    level = _log_level(config.level)
    logging.basicConfig(level=level, format="%(message)s", force=True)
    root_logger = logging.getLogger()
    silenced_filter = _SilencedLoggerFilter(config.silenced_loggers)
    for handler in root_logger.handlers:
        handler.addFilter(silenced_filter)

    renderer: structlog.types.Processor
    if config.json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = _console_renderer(colors=config.colors)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.format_exc_info,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        # No explicit file: structlog then binds the stream that stdout refers to
        # when a logger is built rather than the one that happened to be in place
        # here, so a replaced stdout never leaves loggers writing to a dead stream.
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    """Return a named structlog logger enriched by current context variables."""
    logger = structlog.get_logger()
    return cast(
        structlog.stdlib.BoundLogger,
        logger.bind(name=name or "root"),
    )


@contextmanager
def bind_context(**values: Any) -> Generator[None]:
    """Bind non-null values for the current task without leaking them afterward."""
    with structlog.contextvars.bound_contextvars(
        **{key: value for key, value in values.items() if value is not None}
    ):
        yield


def _log_level(level: str) -> int:
    """Resolve an approved level name or reject invalid startup configuration."""
    resolved = logging.getLevelName(level.upper())
    if not isinstance(resolved, int):
        raise ValueError(f"Unknown logging level: {level}")
    return resolved


def _console_renderer(*, colors: bool) -> structlog.types.Processor:
    """Render `[timestamp][level][name] message key=value` at second precision."""

    def render(_: Any, __: str, event_dict: Mapping[str, Any]) -> str:
        mutable = dict(event_dict)
        event = str(mutable.pop("event", ""))
        level = str(mutable.pop("level", "info")).upper()
        name = str(mutable.pop("logger", mutable.pop("name", "root")))
        timestamp = SystemClock.now().strftime("%Y-%m-%d %H:%M:%S")
        prefix = _prefix(timestamp, level, name, colors)
        attributes = " ".join(
            _attribute(key, value, colors) for key, value in sorted(mutable.items())
        )
        return f"{prefix} {event}{f'  {attributes}' if attributes else ''}"

    return render


def _prefix(timestamp: str, level: str, name: str, colors: bool) -> str:
    """Produce independently colored timestamp, level, and logger-name segments."""
    if not colors:
        return f"[{timestamp}][{level}][{name}]"
    level_color = _LEVEL_COLORS.get(level.lower(), _LEVEL_COLORS["info"])
    return (
        f"{_TIMESTAMP_COLOR}[{timestamp}]{_RESET}"
        f"{level_color}[{level}]{_RESET}"
        f"{_NAME_COLOR}[{name}]{_RESET}"
    )


def _attribute(key: str, value: Any, colors: bool) -> str:
    """Render a log attribute, giving its key a distinct console color."""
    rendered = f"{key}={value!r}"
    return f"{_KEY_COLOR}{key}{_RESET}={value!r}" if colors else rendered
