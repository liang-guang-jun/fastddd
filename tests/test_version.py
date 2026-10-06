"""Tests for the fastddd package version and entry point."""

import src.fastddd


def test_version_value() -> None:
    """Check that __version__ matches the expected value."""
    assert src.fastddd.__version__ == "0.0.1"
