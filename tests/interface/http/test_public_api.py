"""Tests for the public surface of the http package."""

from __future__ import annotations

from importlib import import_module

import fastddd.interface.http as http

EXPECTED = {
    "BEARER_PREFIX",
    "TABLE_STATE_ATTRIBUTE",
    "AuthorizationError",
    "BaseExceptionError",
    "ConflictError",
    "CustomCodeBase",
    "CustomError",
    "CustomErrorCode",
    "CustomResponse",
    "CustomResponseCode",
    "ForbiddenError",
    "GatewayError",
    "HTTPError",
    "NotFoundError",
    "RequestError",
    "RequestLoggingMiddleware",
    "ResponseBase",
    "ResponseModel",
    "ResponseSchemaModel",
    "ServerError",
    "StandardResponseCode",
    "StatusTable",
    "TokenError",
    "bearer_token",
    "details_of",
    "password_flow_scheme",
    "register_domain_error_handler",
    "response_base",
    "status_for",
}


def test_the_surface_is_exactly_what_the_package_publishes() -> None:
    assert set(http.__all__) == EXPECTED


def test_the_public_surface_has_no_duplicates() -> None:
    assert len(http.__all__) == len(set(http.__all__))


def test_every_exported_name_resolves_to_an_attribute() -> None:
    missing = [name for name in http.__all__ if not hasattr(http, name)]

    assert missing == []


def test_every_exported_name_is_the_object_its_module_defines() -> None:
    error = import_module("fastddd.interface.http.error")
    middleware = import_module("fastddd.interface.http.middleware")
    response = import_module("fastddd.interface.http.response")
    security = import_module("fastddd.interface.http.security")

    assert http.BaseExceptionError is error.BaseExceptionError
    assert http.register_domain_error_handler is error.register_domain_error_handler
    assert http.status_for is error.status_for
    assert http.details_of is error.details_of
    assert http.RequestLoggingMiddleware is middleware.RequestLoggingMiddleware
    assert http.StandardResponseCode is response.StandardResponseCode
    assert http.response_base is response.response_base
    assert http.password_flow_scheme is security.password_flow_scheme
    assert http.BEARER_PREFIX == security.BEARER_PREFIX
