"""Tests for the message-lifecycle logging behavior."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from fastddd.application.execution.context import Context, MessageMetadata
from fastddd.application.messaging.message import Command
from fastddd.infrastructure.logging import LoggingBehavior
from tests.infrastructure.logging._helpers import captured_logs


class _Ping(Command[str]):
    """A command whose execution the behavior logs."""


def _metadata() -> MessageMetadata:
    """Return the metadata a caller would have bound."""
    return MessageMetadata(
        message_id="message-1",
        correlation_id="correlation-1",
        causation_id="causation-1",
        principal_id="principal-1",
        tenant_id="tenant-1",
        occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


async def _succeeds(message: Command[str]) -> str:
    return "done"


def _behavior(name: str = "server.message") -> LoggingBehavior[Command[str], str]:
    """Return the behavior under test, typed for the command it logs."""
    return LoggingBehavior(name)


async def test_a_successful_execution_logs_its_start_and_its_outcome() -> None:
    with captured_logs() as entries:
        result = await _behavior().handle(_Ping(), _succeeds)

    assert result == "done"
    assert [entry["event"] for entry in entries] == [
        "message.started",
        "message.finished",
    ]
    assert entries[0]["message_type"].endswith("._Ping")
    assert entries[1]["success"] is True
    assert isinstance(entries[1]["duration_ms"], float)


async def test_a_failing_execution_is_logged_and_still_propagates() -> None:
    async def fails(message: Command[str]) -> str:
        raise RuntimeError("boom")

    with captured_logs() as entries:
        with pytest.raises(RuntimeError, match="boom"):
            await _behavior().handle(_Ping(), fails)

    assert entries[-1]["event"] == "message.finished"
    assert entries[-1]["success"] is False


async def test_the_message_metadata_is_bound_into_the_log_context() -> None:
    with captured_logs() as entries:
        async with Context(_metadata()):
            await _behavior().handle(_Ping(), _succeeds)

    assert entries[0]["message_id"] == "message-1"
    assert entries[0]["correlation_id"] == "correlation-1"
    assert entries[0]["causation_id"] == "causation-1"
    assert entries[0]["principal_id"] == "principal-1"
    assert entries[0]["tenant_id"] == "tenant-1"


async def test_without_a_scope_no_metadata_is_bound() -> None:
    with captured_logs() as entries:
        await _behavior().handle(_Ping(), _succeeds)

    assert "message_id" not in entries[0]
    assert "correlation_id" not in entries[0]


async def test_the_bound_metadata_does_not_leak_past_the_message() -> None:
    with captured_logs() as entries:
        async with Context(_metadata()):
            await _behavior().handle(_Ping(), _succeeds)
        await _behavior().handle(_Ping(), _succeeds)

    assert entries[0]["correlation_id"] == "correlation-1"
    assert "correlation_id" not in entries[-1]


async def test_the_behavior_logs_under_the_name_it_was_given() -> None:
    with captured_logs() as entries:
        await _behavior("acme.messages").handle(_Ping(), _succeeds)

    assert entries[0]["name"] == "acme.messages"
