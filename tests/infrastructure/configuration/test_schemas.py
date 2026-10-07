"""Tests for the schemas a configuration is validated into."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fastddd.infrastructure.configuration.schemas import (
    ApiConfig,
    AppConfig,
    CorsConfig,
    LoggingConfig,
    ProfileConfig,
    StrictModel,
)


def test_the_strict_base_forbids_unknown_fields() -> None:
    assert StrictModel.model_config["extra"] == "forbid"


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(ValidationError, match="extra_forbidden"):
        ApiConfig.model_validate({"app": "fastddd", "factory": "x:y", "typo": True})


def test_a_profile_names_the_overlay_it_reads() -> None:
    profile = ProfileConfig(name="dev")

    assert profile.name == "dev"
    assert profile.priority == 0


def test_a_profile_needs_a_name() -> None:
    with pytest.raises(ValidationError, match="name"):
        ProfileConfig.model_validate({"priority": 10})


def test_a_profile_defaults_to_the_lowest_priority() -> None:
    assert ProfileConfig(name="dev").priority == 0


def test_an_http_api_declares_what_starts_it() -> None:
    api = ApiConfig(
        app="examples.composition.bootstrap",
        factory="create_app",
    )

    assert api.prefix == "/api/v1"
    assert (api.host, api.port) == ("127.0.0.1", 8000)
    assert api.reload is False
    assert api.debug is False


def test_a_port_outside_the_valid_range_is_refused() -> None:
    with pytest.raises(ValidationError, match="less than or equal to 65535"):
        ApiConfig.model_validate({"app": "a", "factory": "b", "port": 70000})


def test_cors_defaults_to_no_origin_and_credentials() -> None:
    cors = CorsConfig()

    assert cors.allow_origins == []
    assert cors.allow_credentials is True


def test_logging_defaults_to_info_in_plain_text() -> None:
    logging = LoggingConfig()

    assert logging.level == "INFO"
    assert logging.json_output is False
    assert logging.colors is False
    assert logging.silenced_loggers == []
    assert logging.log_request_headers is False


def test_an_unknown_logging_level_is_refused() -> None:
    with pytest.raises(ValidationError, match="level"):
        LoggingConfig.model_validate({"level": "LOUD"})


def test_the_default_aggregate_requires_the_api_section() -> None:
    config = AppConfig(api=ApiConfig(app="fastddd", factory="x:y"))

    assert config.logging.level == "INFO"
