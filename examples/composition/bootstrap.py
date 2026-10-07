"""The process: an ASGI application whose lifespan owns the background worker.

Everything that has a beginning and an end is here. The outbox is durable but
inert -- something has to ask a dispatcher to publish -- so the worker starts
with the process, and the engine is released on the way out instead of being
abandoned to the garbage collector.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from fastddd.infrastructure import get_logger
from fastddd.interface import (
    RequestLoggingMiddleware,
    register_domain_error_handler,
)

from ..counter.interface import COUNTER_STATUS_TABLE, create_counter_router
from .container import AppContainer
from .wiring import AppState, build_state


def create_app(
    container: AppContainer | None = None,
    *,
    api_prefix: str | None = None,
) -> FastAPI:
    """Build the ASGI application around an assembled object graph.

    The container is an argument so a test can override providers -- a frozen
    clock, a stub identifier source, a throwaway database -- *before* anything is
    resolved. Without that seam a composition root is only testable end to end,
    through the network.
    """
    container = container or AppContainer()
    container.logging_setup()
    settings = container.settings()
    state = build_state(container)
    prefix = api_prefix or settings.api.prefix
    logger = get_logger("example")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Start the outbox worker, and release the engine on the way out."""
        state.worker.start()
        logger.info("service.started", api_prefix=prefix)
        try:
            yield
        finally:
            await state.worker.stop()
            await container.engine().dispose()
            logger.info("service.stopped")

    app = FastAPI(title="counter service", lifespan=lifespan)
    app.add_middleware(RequestLoggingMiddleware)
    # One handler per application, and each context contributes the statuses its
    # own failures travel under. Registering twice would install a second handler
    # for the same error type, so this call is idempotent by design.
    register_domain_error_handler(app, COUNTER_STATUS_TABLE)
    app.include_router(create_counter_router(state.message_bus), prefix=prefix)

    return app


def create_state(container: AppContainer | None = None) -> AppState:
    """Assemble the object graph for a script that needs no HTTP application."""
    return build_state(container or AppContainer())
