"""Adapters for databases, messaging, logging, configuration, and the clock.

Each concern owns a child package that publishes its own surface, and this
package re-exports all of them so a composition root can name every adapter
from one import. ``clock`` and ``identity`` are the two implementations the
application's own ports need, and ``inbox`` is the idempotent-consumption
primitive the messaging adapters reuse.
"""

from .clock import SystemClock
from .configuration import (
    ApiConfig,
    AppConfig,
    ConfigError,
    ConfigResolver,
    CorsConfig,
    DatabaseConfig,
    DatabaseOptionsConfig,
    DatabasePasswordAuthConfig,
    DatabasePoolConfig,
    LoggingConfig,
    ProfileConfig,
    StrictModel,
)
from .identity import UuidGenerator
from .inbox import InboxConsumer, claim_inbox_message, projection_consumer
from .logging import LoggingBehavior, bind_context, configure_logging, get_logger
from .messaging import (
    Dispatcher,
    InMemoryIntegrationEventPublisher,
    OutboxDispatcher,
    OutboxWorker,
    TransactionBehavior,
)
from .persistence import (
    AggregateRecordMapper,
    DatabaseBackend,
    DatabaseConfigurationError,
    DatabricksLakebaseCredentialProvider,
    SqlAlchemyAggregateRepository,
    SqlAlchemyMaintenance,
    SqlAlchemyMappedRepository,
    SqlAlchemyOutbox,
    SqlAlchemyUnitOfWork,
    create_async_engine,
    create_database_backend,
    create_session_factory,
)

__all__ = [
    "AggregateRecordMapper",
    "ApiConfig",
    "AppConfig",
    "ConfigError",
    "ConfigResolver",
    "CorsConfig",
    "DatabaseBackend",
    "DatabaseConfig",
    "DatabaseConfigurationError",
    "DatabaseOptionsConfig",
    "DatabasePasswordAuthConfig",
    "DatabasePoolConfig",
    "DatabricksLakebaseCredentialProvider",
    "Dispatcher",
    "InMemoryIntegrationEventPublisher",
    "InboxConsumer",
    "LoggingBehavior",
    "LoggingConfig",
    "OutboxDispatcher",
    "OutboxWorker",
    "ProfileConfig",
    "SqlAlchemyAggregateRepository",
    "SqlAlchemyMaintenance",
    "SqlAlchemyMappedRepository",
    "SqlAlchemyOutbox",
    "SqlAlchemyUnitOfWork",
    "StrictModel",
    "SystemClock",
    "TransactionBehavior",
    "UuidGenerator",
    "bind_context",
    "claim_inbox_message",
    "configure_logging",
    "create_async_engine",
    "create_database_backend",
    "create_session_factory",
    "get_logger",
    "projection_consumer",
]
