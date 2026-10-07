"""How the interface layer reports a failure.

The module holds two vocabularies, because they answer two different questions.

``BaseExceptionError`` and its subclasses are what a route raises when the failure
belongs to the interface itself: a malformed request, a resource that is not
there, a token that cannot be used. FastAPI answers those directly.

A domain failure is answered by ``register_domain_error_handler``. Each context
owns the status table of its own error vocabulary, but they all build on the same
kernel error hierarchy, and an application serves several contexts at once.
FastAPI keeps one handler per exception class, so two contexts registering
``DomainError`` would silently replace one another's statuses. This module keeps
exactly one handler per application and resolves a failure against every table
the contexts registered. A failure is matched by concrete class across all tables
first, then by ``isinstance``, so the most specific rule wins no matter which
context attached its table first.
"""

from __future__ import annotations

from http import HTTPStatus
from typing import Any, cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.background import BackgroundTask

from ...domain.error import DomainError
from .response import CustomErrorCode, StandardResponseCode


class BaseExceptionError(Exception):
    """Base exception for application-level errors."""

    code: int

    def __init__(
        self,
        *,
        msg: str | None = None,
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize an application-level exception."""
        self.msg = msg
        self.data = data
        self.background = background
        super().__init__(msg)


class HTTPError(HTTPException):
    """Base exception for HTTP errors handled directly by FastAPI."""

    def __init__(
        self,
        *,
        code: int,
        msg: Any = None,
        headers: dict[str, Any] | None = None,
    ) -> None:
        """Initialize an HTTP exception."""
        super().__init__(status_code=code, detail=msg, headers=headers)


class CustomError(BaseExceptionError):
    """Application error defined by a custom error code."""

    def __init__(
        self,
        *,
        error: CustomErrorCode,
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize an exception from a custom error definition."""
        self.code = error.code
        super().__init__(msg=error.msg, data=data, background=background)


class RequestError(BaseExceptionError):
    """Error raised for an invalid client request."""

    def __init__(
        self,
        *,
        code: int = StandardResponseCode.HTTP_400,
        msg: str = "Bad Request",
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize a client request error."""
        self.code = code
        super().__init__(msg=msg, data=data, background=background)


class ForbiddenError(BaseExceptionError):
    """Error raised when access to a resource is forbidden."""

    code = StandardResponseCode.HTTP_403

    def __init__(
        self,
        *,
        msg: str = "Forbidden",
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize a forbidden-access error."""
        super().__init__(msg=msg, data=data, background=background)


class NotFoundError(BaseExceptionError):
    """Error raised when the requested resource does not exist."""

    code = StandardResponseCode.HTTP_404

    def __init__(
        self,
        *,
        msg: str = "Not Found",
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize a resource-not-found error."""
        super().__init__(msg=msg, data=data, background=background)


class ServerError(BaseExceptionError):
    """Error raised for an unexpected internal server failure."""

    code = StandardResponseCode.HTTP_500

    def __init__(
        self,
        *,
        msg: str = "Internal Server Error",
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize an internal server error."""
        super().__init__(msg=msg, data=data, background=background)


class GatewayError(BaseExceptionError):
    """Error raised when an upstream service returns an invalid response."""

    code = StandardResponseCode.HTTP_502

    def __init__(
        self,
        *,
        msg: str = "Bad Gateway",
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize a gateway error."""
        super().__init__(msg=msg, data=data, background=background)


class AuthorizationError(BaseExceptionError):
    """Error raised when the caller lacks the required permissions."""

    code = StandardResponseCode.HTTP_403

    def __init__(
        self,
        *,
        msg: str = "Permission Denied",
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize an authorization error."""
        super().__init__(msg=msg, data=data, background=background)


class TokenError(HTTPError):
    """Authentication error caused by a missing or invalid access token."""

    code = StandardResponseCode.HTTP_401

    def __init__(
        self,
        *,
        msg: str = "Not Authenticated",
        headers: dict[str, Any] | None = None,
    ) -> None:
        """Initialize an authentication token error."""
        super().__init__(
            code=self.code,
            msg=msg,
            headers=headers or {"WWW-Authenticate": "Bearer"},
        )


class ConflictError(BaseExceptionError):
    """Error raised when the request conflicts with the current resource state."""

    code = StandardResponseCode.HTTP_409

    def __init__(
        self,
        *,
        msg: str = "Conflict",
        data: Any = None,
        background: BackgroundTask | None = None,
    ) -> None:
        """Initialize a resource conflict error."""
        super().__init__(msg=msg, data=data, background=background)


# Domain failures: one handler per application, many contexts' status tables.

type StatusTable = tuple[tuple[type[DomainError], int], ...]

TABLE_STATE_ATTRIBUTE = "domain_error_status_tables"


def register_domain_error_handler(app: FastAPI, table: StatusTable) -> None:
    """Append a context's status table and make sure the handler is installed.

    Within one table the first matching rule wins, so a context must list
    specific errors before their base classes.
    """
    tables: list[StatusTable] = [
        *getattr(app.state, TABLE_STATE_ATTRIBUTE, ()),
        table,
    ]
    setattr(app.state, TABLE_STATE_ATTRIBUTE, tables)

    if DomainError not in app.exception_handlers:
        app.add_exception_handler(DomainError, _domain_error)


def status_for(app: FastAPI, error: DomainError) -> int:
    """Return the HTTP status the registered tables assign to ``error``.

    An exact class match in any table outranks an inherited one, so a context
    that maps a specific application error keeps that mapping even though
    another context's table also covers its base class.
    """
    tables: tuple[StatusTable, ...] = getattr(app.state, TABLE_STATE_ATTRIBUTE, ())

    for error_type, status in (rule for table in tables for rule in table):
        if type(error) is error_type:
            return status

    for error_type, status in (rule for table in tables for rule in table):
        if isinstance(error, error_type):
            return status

    return StandardResponseCode.HTTP_400


async def _domain_error(request: Request, exc: Exception) -> JSONResponse:
    """Return the status of the failure with the standard response envelope."""
    error = cast(DomainError, exc)
    status = status_for(request.app, error)
    message = str(error) or HTTPStatus(status).phrase

    return JSONResponse(
        status_code=status,
        content={"code": status, "msg": message, "data": details_of(error)},
    )


def details_of(error: DomainError) -> dict[str, str] | None:
    """Return what a caller needs in order to act on the failure, or ``None``.

    A failure that names itself travels in ``data`` so a caller can branch on the name
    without matching the message, which is prose and belongs to the context that wrote it.
    """
    return {"error": error.code} if error.code else None
