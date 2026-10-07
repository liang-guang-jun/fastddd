"""Pydantic schemas for application configuration.

``StrictModel`` and the section models are the vocabulary a service composes
its own root schema from; ``AppConfig`` is the kernel's ready-made default.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PositiveInt, SecretStr


class StrictModel(BaseModel):
    """Base configuration model with strict extra-field handling."""

    model_config = ConfigDict(extra="forbid")


class ProfileConfig(StrictModel):
    """One configuration overlay: the file to read and when to apply it.

    ``name`` selects ``config.<name>.yaml`` next to the default file, and
    ``priority`` orders the overlays, a larger number winning. Profiles that
    share a priority are applied in the order they are declared.
    """

    name: str
    priority: int = 0


class CorsConfig(StrictModel):
    """Cross-origin resource sharing configuration."""

    allow_origins: list[str] = Field(default_factory=list)
    allow_credentials: bool = True


class ApiConfig(StrictModel):
    """HTTP API server configuration."""

    app: str
    factory: str
    prefix: str = "/api/v1"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    reload: bool = False
    debug: bool = False
    cors: CorsConfig = Field(default_factory=CorsConfig)


class DatabasePasswordAuthConfig(StrictModel):
    """Username/password database authentication."""

    type: Literal["password"] = "password"
    username: str
    password: SecretStr
    database: str


class DatabasePoolConfig(StrictModel):
    """SQLAlchemy connection-pool configuration."""

    size: PositiveInt = 5
    max_overflow: int = Field(default=10, ge=0)
    timeout_seconds: PositiveInt = 30
    recycle_seconds: PositiveInt = 1800


class DatabaseOptionsConfig(StrictModel):
    """Provider-specific database options."""

    busy_timeout_ms: int | None = Field(default=None, ge=0)


class DatabaseConfig(StrictModel):
    """Database connection and pooling configuration."""

    provider: Literal["postgresql", "sqlite", "databricks_lakebase"]
    driver: str
    auth: DatabasePasswordAuthConfig
    echo: bool = False
    pool: DatabasePoolConfig = Field(default_factory=DatabasePoolConfig)
    options: DatabaseOptionsConfig = Field(default_factory=DatabaseOptionsConfig)


class LoggingConfig(StrictModel):
    """Application logging configuration."""

    level: Literal[
        "CRITICAL",
        "ERROR",
        "WARNING",
        "INFO",
        "DEBUG",
        "NOTSET",
    ] = "INFO"
    json_output: bool = False
    colors: bool = False
    silenced_loggers: list[str] = Field(default_factory=list)
    log_request_headers: bool = False


class AppConfig(StrictModel):
    """The kernel's default aggregate: what every service declares.

    It is the schema ``ConfigResolver`` falls back to, so a service that needs
    more sections composes its own root model from the section classes above
    and hands that to the resolver instead.
    """

    api: ApiConfig
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
