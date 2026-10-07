"""Database backend resolution and dynamic credential providers."""
# ruff: noqa: D102, D107

from __future__ import annotations

import asyncio
import os
import ssl
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import AsyncEngine

from .database import create_async_engine

if TYPE_CHECKING:
    from ...configuration.schemas import DatabaseConfig


class DatabaseConfigurationError(RuntimeError):
    """Raised when effective backend configuration cannot be resolved safely."""


class DatabaseCredentialProvider(Protocol):
    """Return credentials only when a physical connection needs them."""

    async def password(self) -> str | None: ...


class NoDatabaseCredentialProvider:
    """Use no database password for SQLite."""

    async def password(self) -> str | None:
        return None


class StaticPasswordCredentialProvider:
    """Return the configured PostgreSQL password without exposing it elsewhere."""

    def __init__(self, password: str) -> None:
        self._password = password

    async def password(self) -> str:
        return self._password


class DatabaseCredential(Protocol):
    """The token a Databricks Lakebase database credential carries."""

    token: str | None


class LakebasePostgresApi(Protocol):
    """The slice of the Databricks Postgres API this adapter calls."""

    def generate_database_credential(self, *, endpoint: str) -> DatabaseCredential: ...


class DatabricksWorkspace(Protocol):
    """The slice of the Databricks workspace client this adapter calls.

    The Databricks SDK is an optional extra, so nothing here imports it: the
    composition root builds a client and injects it, and any object shaped like
    this — the SDK's own ``WorkspaceClient`` included — is accepted.
    """

    @property
    def postgres(self) -> LakebasePostgresApi: ...


class DatabricksLakebaseCredentialProvider:
    """Generate a fresh App service-principal database token per new connection."""

    def __init__(self, workspace: DatabricksWorkspace, endpoint: str) -> None:
        self._workspace = workspace
        self._endpoint = endpoint

    async def password(self) -> str:
        credential = await asyncio.to_thread(
            self._workspace.postgres.generate_database_credential,
            endpoint=self._endpoint,
        )
        if not credential.token:
            raise DatabaseConfigurationError(
                "Databricks Lakebase returned an empty database credential"
            )
        return credential.token


@dataclass(frozen=True, slots=True)
class DatabaseConnectionInfo:
    """Resolved non-secret metadata needed to create a database connection."""

    drivername: str
    host: str | None
    port: int | None
    database: str | None
    username: str | None
    sslmode: str

    def url(self) -> URL:
        """Build a password-free URL so secrets never enter engine state/logs."""
        return URL.create(
            self.drivername,
            username=self.username,
            host=self.host,
            port=self.port,
            database=self.database,
            query={"sslmode": self.sslmode} if self.sslmode else {},
        )


class DatabaseBackend(Protocol):
    """Resolve provider-specific settings and create its SQLAlchemy engine."""

    def url(self) -> URL: ...

    def create_engine(self) -> AsyncEngine: ...


