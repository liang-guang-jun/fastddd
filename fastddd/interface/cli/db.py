"""Database migration commands backed by Alembic's Python API."""

from __future__ import annotations

import asyncio
import os
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Annotated

import typer
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine

from .scaffold import scaffold_environment


@dataclass(frozen=True, slots=True)
class DbEnvironment:
    """Everything one ``db`` sub-application needs, supplied by its caller.

    The commands read no configuration of their own. They are handed the Alembic
    environment they run, the pattern that numbers its revisions, the database
    URL to fall back on, and -- for a database whose credentials cannot be
    written down ahead of time, such as an endpoint that mints a token per
    connection -- a factory for an engine that already holds them.

    Attributes:
        migrations: Directory holding the ``env.py`` the commands run and the
            ``versions/`` they read.
        revision_pattern: Pattern whose ``number`` group yields the zero-padded
            prefix of a revision file name, so the next id resumes after the
            highest one already on disk.
        database_url: Called when neither ``--url`` nor the environment variable
            names a database. The URL must be absolute: it reaches Alembic
            as-is, and the commands may run from any working directory.
        env_var: Name of the environment variable that may name a database, so a
            deployment can redirect a command without rewriting its command line.
        program_name: Name of the program the commands are reached through, used
            only to spell out an actionable hint.
        base_module: Module that defines the metadata root ``Base``, read only
            when the environment is scaffolded.
        model_modules: Modules the scaffolded environment imports for the tables
            they declare. Autogenerate sees only imported models.
        engine: Called to obtain an engine whose credentials the caller owns, so
            an online command can run on a connection that caller opened. Pass
            ``None`` to let Alembic open its own connection from the URL, which
            is all a statically configured database needs.
    """

    migrations: Path
    revision_pattern: re.Pattern[str]
    database_url: Callable[[], str]
    env_var: str
    program_name: str
    base_module: str
    model_modules: Sequence[str]
    engine: Callable[[], AsyncEngine] | None


def _require_environment(environment: DbEnvironment) -> None:
    """Exit with an actionable message when the Alembic environment is missing."""
    if not (environment.migrations / "env.py").is_file():
        typer.echo(
            f"Alembic environment not found at {environment.migrations}; "
            f"run '{environment.program_name} db init'."
        )
        raise typer.Exit(code=1)


def _resolve_url(environment: DbEnvironment, url: str | None) -> str:
    """Return the URL to use: the flag first, then the environment, then the caller's."""
    return url or os.getenv(environment.env_var) or environment.database_url()


def alembic_config(environment: DbEnvironment, url: str | None = None) -> Config:
    """Create a cwd-independent Alembic configuration for the given URL."""
    _require_environment(environment)
    config = Config()
    config.set_main_option("script_location", str(environment.migrations))
    config.set_main_option("sqlalchemy.url", _resolve_url(environment, url))
    return config


def _run_operation(
    environment: DbEnvironment,
    operation: object,
    url: str | None,
    *args: object,
    **kwargs: object,
) -> None:
    """Run an Alembic operation, reusing the injected engine when there is one."""
    _require_environment(environment)
    engine_factory = environment.engine
    if url or os.getenv(environment.env_var) or engine_factory is None:
        # An explicit URL names the database on its own, and with no engine to
        # reuse there is nothing to inject: Alembic opens its own connection.
        operation(  # type: ignore[operator]
            alembic_config(environment, url), *args, **kwargs
        )
        return
    engine = engine_factory()

    async def run() -> None:
        async with engine.connect() as connection:
            await connection.run_sync(
                _run_alembic_operation, environment, operation, args, kwargs
            )
        await engine.dispose()

    asyncio.run(run())


def _run_alembic_operation(
    connection: Connection,
    environment: DbEnvironment,
    operation: object,
    args: tuple[object, ...],
    kwargs: dict[str, object],
) -> None:
    """Execute an Alembic command with its connection injected."""
    config = alembic_config(environment)
    config.attributes["connection"] = connection
    operation(config, *args, **kwargs)  # type: ignore[operator]


