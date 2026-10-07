"""Shared helper for the logging adapter tests."""

from __future__ import annotations

import logging
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from typing import Any

import structlog
from structlog.testing import LogCapture


@contextmanager
def captured_logs() -> Iterator[list[MutableMapping[str, Any]]]:
    """Collect log entries through the real processor chain, printing nothing.

    ``structlog.testing.capture_logs`` replaces the whole processor list, which
    would hide the context variables this package binds. This keeps the chain and
    swaps the renderer for a silent logger instead, so an entry looks like what a
    deployment would actually emit.
    """
    capture = LogCapture()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            capture,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG),
        logger_factory=structlog.ReturnLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    try:
        yield capture.entries
    finally:
        structlog.reset_defaults()
