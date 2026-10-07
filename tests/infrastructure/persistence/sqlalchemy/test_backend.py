"""Tests for database backend resolution and credential providers."""

from __future__ import annotations

import ssl
from pathlib import Path
from typing import Any, Literal

import pytest
from pydantic import SecretStr
from sqlalchemy import text
from sqlalchemy.pool import QueuePool

from fastddd.infrastructure.configuration.schemas import (
    DatabaseConfig,
    DatabaseOptionsConfig,
    DatabasePasswordAuthConfig,
    DatabasePoolConfig,
)
from fastddd.infrastructure.persistence.sqlalchemy.backend import (
    DatabaseConfigurationError,
    DatabricksLakebaseCredentialProvider,
    NoDatabaseCredentialProvider,
    StaticPasswordCredentialProvider,
    _ssl_context,
    create_database_backend,
)

Provider = Literal["postgresql", "sqlite", "databricks_lakebase"]

LAKEBASE_ENVIRONMENT = {
    "PGHOST": "lakebase.internal",
    "PGPORT": "5432",
    "PGDATABASE": "databricks_postgres",
    "PGUSER": "app@service-principal",
    "PGSSLMODE": "require",
    "LAKEBASE_ENDPOINT": "projects/p/branches/b/endpoints/e",
}


def _config(
    provider: Provider, *, database: str = "appdb", **overrides: Any
) -> DatabaseConfig:
    """Return a database configuration for one provider."""
    return DatabaseConfig(
        provider=provider,
        driver="aiosqlite" if provider == "sqlite" else "asyncpg",
        auth=DatabasePasswordAuthConfig(
            username="app", password=SecretStr("secret"), database=database
        ),
        **overrides,
    )


class _FakeCredential:
    """A credential shaped like the one the Databricks SDK returns."""

    def __init__(self, token: str | None) -> None:
        self.token = token


class _FakePostgresApi:
    """The slice of the Databricks Postgres API the provider calls."""

    def __init__(self, token: str | None) -> None:
        self.token = token
        self.endpoints: list[str] = []

    def generate_database_credential(self, *, endpoint: str) -> _FakeCredential:
        """Return the configured token and remember which endpoint was asked for."""
        self.endpoints.append(endpoint)

        return _FakeCredential(self.token)


class _FakeWorkspace:
    """A workspace client the provider can be built with."""

    def __init__(self, token: str | None = "token-1") -> None:
        self._postgres = _FakePostgresApi(token)

    @property
    def postgres(self) -> _FakePostgresApi:
        """Return the Postgres API."""
        return self._postgres


def test_sqlite_points_at_the_configured_file() -> None:
    backend = create_database_backend(_config("sqlite", database="app.db"))

    assert backend.url().drivername == "sqlite+aiosqlite"
    assert backend.url().database == "app.db"


async def test_sqlite_engine_carries_the_configured_pragma(tmp_path: Path) -> None:
    database = str(tmp_path / "app.db")
    backend = create_database_backend(
        _config(
            "sqlite",
            database=database,
            options=DatabaseOptionsConfig(busy_timeout_ms=1234),
        )
    )

    engine = backend.create_engine()
    try:
        async with engine.connect() as connection:
            timeout = await connection.execute(text("pragma busy_timeout"))
            assert timeout.scalar() == 1234
    finally:
        await engine.dispose()


def test_postgres_reads_its_endpoint_from_the_environment() -> None:
    backend = create_database_backend(
        _config("postgresql"),
        environment={"DATABASE_HOST": "db.internal", "DATABASE_PORT": "5432"},
    )

    url = backend.url()
    assert url.host == "db.internal"
    assert url.port == 5432
    assert url.username == "app"
    assert url.database == "appdb"
    # The password never enters the URL, so it cannot leak through engine state.
    assert url.password is None


def test_postgres_accepts_the_libpq_variable_names() -> None:
    backend = create_database_backend(
        _config("postgresql"),
        environment={"PGHOST": "localhost", "PGPORT": "6543"},
    )

    assert backend.url().host == "localhost"
    assert backend.url().port == 6543


def test_postgres_without_an_endpoint_is_refused() -> None:
    with pytest.raises(DatabaseConfigurationError, match="DATABASE_HOST or PGHOST"):
        create_database_backend(_config("postgresql"), environment={})


def test_a_port_that_is_not_a_number_is_refused() -> None:
    with pytest.raises(DatabaseConfigurationError, match="PGPORT must be an integer"):
        create_database_backend(
            _config("postgresql"),
            environment={"PGHOST": "db.internal", "PGPORT": "postgres"},
        )