def _required(
    environment: Mapping[str, str],
    *names: str,
    source: str = "Databricks Lakebase",
) -> dict[str, str]:
    """Return the named environment variables or list the missing ones."""
    values = {name: environment.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise DatabaseConfigurationError(
            f"{source} requires runtime environment variables: " + ", ".join(missing)
        )
    return values


def _port(value: str) -> int:
    """Parse and validate a PostgreSQL port from configuration."""
    try:
        port = int(value)
    except ValueError as error:
        raise DatabaseConfigurationError("PGPORT must be an integer") from error
    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError("PGPORT must be between 1 and 65535")
    return port


def _first_defined(environment: Mapping[str, str], *names: str) -> str:
    """Return the first non-empty value among the accepted environment names."""
    for name in names:
        value = environment.get(name, "").strip()
        if value:
            return value
    return ""


def _postgres_endpoint(environment: Mapping[str, str]) -> tuple[str, int, str]:
    """Resolve the PostgreSQL host, port, and sslmode from the environment."""
    host = _first_defined(environment, "DATABASE_HOST", "PGHOST")
    port = _first_defined(environment, "DATABASE_PORT", "PGPORT")
    if not host or not port:
        raise DatabaseConfigurationError(
            "PostgreSQL requires runtime environment variables: "
            "DATABASE_HOST or PGHOST, DATABASE_PORT or PGPORT"
        )
    return (
        host,
        _port(port),
        _first_defined(environment, "PGSSLMODE", "DATABASE_SSLMODE"),
    )


def _ssl_context(sslmode: str) -> ssl.SSLContext | bool | None:
    """Map PostgreSQL SSL modes to asyncpg's supported TLS values."""
    if sslmode in {"", "disable"}:
        return False if sslmode == "disable" else None
    context = ssl.create_default_context()
    if sslmode in {"allow", "prefer", "require"}:
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
    elif sslmode not in {"verify-ca", "verify-full"}:
        raise DatabaseConfigurationError(f"Unsupported PGSSLMODE: {sslmode}")
    return context


class SqliteDatabaseBackend:
    """Create the local SQLite engine with its existing PRAGMA options."""

    def __init__(self, config: DatabaseConfig) -> None:
        self._config = config

    def url(self) -> URL:
        return URL.create("sqlite+aiosqlite", database=self._config.auth.database)

    def create_engine(self) -> AsyncEngine:
        return create_async_engine(
            self.url(),
            echo=self._config.echo,
            sqlite_busy_timeout_ms=self._config.options.busy_timeout_ms,
        )


class PostgresqlDatabaseBackend:
    """Create static-password asyncpg PostgreSQL connections.

    The endpoint lives in the environment rather than in layered configuration:
    ``DATABASE_HOST`` and ``DATABASE_PORT`` are preferred, ``PGHOST`` and
    ``PGPORT`` are accepted fallbacks, and ``PGSSLMODE`` (or
    ``DATABASE_SSLMODE``) is optional. Credentials and the database name come
    from the configured ``database.auth`` section.
    """

    def __init__(
        self,
        config: DatabaseConfig,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config
        host, port, sslmode = _postgres_endpoint(environment or os.environ)
        self._info = DatabaseConnectionInfo(
            "postgresql+asyncpg",
            host,
            port,
            config.auth.database,
            config.auth.username,
            sslmode,
        )
        self._credentials = StaticPasswordCredentialProvider(
            config.auth.password.get_secret_value()
        )

    def url(self) -> URL:
        return self._info.url()

    def create_engine(self) -> AsyncEngine:
        return _create_postgres_engine(
            self.url(),
            self._config,
            self._info.sslmode,
            self._credentials,
        )


class DatabricksLakebaseDatabaseBackend:
    """Resolve Databricks App metadata and refresh OAuth tokens per connection."""

    def __init__(
        self,
        config: DatabaseConfig,
        workspace: DatabricksWorkspace,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._config = config
        values = _required(
            environment or os.environ,
            "PGHOST",
            "PGPORT",
            "PGDATABASE",
            "PGUSER",
            "PGSSLMODE",
            "LAKEBASE_ENDPOINT",
        )
        self._info = DatabaseConnectionInfo(
            "postgresql+asyncpg",
            values["PGHOST"],
            _port(values["PGPORT"]),
            values["PGDATABASE"],
            values["PGUSER"],
            values["PGSSLMODE"],
        )
        self._credentials = DatabricksLakebaseCredentialProvider(
            workspace, values["LAKEBASE_ENDPOINT"]
        )

    def url(self) -> URL:
        return self._info.url()

    def create_engine(self) -> AsyncEngine:
        return _create_postgres_engine(
            self.url(),
            self._config,
            self._info.sslmode,
            self._credentials,
        )


def _create_postgres_engine(
    url: URL,
    config: DatabaseConfig,
    sslmode: str,
    credentials: DatabaseCredentialProvider,
) -> AsyncEngine:
    """Create asyncpg connections with credentials supplied at pool expansion time."""

    async def connect() -> object:
        import asyncpg  # type: ignore[import-untyped]

        password = await credentials.password()
        return await asyncpg.connect(
            host=url.host,
            port=url.port,
            user=url.username,
            password=password,
            database=url.database,
            ssl=_ssl_context(sslmode),
        )

    return create_async_engine(
        url,
        echo=config.echo,
        pool_size=config.pool.size,
        max_overflow=config.pool.max_overflow,
        pool_timeout=config.pool.timeout_seconds,
        pool_recycle=config.pool.recycle_seconds,
        async_creator=connect,
    )


def create_database_backend(
    config: DatabaseConfig,
    *,
    workspace: DatabricksWorkspace | None = None,
    environment: Mapping[str, str] | None = None,
) -> DatabaseBackend:
    """Select the sole provider-specific branch for the application.

    The Databricks branch is the only one needing anything extra: its client
    comes from the optional ``databricks`` extra and is injected here, so the
    SDK is never imported by this module.
    """
    if config.provider == "sqlite":
        return SqliteDatabaseBackend(config)
    if config.provider == "postgresql":
        return PostgresqlDatabaseBackend(config, environment)
    if workspace is None:
        raise DatabaseConfigurationError(
            "databricks_lakebase requires an injected workspace client "
            "(the optional 'databricks' extra builds one)"
        )
    return DatabricksLakebaseDatabaseBackend(config, workspace, environment)
