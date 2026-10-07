"""Alembic environment templates and the scaffolder that writes them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

_ENV_PY = '''"""Alembic environment for the schema an application declares.

The database URL reaches this file through the Alembic configuration the
migration commands build, so nothing here reads application configuration.
"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy import Connection, create_engine, pool
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

# Autogenerate sees only imported models, so every module that declares a table
# is imported here; a module left out of the list is simply invisible.
__METADATA_IMPORTS__

config = context.config

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Emit SQL without connecting to a database, as used by ``--sql``."""
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations on an established connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=connection.dialect.name == "sqlite",
    )

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations(url: str) -> None:
    """Run migrations through an async engine created from the configured URL."""
    engine = create_async_engine(url, poolclass=pool.NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(do_run_migrations)
    finally:
        await engine.dispose()


def run_migrations_online() -> None:
    """Run migrations, reusing a connection injected by the caller when present."""
    injected = config.attributes.get("connection")
    if isinstance(injected, Connection):
        do_run_migrations(injected)
        return

    url = make_url(str(config.get_main_option("sqlalchemy.url")))
    if url.get_dialect().is_async:
        asyncio.run(run_async_migrations(str(url)))
        return

    engine = create_engine(url, poolclass=pool.NullPool)
    try:
        with engine.connect() as connection:
            do_run_migrations(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
'''

_SCRIPT_PY_MAKO = '''"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}

revision: str = ${repr(up_revision)}
down_revision: str | Sequence[str] | None = ${repr(down_revision)}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels)}
depends_on: str | Sequence[str] | None = ${repr(depends_on)}


def upgrade() -> None:
    """Apply the schema change."""
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    """Revert the schema change."""
    ${downgrades if downgrades else "pass"}
'''

_METADATA_SLOT = "__METADATA_IMPORTS__"


@dataclass(frozen=True, slots=True)
class ScaffoldResult:
    """Paths written by a scaffold run and paths kept from an earlier run."""

    written: list[Path]
    kept: list[Path]


def _render_env_py(base_module: str, model_modules: Sequence[str]) -> str:
    """Render the environment for one metadata root and its model modules."""
    imports = [f"from {base_module} import Base"]
    imports += [f"import {module}  # noqa: F401" for module in model_modules]
    return _ENV_PY.replace(_METADATA_SLOT, "\n".join(imports))


def scaffold_environment(
    directory: Path,
    *,
    base_module: str,
    model_modules: Sequence[str],
    force: bool = False,
) -> ScaffoldResult:
    """Write the Alembic environment used by the database migration commands.

    No ``alembic.ini`` is written, because the commands build the Alembic
    configuration in memory and would never read the file. Two consequences are
    worth knowing: the bare ``alembic`` command is not wired up for a project
    that scaffolds this way, and per-project Alembic settings such as
    ``file_template`` have no file to live in -- the migration commands are the
    entry point.

    Args:
        directory: Target directory for ``env.py`` and ``script.py.mako``.
        base_module: Module that defines the metadata root ``Base``.
        model_modules: Modules imported for the tables they declare. Autogenerate
            sees only imported models, so a module left out here stays invisible
            and its tables turn into an empty revision.
        force: Overwrite files that already exist instead of keeping them.

    Returns:
        The paths that were written and the paths that were left untouched.
    """
    written: list[Path] = []
    kept: list[Path] = []

    (directory / "versions").mkdir(parents=True, exist_ok=True)

    for relative, content in (
        (Path("env.py"), _render_env_py(base_module, model_modules)),
        (Path("script.py.mako"), _SCRIPT_PY_MAKO),
        (Path("versions") / ".gitkeep", ""),
    ):
        path = directory / relative
        if path.exists() and not force:
            kept.append(path)
            continue

        path.write_text(content, encoding="utf-8")
        written.append(path)

    return ScaffoldResult(written=written, kept=kept)