def apply_migrations(
    environment: DbEnvironment,
    engine: AsyncEngine,
    revision: str = "head",
    *,
    dispose_after: bool = False,
) -> None:
    """Apply migrations through an engine the caller already owns.

    Alembic otherwise opens its own connection, which never works for an
    in-memory SQLite database: it only exists for the process and pool that
    created it. Injecting the engine keeps the schema and the runtime traffic on
    one database. Synchronous callers such as the CLI use this helper.
    """

    async def run() -> None:
        async with engine.connect() as connection:
            await connection.run_sync(_upgrade_on_connection, environment, revision)
        if dispose_after:
            await engine.dispose()

    asyncio.run(run())


def _upgrade_on_connection(
    connection: Connection, environment: DbEnvironment, revision: str
) -> None:
    """Run an upgrade on a synchronous connection facade."""
    config = alembic_config(environment)
    config.attributes["connection"] = connection
    command.upgrade(config, revision)


def next_revision_id(
    environment: DbEnvironment, versions_dir: Path | None = None
) -> str:
    """Return the next zero-padded four-digit revision prefix.

    Alembic revision identifiers remain strings, so ``0002`` is a valid ID and
    a generated file becomes ``0002_<slug>.py`` through the script template.
    """
    directory = versions_dir or environment.migrations / "versions"
    highest = 0
    for path in directory.glob("*.py"):
        match = environment.revision_pattern.match(path.stem)
        if match is not None:
            highest = max(highest, int(match.group("number")))
    if highest >= 9999:
        raise RuntimeError("Migration revision prefix limit (9999) reached")
    return f"{highest + 1:04d}"


