"""HTTP request logging middleware."""

from __future__ import annotations

from time import perf_counter

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from ...infrastructure.logging import get_logger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request start, completion, endpoint, client, and elapsed time."""

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        """Log request lifecycle information."""
        logger = get_logger("server.http.request")
        started_at = perf_counter()

        client = request.client
        client_host = client.host if client else None
        client_port = client.port if client else None

        endpoint = request.url.path
        method = request.method
        query_params = _safe_query_params(request)

        logger.info(
            "request.started",
            method=method,
            endpoint=endpoint,
            query_params=query_params,
            client_host=client_host,
            client_port=client_port,
        )

        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = (perf_counter() - started_at) * 1000

            logger.exception(
                "request.failed",
                method=method,
                endpoint=endpoint,
                query_params=query_params,
                client_host=client_host,
                client_port=client_port,
                elapsed_ms=round(elapsed_ms, 2),
            )
            raise

        elapsed_ms = (perf_counter() - started_at) * 1000

        logger.info(
            "request.completed",
            method=method,
            endpoint=endpoint,
            query_params=query_params,
            status_code=response.status_code,
            client_host=client_host,
            client_port=client_port,
            elapsed_ms=round(elapsed_ms, 2),
        )

        return response


_SENSITIVE_QUERY_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "password",
        "secret",
        "token",
    }
)


def _safe_query_params(request: Request) -> dict[str, str | list[str]]:
    """Return query parameters for logs without exposing common credentials."""
    params: dict[str, str | list[str]] = {}

    for key, value in request.query_params.multi_items():
        safe_value = "[REDACTED]" if key.lower() in _SENSITIVE_QUERY_KEYS else value
        previous = params.get(key)

        if previous is None:
            params[key] = safe_value
        elif isinstance(previous, list):
            previous.append(safe_value)
        else:
            params[key] = [previous, safe_value]

    return params
