"""The container: what the process is built from, and how long each piece lives.

The container owns *lifetimes*. Which object needs which is decided in
``wiring.py``, and the split is deliberate: several kernel seams take a *callable*
that builds a fresh object -- a unit-of-work factory, a consumer's factory -- and
passing a provider where a callable is expected is exactly the indirection a
composition root exists to make visible.

Nothing here is invented. The kernel reads no file, no environment variable and
no project layout on its own, so every path, schema and name this process needs
appears in this file: the configuration directory, the profiles, the settings
class, and the entry point names.
"""

from __future__ import annotations

from pathlib import Path

from dependency_injector import containers, providers
from sqlalchemy.ext.asyncio import AsyncEngine

from fastddd.infrastructure import (
    AppConfig,
    ConfigResolver,
    DatabaseBackend,
    DatabaseConfig,
    ProfileConfig,
    SqlAlchemyMaintenance,
    SqlAlchemyUnitOfWork,
    SystemClock,
    UuidGenerator,
    configure_logging,
    create_database_backend,
    create_session_factory,
)

from ..counter.application import CounterEventMapper
from ..counter.persistence import CounterReadStore, CounterRepository

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
"""Where this service's layered configuration lives.

Resolved from this file instead of from the working directory, so the example
behaves the same whether it is started from the repository root or from
anywhere else. A path the *process* is told about is one the process should
resolve itself.
"""

PROFILES = (
    # A profile named "base" reads config.base.yaml inside that directory.
    ProfileConfig(name="base"),
    # A larger priority wins, and a file that does not exist is simply skipped,
    # so a deployment ships only the layers it actually needs.
    ProfileConfig(name="local", priority=10),
)


class ServiceConfig(AppConfig):
    """This service's own configuration root.

    The kernel's ``AppConfig`` carries what *every* service declares. A service
    that needs more composes its own root from the kernel's models and hands that
    to the resolver, which is what keeps "we added a database section" from being
    a kernel change.
    """

    database: DatabaseConfig


def _resolve_settings() -> ServiceConfig:
    """Merge the configuration files into one validated settings object."""
    return ConfigResolver(CONFIG_DIR, PROFILES, ServiceConfig).resolve()


def _database_backend(settings: ServiceConfig) -> DatabaseBackend:
    """Select the one provider-specific branch the configuration names."""
    return create_database_backend(settings.database)


def _database_engine(backend: DatabaseBackend) -> AsyncEngine:
    """Open the engine the backend describes.

    The engine comes from the same object that built the URL, so the credentials
    a connection needs are the ones that object read -- for Lakebase, a token
    minted per connection.
    """
    return backend.create_engine()


def _logging_setup(settings: ServiceConfig) -> None:
    """Configure structured logging once, from the settings."""
    configure_logging(settings.logging)


class AppContainer(containers.DeclarativeContainer):
    """Every object this process is built from.

    Process-lifetime objects are singletons. Anything holding a transaction is a
    factory, because a ``SqlAlchemyUnitOfWork`` binds exactly one transaction and
    a shared one would serialise every concurrent command behind it.
    """

    # --- configuration and logging -------------------------------------------
    settings = providers.Singleton(_resolve_settings)
    logging_setup = providers.Callable(_logging_setup, settings)

    # --- database ------------------------------------------------------------
    database = providers.Singleton(_database_backend, settings)
    engine = providers.Singleton(_database_engine, database)
    session_factory = providers.Singleton(create_session_factory, engine)

    # --- one transaction per dispatch, never a shared one ---------------------
    # The factory is handed over as a callable to whoever needs a transaction,
    # and calling it is what gives each command its own.
    uow = providers.Factory(SqlAlchemyUnitOfWork, session_factory, now=SystemClock.now)

    # --- the application's own ports, implemented by this layer ---------------
    clock = providers.Singleton(SystemClock)
    identifiers = providers.Singleton(UuidGenerator)

    # --- the counter context --------------------------------------------------
    counter_repository = providers.Singleton(CounterRepository)
    counter_read_model = providers.Factory(CounterReadStore, session_factory)
    counter_event_mapper = providers.Singleton(
        CounterEventMapper, clock=clock, identifiers=identifiers
    )

    # --- retention ------------------------------------------------------------
    maintenance = providers.Singleton(SqlAlchemyMaintenance, session_factory)