def create_db_app(
    *,
    migrations: Path,
    revision_pattern: re.Pattern[str],
    database_url: Callable[[], str],
    env_var: str,
    program_name: str,
    base_module: str,
    model_modules: Sequence[str],
    engine: Callable[[], AsyncEngine] | None,
) -> typer.Typer:
    """Build the ``db`` sub-application for one Alembic environment.

    Every input is required rather than defaulted, because this module is shared
    by applications that disagree on all of them: one process may serve several
    schemas, and a shared default would silently bind every command to whichever
    environment happened to be imported first. Nothing here reads configuration,
    so the caller decides how a database is found -- and whether the commands may
    open one themselves.

    Args:
        migrations: Directory that holds the Alembic environment, i.e. the
            ``env.py`` the commands run and the ``versions/`` they read.
        revision_pattern: Pattern whose ``number`` group yields the zero-padded
            prefix of a revision file name, so the next id can resume after the
            highest one already on disk.
        database_url: Called to obtain the URL used when neither ``--url`` nor
            the environment variable names a database. It must be absolute: the
            commands run from any working directory.
        env_var: Name of the environment variable that may name a database.
        program_name: Name of the program the commands are reached through, used
            only to spell out an actionable hint.
        base_module: Module that defines the metadata root ``Base``.
        model_modules: Modules the scaffolded environment imports for the tables
            they declare. Autogenerate sees only imported models, so a module
            left out here would silently turn into an empty revision.
        engine: Called to obtain an engine whose credentials the caller owns, so
            an online command runs on a connection that caller opened. Pass
            ``None`` to let Alembic open its own connection from the URL.

    Returns:
        The ``db`` sub-application, ready to be added to a parent Typer app.
    """
    environment = DbEnvironment(
        migrations=migrations,
        revision_pattern=revision_pattern,
        database_url=database_url,
        env_var=env_var,
        program_name=program_name,
        base_module=base_module,
        model_modules=model_modules,
        engine=engine,
    )
    db = typer.Typer(help="Manage database schema migrations.", no_args_is_help=True)
    # One specification shared by every command that can be pointed at a
    # database: Typer builds a distinct click option per command from it, and
    # this is the only way to keep the environment variable a runtime value.
    url_option = typer.Option(
        None,
        "--url",
        envvar=env_var,
        help=f"SQLAlchemy URL; defaults to ${env_var} or the configured database.",
    )

    @db.command()
    def init(
        directory: Annotated[
            Path | None,
            typer.Argument(help="Directory that holds the Alembic environment."),
        ] = None,
        force: Annotated[
            bool, typer.Option("--force", help="Overwrite files that already exist.")
        ] = False,
    ) -> None:
        """Create the Alembic environment used by the other db commands.

        Existing files are kept unless ``--force`` is given, so the command is safe
        to run in a checkout that already owns its migrations.
        """
        result = scaffold_environment(
            directory or migrations,
            base_module=environment.base_module,
            model_modules=environment.model_modules,
            force=force,
        )
        for path in result.written:
            typer.echo(f"created {path}")
        for path in result.kept:
            typer.echo(f"kept    {path}")

    @db.command()
    def revision(
        message: Annotated[
            str, typer.Argument(help="Human-readable migration message.")
        ],
        url: str | None = url_option,
        empty: Annotated[
            bool,
            typer.Option(
                "--empty",
                help="Create a manual migration without schema autogeneration.",
            ),
        ] = False,
        head: Annotated[
            str, typer.Option(help="Parent revision, normally 'head'.")
        ] = "head",
        splice: Annotated[
            bool, typer.Option(help="Allow a branch from a non-head revision.")
        ] = False,
        branch_label: Annotated[
            str | None, typer.Option(help="Optional Alembic branch label.")
        ] = None,
    ) -> None:
        """Create a revision; schema autogeneration is enabled by default."""
        _run_operation(
            environment,
            command.revision,
            url,
            message=message,
            autogenerate=not empty,
            rev_id=next_revision_id(environment),
            head=head,
            splice=splice,
            branch_label=branch_label,
        )

    @db.command()
    def upgrade(
        revision: Annotated[
            str, typer.Argument(help="Target revision, e.g. head or +1")
        ] = "head",
        url: str | None = url_option,
        sql: Annotated[
            bool, typer.Option(help="Print SQL without applying it.")
        ] = False,
        tag: Annotated[
            str | None, typer.Option(help="Optional Alembic environment tag.")
        ] = None,
    ) -> None:
        """Upgrade the database to a target revision."""
        if sql:
            command.upgrade(
                alembic_config(environment, url), revision, sql=True, tag=tag
            )
        else:
            _run_operation(environment, command.upgrade, url, revision, tag=tag)

    @db.command()
    def downgrade(
        revision: Annotated[
            str, typer.Argument(help="Target revision, e.g. -1 or base")
        ],
        url: str | None = url_option,
        sql: Annotated[
            bool, typer.Option(help="Print SQL without applying it.")
        ] = False,
        tag: Annotated[
            str | None, typer.Option(help="Optional Alembic environment tag.")
        ] = None,
    ) -> None:
        """Downgrade the database to a target revision."""
        if sql:
            command.downgrade(
                alembic_config(environment, url), revision, sql=True, tag=tag
            )
        else:
            _run_operation(environment, command.downgrade, url, revision, tag=tag)

    @db.command()
    def current(url: str | None = url_option, verbose: bool = False) -> None:
        """Display the revision currently recorded by the database."""
        _run_operation(environment, command.current, url, verbose=verbose)

    @db.command()
    def history(
        url: str | None = url_option,
        verbose: bool = False,
        indicate_current: bool = False,
    ) -> None:
        """Display migration history."""
        command.history(
            alembic_config(environment, url),
            verbose=verbose,
            indicate_current=indicate_current,
        )

    @db.command()
    def heads(url: str | None = url_option, verbose: bool = False) -> None:
        """Display current migration heads."""
        command.heads(alembic_config(environment, url), verbose=verbose)

    @db.command()
    def branches(url: str | None = url_option, verbose: bool = False) -> None:
        """Display migration branch points."""
        command.branches(alembic_config(environment, url), verbose=verbose)

    @db.command()
    def show(revision: str, url: str | None = url_option) -> None:
        """Display the details of one migration revision."""
        command.show(alembic_config(environment, url), revision)

    @db.command()
    def stamp(
        revision: Annotated[
            str, typer.Argument(help="Revision to record without migration.")
        ],
        url: str | None = url_option,
        purge: Annotated[
            bool, typer.Option(help="Clear existing revision stamps first.")
        ] = False,
    ) -> None:
        """Record a revision without executing upgrade or downgrade code."""
        _run_operation(environment, command.stamp, url, revision, purge=purge)

    @db.command()
    def check(url: str | None = url_option) -> None:
        """Fail if autogenerate detects model changes absent from migrations."""
        _run_operation(environment, command.check, url)

    @db.command()
    def merge(
        revisions: Annotated[list[str], typer.Argument(help="Heads to merge.")],
        message: Annotated[str, typer.Option("--message", "-m", help="Merge message")],
        url: str | None = url_option,
    ) -> None:
        """Create a merge revision with the next four-digit prefix."""
        _run_operation(
            environment,
            command.merge,
            url,
            revisions=revisions,
            message=message,
            rev_id=next_revision_id(environment),
        )

    return db