def test_a_port_outside_the_range_is_refused() -> None:
    with pytest.raises(DatabaseConfigurationError, match="between 1 and 65535"):
        create_database_backend(
            _config("postgresql"),
            environment={"PGHOST": "db.internal", "PGPORT": "70000"},
        )


def test_the_ssl_mode_reaches_the_url() -> None:
    backend = create_database_backend(
        _config("postgresql"),
        environment={
            "PGHOST": "db.internal",
            "PGPORT": "5432",
            "PGSSLMODE": "require",
        },
    )

    assert backend.url().query.get("sslmode") == "require"


async def test_postgres_engine_takes_its_pool_from_configuration() -> None:
    backend = create_database_backend(
        _config("postgresql", pool=DatabasePoolConfig(size=7, max_overflow=2)),
        environment={"PGHOST": "db.internal", "PGPORT": "5432"},
    )

    engine = backend.create_engine()
    try:
        assert engine.dialect.name == "postgresql"
        pool = engine.sync_engine.pool
        assert isinstance(pool, QueuePool)
        assert pool.size() == 7
    finally:
        await engine.dispose()


@pytest.mark.parametrize(
    "sslmode",
    ["", "disable", "allow", "prefer", "require", "verify-ca", "verify-full"],
)
def test_an_ssl_mode_is_mapped_to_what_asyncpg_accepts(sslmode: str) -> None:
    context = _ssl_context(sslmode)

    if sslmode == "":
        assert context is None
        return
    if sslmode == "disable":
        assert context is False
        return

    assert isinstance(context, ssl.SSLContext)
    unverified = sslmode in {"allow", "prefer", "require"}
    assert (context.verify_mode == ssl.CERT_NONE) is unverified
    assert context.check_hostname is not unverified


def test_an_unknown_ssl_mode_is_refused() -> None:
    with pytest.raises(
        DatabaseConfigurationError, match="Unsupported PGSSLMODE: bogus"
    ):
        _ssl_context("bogus")


def test_databricks_without_a_workspace_client_is_refused() -> None:
    with pytest.raises(
        DatabaseConfigurationError, match="requires an injected workspace"
    ):
        create_database_backend(
            _config("databricks_lakebase"), environment=LAKEBASE_ENVIRONMENT
        )


def test_databricks_reads_the_app_metadata_from_the_environment() -> None:
    backend = create_database_backend(
        _config("databricks_lakebase"),
        workspace=_FakeWorkspace(),
        environment=LAKEBASE_ENVIRONMENT,
    )

    url = backend.url()
    assert url.host == "lakebase.internal"
    assert url.port == 5432
    assert url.database == "databricks_postgres"
    assert url.username == "app@service-principal"


def test_databricks_names_every_variable_it_is_missing() -> None:
    with pytest.raises(DatabaseConfigurationError) as refused:
        create_database_backend(
            _config("databricks_lakebase"),
            workspace=_FakeWorkspace(),
            environment={"PGHOST": "lakebase.internal", "PGPORT": "5432"},
        )

    message = str(refused.value)
    assert "PGDATABASE" in message
    assert "LAKEBASE_ENDPOINT" in message
    assert "PGHOST" not in message


async def test_databricks_engine_is_created_for_asyncpg() -> None:
    backend = create_database_backend(
        _config("databricks_lakebase"),
        workspace=_FakeWorkspace(),
        environment=LAKEBASE_ENVIRONMENT,
    )

    engine = backend.create_engine()
    try:
        assert engine.dialect.name == "postgresql"
    finally:
        await engine.dispose()


async def test_sqlite_uses_no_credentials() -> None:
    assert await NoDatabaseCredentialProvider().password() is None


async def test_a_configured_password_is_handed_back_unchanged() -> None:
    assert await StaticPasswordCredentialProvider("s3cret").password() == "s3cret"


async def test_a_lakebase_token_is_generated_per_connection() -> None:
    workspace = _FakeWorkspace("token-1")
    provider = DatabricksLakebaseCredentialProvider(
        workspace, "projects/p/branches/b/endpoints/e"
    )

    assert await provider.password() == "token-1"
    assert workspace.postgres.endpoints == ["projects/p/branches/b/endpoints/e"]


async def test_an_empty_lakebase_token_is_refused() -> None:
    provider = DatabricksLakebaseCredentialProvider(_FakeWorkspace(None), "endpoint")

    with pytest.raises(DatabaseConfigurationError, match="empty database credential"):
        await provider.password()
