"""Tests for the Alembic environment scaffolder."""

from __future__ import annotations

import inspect
from pathlib import Path

from fastddd.interface.cli.scaffold import (
    ScaffoldResult,
    scaffold_environment,
)

BASE = "fastddd.infrastructure.persistence.sqlalchemy.models"
EXPECTED_FILES = ["env.py", "script.py.mako", ".gitkeep"]


def test_a_run_reports_every_file_it_wrote(tmp_path: Path) -> None:
    result = scaffold_environment(tmp_path, base_module=BASE, model_modules=[])

    assert isinstance(result, ScaffoldResult)
    assert [path.name for path in result.written] == EXPECTED_FILES
    assert result.kept == []
    assert (tmp_path / "versions").is_dir()
    assert (tmp_path / "versions" / ".gitkeep").is_file()


def test_the_environment_imports_the_metadata_root_it_was_given(
    tmp_path: Path,
) -> None:
    scaffold_environment(
        tmp_path, base_module="apps.persistence.models", model_modules=[]
    )

    assert "from apps.persistence.models import Base" in (
        tmp_path / "env.py"
    ).read_text(encoding="utf-8")


def test_every_model_module_is_imported_so_autogenerate_can_see_it(
    tmp_path: Path,
) -> None:
    scaffold_environment(
        tmp_path,
        base_module=BASE,
        model_modules=["apps.catalog.models", "apps.iam.models"],
    )

    written = (tmp_path / "env.py").read_text(encoding="utf-8")
    assert "from fastddd.infrastructure.persistence.sqlalchemy.models import Base" in (
        written
    )
    assert "import apps.catalog.models" in written
    assert "import apps.iam.models" in written


def test_the_metadata_slot_never_survives_into_the_written_environment(
    tmp_path: Path,
) -> None:
    scaffold_environment(tmp_path, base_module=BASE, model_modules=["apps.models"])

    assert "__METADATA_IMPORTS__" not in (tmp_path / "env.py").read_text(
        encoding="utf-8"
    )


def test_the_written_environment_is_valid_python_even_without_models(
    tmp_path: Path,
) -> None:
    scaffold_environment(tmp_path, base_module=BASE, model_modules=[])

    compile((tmp_path / "env.py").read_text(encoding="utf-8"), "env.py", "exec")


def test_existing_files_are_kept_unless_forced(tmp_path: Path) -> None:
    scaffold_environment(tmp_path, base_module=BASE, model_modules=[])
    (tmp_path / "env.py").write_text("# edited by hand\n", encoding="utf-8")

    again = scaffold_environment(tmp_path, base_module=BASE, model_modules=[])

    assert [path.name for path in again.kept] == EXPECTED_FILES
    assert again.written == []
    assert (tmp_path / "env.py").read_text(encoding="utf-8") == "# edited by hand\n"


def test_a_forced_run_overwrites_what_was_there(tmp_path: Path) -> None:
    scaffold_environment(tmp_path, base_module=BASE, model_modules=[])
    (tmp_path / "env.py").write_text("# edited by hand\n", encoding="utf-8")

    forced = scaffold_environment(
        tmp_path, base_module=BASE, model_modules=[], force=True
    )

    assert [path.name for path in forced.written] == EXPECTED_FILES
    assert forced.kept == []
    assert "target_metadata" in (tmp_path / "env.py").read_text(encoding="utf-8")


def test_the_metadata_inputs_are_required() -> None:
    parameters = inspect.signature(scaffold_environment).parameters

    for name in ("base_module", "model_modules"):
        assert parameters[name].default is inspect.Parameter.empty, name
