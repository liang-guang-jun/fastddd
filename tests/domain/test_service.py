"""Tests for the domain-service marker base."""

from __future__ import annotations

import inspect

from fastddd.domain.service import DomainService


def test_domain_service_is_a_plain_marker_base() -> None:
    assert not inspect.isabstract(DomainService)
