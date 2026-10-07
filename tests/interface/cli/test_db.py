"""Tests for the database migration sub-application."""

from __future__ import annotations

import inspect
import re
import sqlite3
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from pathlib import Path
from typing import Any, cast

import pytest
import typer
from alembic.config import Config
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine
from typer.main import get_command
from typer.testing import CliRunner, Result

from fastddd.interface.cli import db as db_module
from fastddd.interface.cli.db import (
    DbEnvironment,
    alembic_config,
    create_db_app,
    next_revision_id,
)
from fastddd.interface.cli.scaffold import scaffold_environment

BASE = "fastddd.infrastructure.persistence.sqlalchemy.models"
PATTERN = re.compile(r"^(?P<number>\d{4})(?:_|$)")
ENV_VAR = "FASTDDD_TEST_DATABASE_URL"
FALLBACK = "sqlite+aiosqlite:////tmp/fastddd-fallback.db"
COMMANDS = [
    "branches",
    "check",
    "current",
    "downgrade",
    "heads",
    "history",
    "init",
    "merge",
    "revision",
    "show",
    "stamp",
    "upgrade",
]


@pytest.fixture(autouse=True)
def _no_ambient_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every test independent of the environment it happens to run in."""
    monkeypatch.delenv(ENV_VAR, raising=False)


def refuse_url() -> str:
    raise AssertionError("the caller's database URL must not be consulted")


def refuse_engine() -> AsyncEngine:
    raise AssertionError("the engine must not be built")


def build(
    migrations: Path,
    *,
    database_url: Callable[[], str] = lambda: FALLBACK,
    engine: Callable[[], AsyncEngine] | None = None,
    model_modules: Sequence[str] = (),
) -> typer.Typer:
    return create_db_app(
        migrations=migrations,
        revision_pattern=PATTERN,
        database_url=database_url,
        env_var=ENV_VAR,
        program_name="fastddd",
        base_module=BASE,
        model_modules=model_modules,
        engine=engine,
    )


def environment(migrations: Path, *, database_url: str = FALLBACK) -> DbEnvironment:
    return DbEnvironment(
        migrations=migrations,
        revision_pattern=PATTERN,
        database_url=lambda: database_url,
        env_var=ENV_VAR,
        program_name="fastddd",
        base_module=BASE,
        model_modules=(),
        engine=None,
    )


def scaffolded(directory: Path) -> Path:
    """Write a real Alembic environment and hand back the directory holding it."""
    scaffold_environment(directory, base_module=BASE, model_modules=[])
    return directory


def invoke(
    app: typer.Typer, *args: str, env: Mapping[str, str | None] | None = None
) -> Result:
    return CliRunner().invoke(app, list(args), env=env)


def click_group(app: typer.Typer) -> Any:
    """The command tree Typer builds, as the click layer a user types against.

    Typer 0.27 vendors its own copy of click, so the type ``get_command`` returns
    cannot be named here and ``Any`` is the honest type for that layer. The
    assertions below read it on purpose.
    """
    return cast("Any", get_command(app))


def url_env_vars(app: typer.Typer) -> dict[str, Any]:
    """Map every command that offers ``--url`` to the environment it reads."""
    found: dict[str, Any] = {}
    for name, command in click_group(app).commands.items():
        for option in command.params:
            if "--url" in option.opts:
                found[name] = option.envvar
    return found


def prepared(
    tmp_path: Path,
    *,
    database_url: Callable[[], str] = lambda: FALLBACK,
    engine: Callable[[], AsyncEngine] | None = None,
    model_modules: Sequence[str] = (),
) -> typer.Typer:
    """Build the sub-application and write its environment through ``init``."""
    app = build(
        tmp_path,
        database_url=database_url,
        engine=engine,
        model_modules=model_modules,
    )
    assert invoke(app, "init").exit_code == 0
    return app


class _RecordingConnection:
    """Stands in for the connection an injected engine hands out."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def __aenter__(self) -> _RecordingConnection:
        return self

    async def __aexit__(self, *info: object) -> bool:
        self.events.append("close")
        return False

    async def run_sync(self, function: Callable[..., object], *args: object) -> object:
        return function(self, *args)


