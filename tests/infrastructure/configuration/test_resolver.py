"""Tests for resolving a configuration directory into settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from pydantic import BaseModel

from fastddd.infrastructure.configuration import (
    AppConfig,
    ConfigError,
    ConfigResolver,
    ProfileConfig,
)


class _ServiceSettings(BaseModel):
    """A service-owned schema, composed without the kernel aggregate."""

    api: dict[str, Any]


class _EmptySettings(BaseModel):
    """A schema that accepts a directory carrying nothing."""

    api: dict[str, Any] | None = None


def _write(directory: Path, name: str, document: Any) -> None:
    (directory / name).write_text(yaml.safe_dump(document), encoding="utf-8")


def _document(**api: Any) -> dict[str, Any]:
    """Return a minimal document that satisfies the kernel schema."""
    return {
        "api": {
            "app": "examples.composition.bootstrap",
            "factory": "create_app",
            **api,
        }
    }


def _profile_file(directory: Path, name: str, **api: Any) -> None:
    """Write the file the profile called ``name`` reads."""
    _write(directory, f"config.{name}.yaml", _document(**api))


# --- the file a profile reads -----------------------------------------------


def test_the_file_name_comes_from_the_profile_name(tmp_path: Path) -> None:
    _profile_file(tmp_path, "dev", app="from-the-file")

    resolved = ConfigResolver(
        tmp_path, [ProfileConfig(name="dev")], AppConfig
    ).resolve()

    assert resolved.api.app == "from-the-file"


def test_a_profile_reads_no_file_it_was_not_named_after(tmp_path: Path) -> None:
    _profile_file(tmp_path, "other")

    with pytest.raises(ConfigError, match="Invalid merged application configuration"):
        ConfigResolver(tmp_path, [ProfileConfig(name="dev")], AppConfig).resolve()


def test_a_profile_without_a_file_is_skipped(tmp_path: Path) -> None:
    _profile_file(tmp_path, "base")

    resolver = ConfigResolver(
        tmp_path,
        [ProfileConfig(name="base"), ProfileConfig(name="absent", priority=10)],
        AppConfig,
    )

    assert resolver.resolve().api.app == "examples.composition.bootstrap"


def test_resolving_a_directory_with_nothing_in_it_is_left_to_the_schema(
    tmp_path: Path,
) -> None:
    resolver = ConfigResolver(tmp_path, [ProfileConfig(name="dev")], _EmptySettings)

    assert resolver.resolve().api is None


def test_the_resolver_reports_the_directory_and_schema_it_was_given() -> None:
    resolver = ConfigResolver(Path("/tmp/settings"), [], _ServiceSettings)

    assert resolver.config_dir == Path("/tmp/settings")
    assert resolver.schema is _ServiceSettings


# --- ordering ---------------------------------------------------------------


def test_profiles_are_merged_in_ascending_priority(tmp_path: Path) -> None:
    _profile_file(tmp_path, "low", app="low")
    _profile_file(tmp_path, "high", app="high")

    resolved = ConfigResolver(
        tmp_path,
        [
            ProfileConfig(name="high", priority=20),
            ProfileConfig(name="low", priority=10),
        ],
        AppConfig,
    ).resolve()

    assert resolved.api.app == "high"


def test_profiles_of_equal_priority_keep_the_order_they_were_given_in(
    tmp_path: Path,
) -> None:
    _profile_file(tmp_path, "first", app="first")
    _profile_file(tmp_path, "second", app="second")

    resolved = ConfigResolver(
        tmp_path,
        [ProfileConfig(name="first"), ProfileConfig(name="second")],
        AppConfig,
    ).resolve()

    assert resolved.api.app == "second"


def test_a_later_profile_only_replaces_what_it_declares(tmp_path: Path) -> None:
    _profile_file(tmp_path, "base")
    _write(tmp_path, "config.dev.yaml", {"logging": {"level": "DEBUG"}})

    resolved = ConfigResolver(
        tmp_path,
        [ProfileConfig(name="base"), ProfileConfig(name="dev", priority=10)],
        AppConfig,
    ).resolve()

    assert resolved.logging.level == "DEBUG"
    assert resolved.api.app == "examples.composition.bootstrap"


def test_resolving_the_same_directory_twice_is_stable(tmp_path: Path) -> None:
    _profile_file(tmp_path, "base")
    _write(tmp_path, "config.dev.yaml", {"logging": {"level": "DEBUG"}})
    resolver = ConfigResolver(
        tmp_path,
        [ProfileConfig(name="base"), ProfileConfig(name="dev", priority=10)],
        AppConfig,
    )

    assert resolver.resolve() == resolver.resolve()


# --- merging ----------------------------------------------------------------


def test_merging_replaces_lists_and_scalars() -> None:
    merged = ConfigResolver._merge({"a": {"b": 1, "c": [1, 2]}}, {"a": {"c": [3]}})

    assert merged == {"a": {"b": 1, "c": [3]}}


def test_merging_keeps_what_only_one_side_declares() -> None:
    assert ConfigResolver._merge({"a": 1}, {"b": 2}) == {"a": 1, "b": 2}


def test_merging_does_not_mutate_its_inputs() -> None:
    base: dict[str, Any] = {"a": {"b": 1}}
    override: dict[str, Any] = {"a": {"c": [1]}}

    ConfigResolver._merge(base, override)

    assert base == {"a": {"b": 1}}
    assert override == {"a": {"c": [1]}}


# --- reading ----------------------------------------------------------------


def test_reading_an_absent_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="does not exist"):
        ConfigResolver._read_yaml(tmp_path / "absent.yaml")


def test_reading_broken_yaml_is_refused(tmp_path: Path) -> None:
    (tmp_path / "broken.yaml").write_text("api: [unclosed", encoding="utf-8")

    with pytest.raises(ConfigError, match="Invalid YAML"):
        ConfigResolver._read_yaml(tmp_path / "broken.yaml")


def test_reading_a_root_that_is_not_a_mapping_is_refused(tmp_path: Path) -> None:
    (tmp_path / "list.yaml").write_text("- item\n", encoding="utf-8")

    with pytest.raises(ConfigError, match="must be a mapping"):
        ConfigResolver._read_yaml(tmp_path / "list.yaml")


def test_an_empty_file_reads_as_a_document_with_no_keys(tmp_path: Path) -> None:
    (tmp_path / "empty.yaml").write_text("", encoding="utf-8")

    assert ConfigResolver._read_yaml(tmp_path / "empty.yaml") == {}


def test_a_document_reads_back_what_it_declares(tmp_path: Path) -> None:
    (tmp_path / "api.yaml").write_text("api:\n  app: fastddd\n", encoding="utf-8")

    assert ConfigResolver._read_yaml(tmp_path / "api.yaml") == {
        "api": {"app": "fastddd"}
    }


# --- validation -------------------------------------------------------------


def test_a_merged_document_that_violates_the_schema_is_reported(
    tmp_path: Path,
) -> None:
    _profile_file(tmp_path, "dev", port=0)

    with pytest.raises(ConfigError, match="Invalid merged application configuration"):
        ConfigResolver(tmp_path, [ProfileConfig(name="dev")], AppConfig).resolve()


def test_the_result_is_built_from_the_supplied_schema(tmp_path: Path) -> None:
    _profile_file(tmp_path, "dev")

    resolved = ConfigResolver(tmp_path, [ProfileConfig(name="dev")], _ServiceSettings)

    assert isinstance(resolved.resolve(), _ServiceSettings)
    assert resolved.resolve().api["app"] == "examples.composition.bootstrap"
