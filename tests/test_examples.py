"""Tests that the example still describes the kernel it documents.

An example is code, so it is checked like code: Ruff and mypy cover it because it
lives in this repository, and this module proves the half they cannot -- that the
whole graph still assembles and that a command really does travel through the
outbox into a read model. When a kernel signature changes, this fails, instead of
a walkthrough quietly becoming fiction.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from importlib import import_module
from pathlib import Path
from uuid import uuid4

import pytest
from dependency_injector import providers
from fastapi import FastAPI
from pydantic import TypeAdapter

from examples.composition.bootstrap import create_app
from examples.composition.container import AppContainer
from examples.composition.wiring import AppState, build_state
from examples.counter.application import (
    CounterView,
    CreateCounter,
    GetCounter,
    IncrementCounter,
)
from examples.counter.domain import CounterNotFoundError
from examples.counter.interface import COUNTER_STATUS_TABLE
from fastddd.domain import InvariantViolationError
from fastddd.infrastructure import create_async_engine
from fastddd.infrastructure.persistence.sqlalchemy.models import Base
from fastddd.interface import (
    ResponseSchemaModel,
    register_domain_error_handler,
    status_for,
)

EXAMPLES_DIR = Path(__file__).resolve().parents[1] / "examples"
"""The example package, from the repository root rather than from the cwd."""


def _module_name(path: Path) -> str:
    """Return the import name of one example file."""
    relative = path.relative_to(EXAMPLES_DIR.parent).with_suffix("")

    return ".".join(part for part in relative.parts if part != "__init__")


def _example_modules() -> list[Path]:
    """Return every hand-written example module.

    A ``migrations`` tree is skipped on purpose: the example's ``db init`` writes
    it, Alembic owns its contents, and the module names there are filesystem-based
    by design.
    """
    return sorted(
        path
        for path in EXAMPLES_DIR.rglob("*.py")
        if "__pycache__" not in path.parts and "migrations" not in path.parts
    )


def test_the_example_has_modules_to_check() -> None:
    assert _example_modules() != []


def test_every_example_module_imports_and_documents_itself() -> None:
    undocumented = [
        _module_name(path)
        for path in _example_modules()
        if not (import_module(_module_name(path)).__doc__ or "").strip()
    ]

    assert undocumented == []


@pytest.fixture
async def container() -> AsyncIterator[AppContainer]:
    """Return the example's container over a throwaway database.

    Everything except the engine and the logging setup comes from the example's
    own configuration file, so the settings, the profiles and the database URL
    are the ones a deployment would read.
    """
    app_container = AppContainer()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    app_container.engine.override(providers.Object(engine))
    # Configuring logging is a process-wide side effect. The assembly under test
    # does not need it, and a test suite must not reconfigure its own output.
    app_container.logging_setup.override(providers.Object(None))

    try:
        yield app_container
    finally:
        await engine.dispose()


@pytest.fixture
def state(container: AppContainer) -> AppState:
    """Return the object graph assembled around the throwaway database."""
    return build_state(container)


def test_the_settings_come_from_the_examples_configuration_file(
    container: AppContainer,
) -> None:
    settings = container.settings()

    assert settings.database.provider == "sqlite"
    assert settings.api.prefix == "/api/v1"


def test_the_application_assembles_with_its_routes(container: AppContainer) -> None:
    # The schema is the contract a client reads, and asking for it is also what
    # proves the response models are valid: a route whose envelope cannot be
    # described raises here rather than at the first request.
    paths = create_app(container).openapi()["paths"]

    assert "/api/v1/counters" in paths
    assert "/api/v1/counters/{counter_id}" in paths
    assert "/api/v1/counters/{counter_id}/increments" in paths


def test_the_context_maps_its_failures_to_statuses() -> None:
    app = FastAPI()
    register_domain_error_handler(app, COUNTER_STATUS_TABLE)

    assert status_for(app, CounterNotFoundError("gone")) == 404
    assert status_for(app, InvariantViolationError("refused")) == 400


def test_the_response_envelope_carries_the_view() -> None:
    view = CounterView(counter_id=uuid4(), label="page views", total=3)
    envelope = TypeAdapter(ResponseSchemaModel[CounterView])

    rendered = envelope.dump_python(envelope.validate_python({"data": view}))

    assert rendered["code"] == 200
    assert rendered["data"] == {
        "counter_id": view.counter_id,
        "label": "page views",
        "total": 3,
    }


async def test_a_command_reaches_the_read_model_through_the_outbox(
    state: AppState,
) -> None:
    created = await state.message_bus.send(CreateCounter(label="page views"))
    assert created.total == 0
    assert await state.dispatcher.dispatch_once() == 1

    # The read model is built from events, so it answers only once the projection
    # has consumed the fact -- which is what eventual consistency means for a
    # caller that reads instead of writing.
    projected = await state.message_bus.ask(GetCounter(counter_id=created.counter_id))
    assert projected == created

    await state.message_bus.send(IncrementCounter(counter_id=created.counter_id, by=5))
    assert await state.dispatcher.dispatch_once() == 1

    advanced = await state.message_bus.ask(GetCounter(counter_id=created.counter_id))
    assert advanced.total == 5


async def test_a_missing_counter_is_reported_as_not_found(state: AppState) -> None:
    with pytest.raises(CounterNotFoundError):
        await state.message_bus.ask(GetCounter(counter_id=uuid4()))


async def test_an_aggregate_that_refuses_a_command_rolls_the_transaction_back(
    state: AppState,
) -> None:
    created = await state.message_bus.send(CreateCounter(label="page views"))

    with pytest.raises(InvariantViolationError):
        await state.message_bus.send(
            IncrementCounter(counter_id=created.counter_id, by=0)
        )

    # The refusal left nothing behind: no published fact, so no new delivery.
    assert await state.dispatcher.dispatch_once() == 1
