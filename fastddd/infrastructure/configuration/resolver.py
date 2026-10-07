"""Turning a configuration directory into one validated settings object."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ValidationError

from .schemas import ProfileConfig


class ConfigError(RuntimeError):
    """Raised when a configuration source cannot be read or validated."""


class ConfigResolver[TSchema: BaseModel]:
    """Merge a directory's profile files into one validated settings object.

    Every profile names the file it reads: a profile called ``dev`` reads
    ``config.dev.yaml`` inside the directory. The files are merged in ascending
    priority, so a larger priority overrides a smaller one, every later file
    overrides the earlier ones, and ties keep the order the profiles were given
    in. A profile whose file is absent is skipped on purpose, so a deployment
    ships only the layers it actually needs.

    Nothing is implicit: the directory to read, the profiles making it up and
    the model to validate into all come from the caller. There is no default
    file and no default directory, so the mechanism carries no assumption about
    where a project keeps its files or what it calls them.
    """

    def __init__(
        self,
        config_dir: Path,
        profiles: Sequence[ProfileConfig],
        schema: type[TSchema],
    ) -> None:
        """Store the directory to read, the profiles making it up and the model."""
        self._config_dir = config_dir
        self._profiles = profiles
        self._schema = schema

    @property
    def config_dir(self) -> Path:
        """Return the directory every profile file is read from."""
        return self._config_dir

    @property
    def schema(self) -> type[TSchema]:
        """Return the model a successful resolution produces."""
        return self._schema

    def resolve(self) -> TSchema:
        """Merge every profile file and validate the result against the schema.

        Returns:
            An instance of the schema, built from the profiles whose files
            exist. When none of them exists the schema validates an empty
            document, which it is free to accept or refuse.

        Raises:
            ConfigError: A file is not a YAML mapping, or the merged document
                does not satisfy the schema.
        """
        merged: dict[str, Any] = {}
        for profile in sorted(self._profiles, key=lambda profile: profile.priority):
            profile_path = self.config_dir / f"config.{profile.name}.yaml"
            if not profile_path.is_file():
                continue
            merged = self._merge(merged, self._read_yaml(profile_path))
        return self._validate(merged)

    def _validate(self, merged: Mapping[str, Any]) -> TSchema:
        """Validate the merged document, reporting pydantic's error as ours."""
        try:
            return self.schema.model_validate(merged)
        except ValidationError as error:
            raise ConfigError(
                f"Invalid merged application configuration: {error}"
            ) from error

    @staticmethod
    def _merge[TMapping: Mapping[str, Any]](
        base: TMapping, override: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Recursively merge mappings, replacing lists and scalar values wholesale."""
        merged = deepcopy(dict(base))
        for key, override_value in override.items():
            base_value = merged.get(key)
            if isinstance(base_value, Mapping) and isinstance(override_value, Mapping):
                merged[key] = ConfigResolver._merge(base_value, override_value)
            else:
                merged[key] = deepcopy(override_value)
        return merged

    @staticmethod
    def _read_yaml(path: Path) -> dict[str, Any]:
        """Read a required YAML mapping, reporting anything else as a ConfigError.

        An empty file reads as a valid document with no keys, so a profile file
        can be introduced as a placeholder before it carries any setting.
        """
        if not path.is_file():
            raise ConfigError(f"Configuration file does not exist: {path}")
        try:
            with path.open(encoding="utf-8") as stream:
                loaded = yaml.safe_load(stream)
        except yaml.YAMLError as error:
            raise ConfigError(f"Invalid YAML in {path}: {error}") from error
        if loaded is None:
            return {}
        if not isinstance(loaded, dict):
            raise ConfigError(f"Configuration root must be a mapping: {path}")
        return loaded
