"""The console entry point: the migration commands, wired to this service.

Run it with ``uv run python -m examples.cli db upgrade head``. A real service
names this module in its own ``[project.scripts]``; the kernel deliberately ships
no entry point of its own.

The factory is handed all eight inputs on purpose. It reads no configuration and
knows no project layout, so the directory Alembic scaffolding lands in, the
revision naming scheme, the database URL, the environment variable that overrides
it, the program name that appears in errors, the metadata root autogenerate
imports and the model modules it is allowed to see are all decisions made here.
"""

from __future__ import annotations

import re
from pathlib import Path

import typer

from fastddd.interface import create_db_app

from .composition.container import AppContainer

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
"""Where this service's Alembic environment lives.

Inside a ``migrations`` directory on purpose: that is the tree Ruff and mypy are
configured to leave alone, because Alembic generates irregular module names and
empty revisions that no linter should reject.
"""

REVISION_PATTERN = re.compile(r"^(?P<number>\d{4})(?:_|$)")
"""How ``db revision`` numbers its files: four digits, then an underscore.

The pattern is the project's, not the kernel's -- another project numbers them
with a date prefix and passes a different regex.
"""

app = typer.Typer(help="example service", no_args_is_help=True)
"""The service's command line. ``db`` is one sub-application of it."""

container = AppContainer()
"""The container declaring the db commands resolves against.

Building it resolves nothing: a declarative container is lazy, so importing this
module costs one object and no connection.
"""

app.add_typer(
    create_db_app(
        migrations=MIGRATIONS_DIR,
        revision_pattern=REVISION_PATTERN,
        # Precedence is ``--url``, then ``EXAMPLE_DATABASE_URL``, then this. The
        # kernel asks for a *callable*, so naming the database from configuration
        # stays this service's decision.
        database_url=lambda: str(container.database().url()),
        env_var="EXAMPLE_DATABASE_URL",
        program_name="example",
        # The metadata root, and every module whose tables autogenerate may see.
        # A model module left out of this tuple is invisible, and its tables
        # silently become an empty revision.
        base_module="fastddd.infrastructure.persistence.sqlalchemy.models",
        model_modules=("examples.counter.persistence",),
        # ``None`` lets Alembic open its own connection from the URL above. Pass
        # a factory here when the credentials cannot be written down -- an
        # endpoint that mints a token per connection -- and the connection built
        # from it is used for the whole command.
        engine=None,
    ),
    name="db",
)


if __name__ == "__main__":
    app()
