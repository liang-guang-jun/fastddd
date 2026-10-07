"""Persistence adapters, one package per storage engine.

``sqlalchemy`` is the only engine wired so far, and its surface is re-exported
here so a caller can name an adapter without committing to the engine behind
it.
"""

from .sqlalchemy import (
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
    "DatabaseBackend",
    "DatabaseConfigurationError",
    "DatabricksLakebaseCredentialProvider",
    "SqlAlchemyAggregateRepository",
    "SqlAlchemyMaintenance",
    "SqlAlchemyMappedRepository",
    "SqlAlchemyOutbox",
    "SqlAlchemyUnitOfWork",
    "create_async_engine",
    "create_database_backend",
    "create_session_factory",
]
