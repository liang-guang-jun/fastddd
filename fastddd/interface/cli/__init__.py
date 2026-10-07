"""Command-line interface of the application, assembled by a factory.

``create_db_app`` builds the migration sub-application from a
``DbEnvironment`` the caller supplies, and ``scaffold_environment`` writes the
Alembic environment that sub-application then runs. Nothing here reads
configuration of its own, so the same commands serve several schemas and
several deployments with one code path.
"""

from .db import (
    DbEnvironment,
    alembic_config,
    apply_migrations,
    create_db_app,
    next_revision_id,
)
from .scaffold import ScaffoldResult, scaffold_environment

__all__ = [
    "DbEnvironment",
    "ScaffoldResult",
    "alembic_config",
    "apply_migrations",
    "create_db_app",
    "next_revision_id",
    "scaffold_environment",
]