class _RecordingEngine:
    """Stands in for an engine whose credentials the caller owns."""

    def __init__(self, events: list[str]) -> None:
        self.events = events

    def connect(self) -> _RecordingConnection:
        self.events.append("connect")
        return _RecordingConnection(self.events)

    async def dispose(self) -> None:
        self.events.append("dispose")


# --- the shape of the sub-application -----------------------------------------


def test_every_input_is_required() -> None:
    parameters = inspect.signature(create_db_app).parameters

    assert list(parameters) == [
        "migrations",
        "revision_pattern",
        "database_url",
        "env_var",
        "program_name",
        "base_module",
        "model_modules",
        "engine",
    ]
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in parameters.values()
    )


def test_the_sub_application_offers_every_migration_command(tmp_path: Path) -> None:
    assert sorted(click_group(build(tmp_path)).commands) == COMMANDS


def test_only_the_commands_that_connect_accept_a_url(tmp_path: Path) -> None:
    assert sorted(url_env_vars(build(tmp_path))) == sorted(set(COMMANDS) - {"init"})


def test_every_url_option_reads_the_environment_variable_it_was_given(
    tmp_path: Path,
) -> None:
    offered = url_env_vars(build(tmp_path))

    assert len(offered) == len(COMMANDS) - 1
    assert set(offered.values()) == {ENV_VAR}


# --- where a database URL comes from ------------------------------------------


def test_the_flag_names_the_database_when_it_is_given(tmp_path: Path) -> None:
    config = alembic_config(environment(scaffolded(tmp_path)), "sqlite://flag")

    assert config.get_main_option("sqlalchemy.url") == "sqlite://flag"


def test_the_environment_names_the_database_when_the_flag_is_absent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(ENV_VAR, "sqlite://environment")

    config = alembic_config(environment(scaffolded(tmp_path)))

    assert config.get_main_option("sqlalchemy.url") == "sqlite://environment"


def test_the_callers_url_is_used_when_nothing_else_names_a_database(
    tmp_path: Path,
) -> None:
    config = alembic_config(environment(scaffolded(tmp_path)))

    assert config.get_main_option("sqlalchemy.url") == FALLBACK


def test_the_callers_url_is_not_consulted_when_the_flag_names_a_database(
    tmp_path: Path,
) -> None:
    app = prepared(tmp_path, database_url=refuse_url)

    outcome = invoke(app, "heads", "--url", "sqlite://flag")

    assert outcome.exit_code == 0, outcome.output
    assert outcome.exception is None


def test_the_callers_url_is_not_consulted_when_the_environment_names_one(
    tmp_path: Path,
) -> None:
    app = prepared(tmp_path, database_url=refuse_url)

    outcome = invoke(app, "heads", env={ENV_VAR: "sqlite://environment"})

    assert outcome.exit_code == 0, outcome.output
    assert outcome.exception is None


# --- the engine a caller injects ----------------------------------------------


