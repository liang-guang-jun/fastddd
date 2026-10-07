"""How a caller presents an access token, as the published contract states it.

The API speaks OAuth2: a caller exchanges credentials for a bearer token at a
token endpoint, and every guarded operation declares that it needs one. Declaring
the standard scheme is what puts the *Authorize* button on the documentation page
and lets the page run the password flow itself, so a reader can try a guarded
operation without leaving the page.

``auto_error`` is off on purpose: refusing a request is the gateway's job, and the
gateway answers with the project's error envelope and the reason it refused. An
absent or unprefixed header is therefore reported by the caller gate rather than
by FastAPI's own body.
"""

from __future__ import annotations

from fastapi.security import OAuth2PasswordBearer

BEARER_PREFIX = "bearer "


def password_flow_scheme(*, token_url: str) -> OAuth2PasswordBearer:
    """Return the bearer scheme of an API whose tokens come from ``token_url``."""
    return OAuth2PasswordBearer(tokenUrl=token_url, auto_error=False)


def bearer_token(value: str) -> str:
    """Return the token a header value carries, with the scheme removed.

    A bearer credential is ``Bearer <token>``; a deployment that delivers the
    token in a header of its own may omit the scheme, so both forms are accepted.
    """
    presented = value.strip()
    if presented.lower().startswith(BEARER_PREFIX):
        return presented[len(BEARER_PREFIX) :].strip()

    return presented
