"""SQLAlchemy adapters configured for SQLite as the first storage engine."""

from .backend import (
    DatabaseBackend,
    DatabaseConfigurationError,
    DatabricksLakebaseCredentialProvider,
    create_database_backend,
)
from .database import (
    create_async_engine,
    create_session_factory,
)
from .maintenance import SqlAlchemyMaintenance
from .mapper import AggregateRecordMapper
from .outbox import SqlAlchemyOutbox
from .repository import SqlAlchemyAggregateRepository, SqlAlchemyMappedRepository
from .unit_of_work import SqlAlchemyUnitOfWork

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
