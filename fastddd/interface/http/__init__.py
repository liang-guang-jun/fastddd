"""The HTTP side of the interface layer: envelope, errors, logging, and auth.

These modules translate between the transport and the application. They are
FastAPI-shaped on purpose, so an application composes them while nothing in the
kernel depends on them.

The error vocabulary is what a route raises; ``register_domain_error_handler``
is what turns a domain failure into a response, and it keeps exactly one
handler per application so several contexts can map their own statuses.
"""

from .error import (
    TABLE_STATE_ATTRIBUTE,
    AuthorizationError,
    BaseExceptionError,
    ConflictError,
    CustomError,
    ForbiddenError,
    GatewayError,
    HTTPError,
    NotFoundError,
    RequestError,
    ServerError,
    StatusTable,
    TokenError,
    details_of,
    register_domain_error_handler,
    status_for,
)
from .middleware import RequestLoggingMiddleware
from .response import (
    CustomCodeBase,
    CustomErrorCode,
    CustomResponse,
    CustomResponseCode,
    ResponseBase,
    ResponseModel,
    ResponseSchemaModel,
    StandardResponseCode,
    response_base,
)
from .security import BEARER_PREFIX, bearer_token, password_flow_scheme

__all__ = [
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
]