def test_an_injected_engine_is_built_opened_used_and_released(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []
    seen: list[object] = []
    built: list[str] = []
    monkeypatch.setattr(
        db_module,
        "_run_alembic_operation",
        lambda connection, *rest: seen.append(connection),
    )

    def engine() -> AsyncEngine:
        built.append("built")
        return cast("AsyncEngine", _RecordingEngine(events))

    app = prepared(tmp_path, engine=engine)

    outcome = invoke(app, "current")

    assert outcome.exit_code == 0, outcome.output
    assert built == ["built"]
    assert events == ["connect", "close", "dispose"]
    assert len(seen) == 1


def test_the_injected_connection_reaches_the_alembic_configuration(
    tmp_path: Path,
) -> None:
    seen: list[Config] = []
    connection = _RecordingConnection([])

    db_module._run_alembic_operation(
        cast("Connection", connection),
        environment(scaffolded(tmp_path)),
        seen.append,
        (),
        {},
    )

    assert seen[0].attributes["connection"] is connection
    assert seen[0].get_main_option("sqlalchemy.url") == FALLBACK


def test_the_engine_is_not_built_when_the_flag_names_a_database(
    tmp_path: Path,
) -> None:
    app = prepared(tmp_path, engine=refuse_engine)

    outcome = invoke(app, "heads", "--url", "sqlite://flag")

    assert outcome.exit_code == 0, outcome.output
    assert outcome.exception is None


# --- revision numbering -------------------------------------------------------


def test_the_next_revision_resumes_after_the_highest_prefix_on_disk(
    tmp_path: Path,
) -> None:
    migrations = scaffolded(tmp_path)
    for name in ("0003_a.py", "0009_b.py", "notes.py"):
        (migrations / "versions" / name).touch()

    assert next_revision_id(environment(migrations)) == "0010"


def test_an_explicit_versions_directory_wins(tmp_path: Path) -> None:
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / "0007_x.py").touch()

    assert next_revision_id(environment(tmp_path), elsewhere) == "0008"


def test_the_prefix_limit_is_reported(tmp_path: Path) -> None:
    migrations = scaffolded(tmp_path)
    (migrations / "versions" / "9999_x.py").touch()

    with pytest.raises(RuntimeError, match="9999"):
        next_revision_id(environment(migrations))


# --- scaffolding through the command ------------------------------------------


def test_init_writes_the_environment_the_factory_was_configured_with(
    tmp_path: Path,
) -> None:
    outcome = invoke(build(tmp_path, model_modules=("apps.models",)), "init")

    assert outcome.exit_code == 0, outcome.output
    written = (tmp_path / "env.py").read_text(encoding="utf-8")
    assert f"from {BASE} import Base" in written
    assert "import apps.models" in written
    assert "created" in outcome.output


def test_a_missing_environment_names_the_program_and_the_directory(
    tmp_path: Path,
) -> None:
    absent = tmp_path / "absent"

    outcome = invoke(build(absent), "current")
    reported = outcome.output + outcome.stderr

    assert outcome.exit_code == 1
    assert f"Alembic environment not found at {absent}" in reported
    assert "run 'fastddd db init'" in reported


# --- against a real database --------------------------------------------------


def test_a_scaffolded_environment_migrates_a_database(tmp_path: Path) -> None:
    migrations = tmp_path / "migrations"
    database = tmp_path / "app.sqlite"
    url = f"sqlite+aiosqlite:///{database}"
    app = prepared(migrations, database_url=lambda: url)

    generated = invoke(app, "revision", "init schema")

    assert generated.exit_code == 0, generated.output
    revisions = sorted((migrations / "versions").glob("0*.py"))
    assert [path.name for path in revisions] == ["0001_init_schema.py"]
    assert "kernel_outbox" in revisions[0].read_text(encoding="utf-8")

    assert invoke(app, "upgrade", "head", "--url", url).exit_code == 0

    with closing(sqlite3.connect(database)) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "select name from sqlite_master where type = 'table'"
            )
        }
    assert {"kernel_inbox", "kernel_outbox"} <= tables


def test_the_offline_mode_prints_sql_without_opening_the_database(
    tmp_path: Path,
) -> None:
    migrations = tmp_path / "migrations"
    scratch = tmp_path / "scratch.sqlite"
    app = prepared(migrations, database_url=lambda: f"sqlite+aiosqlite:///{scratch}")
    assert invoke(app, "revision", "init schema").exit_code == 0
    untouched = tmp_path / "untouched.sqlite"

    printed = invoke(
        app, "upgrade", "head", "--sql", "--url", f"sqlite+aiosqlite:///{untouched}"
    )

    assert printed.exit_code == 0, printed.output
    assert "CREATE TABLE kernel_outbox" in printed.output
    assert not untouched.exists()
