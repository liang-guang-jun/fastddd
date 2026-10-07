"""Tests for the fastddd package version and entry point."""

import fastddd


def test_version_value() -> None:
    """Check that __version__ matches the expected value."""
    assert fastddd.__version__ == "0.0.1"
