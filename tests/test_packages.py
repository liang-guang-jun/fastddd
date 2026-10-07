"""Tests for the package tree: every directory is a documented package."""

from __future__ import annotations

import importlib
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
PACKAGE_ROOT = REPOSITORY_ROOT / "fastddd"


def packages() -> list[tuple[Path, str]]:
    """Every package in the tree, as its directory and its importable name."""
    found = [PACKAGE_ROOT, *sorted(PACKAGE_ROOT.rglob("*"))]

    return [
        (path, ".".join(path.relative_to(REPOSITORY_ROOT).parts))
        for path in found
        if path.is_dir() and "__pycache__" not in path.parts
    ]


def test_every_package_is_marked_with_an_initializer() -> None:
    unmarked = [
        name for path, name in packages() if not (path / "__init__.py").is_file()
    ]

    assert unmarked == []


def test_every_package_is_importable_and_documents_itself() -> None:
    undocumented = [
        name for _, name in packages() if not importlib.import_module(name).__doc__
    ]

    assert undocumented == []
