"""Convert every exception path into the error envelope.

    {"error": {"type": "<snake_case>", "message": "<english>",
               "details": <optional structured payload>}}

- :func:`app_error_handler` — typed :class:`~app.errors.AppError` raises.
- :func:`http_exception_handler` — bare ``HTTPException`` from the
  framework (unknown route, wrong method) or a quick exit in an endpoint;
  ``type`` is derived from the status phrase.
- :func:`integrity_error_handler` / :func:`database_error_handler` —
  database escapes that bypass the typed hierarchy.
- :func:`validation_error_handler` — request validation; per-field
  breakdown in ``details``.
- :class:`UnexpectedErrorMiddleware` — the last-resort 500.

:func:`install_error_handlers` registers all of them in one call, so every
app built by :func:`app.asgi.create_app` answers errors identically.
"""

import logging
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.errors import AppError

logger = logging.getLogger(__name__)


def error_response(
    status_code: int,
    *,
    type_: str,
    message: str,
    details: object | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    """Build an envelope response. ``details`` is omitted when ``None`` so
    responses carry no explicit nulls."""
    error: dict[str, Any] = {"type": type_, "message": message}
    if details is not None:
        error["details"] = details
    return JSONResponse(status_code=status_code, content={"error": error}, headers=headers)


def _status_phrase(code: int) -> str:
    """The standard reason phrase, or ``"HTTP Error"`` for a code outside
    :class:`HTTPStatus`."""
    try:
        return HTTPStatus(code).phrase
    except ValueError:
        return "HTTP Error"


def _status_to_type(code: int) -> str:
    """``404`` → ``"not_found"``, ``401`` → ``"unauthorized"``."""
    return _status_phrase(code).lower().replace(" ", "_").replace("-", "_")


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    # RFC 7235 requires a challenge on every 401. Bearer is the only scheme
    # this API speaks, so the header is added here rather than remembered
    # per error class.
    headers = (
        {"WWW-Authenticate": "Bearer"} if exc.status_code == status.HTTP_401_UNAUTHORIZED else None
    )
    return error_response(
        exc.status_code,
        type_=exc.error_type,
        message=exc.message,
        details=exc.details,
        headers=headers,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """A ``dict`` detail is a structured payload and goes under ``details``
    with the status phrase as message; anything else is the message."""
    type_ = _status_to_type(exc.status_code)
    if isinstance(exc.detail, dict):
        return error_response(
            exc.status_code,
            type_=type_,
            message=_status_phrase(exc.status_code),
            details=exc.detail,
            headers=exc.headers,
        )
    return error_response(
        exc.status_code, type_=type_, message=str(exc.detail), headers=exc.headers
    )


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Integrity error: %s", exc)
    return error_response(
        status.HTTP_409_CONFLICT,
        type_="conflict",
        message="The request violates a database constraint.",
    )


async def database_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("Database error: %s", exc, exc_info=exc)
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        type_="database_error",
        message="An error occurred while processing the request.",
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Clients toast ``error.message``; forms read the flat per-field list in
    ``error.details``."""
    details = [
        {
            "location": list(err["loc"]),
            "message": err["msg"],
            "type": err["type"],
            **({"context": _jsonable_context(err["ctx"])} if "ctx" in err else {}),
        }
        for err in exc.errors()
    ]
    return error_response(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        type_="validation_error",
        message="Request failed validation.",
        details=details,
    )


def _jsonable_context(ctx: dict[str, Any]) -> dict[str, Any]:
    """Make a pydantic error ``ctx`` JSON-safe.

    Constraint contexts are scalars (``{"ge": 1}``), but a custom validator
    that raises ``ValueError`` arrives as ``{"error": ValueError(...)}`` — a
    live exception that would crash serialization and turn the 422 into a
    500.
    """
    return {
        key: value if isinstance(value, str | int | float | bool | None) else str(value)
        for key, value in ctx.items()
    }


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unexpected error: %s", exc)
    return error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        type_="internal_server_error",
        message="An unexpected error occurred.",
    )


class UnexpectedErrorMiddleware:
    """Answer an exception no handler took, from inside the other middleware.

    Starlette runs an ``Exception`` handler in its outermost middleware, so
    that 500 would carry no CORS headers and a browser would report a
    network error instead of the envelope. A response that has already
    started has nothing left to answer with, so its exception propagates.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = False

        async def tracking_send(message: Message) -> None:
            nonlocal started
            started = started or message["type"] == "http.response.start"
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception as exc:
            if started:
                raise
            response = await unexpected_error_handler(Request(scope), exc)
            await response(scope, receive, send)


def install_error_handlers(app: FastAPI) -> None:
    """Register every handler above, plus the middleware for what none of
    them takes.

    Starlette dispatches on the exception class (most specific registered
    base wins), so registration order does not matter — but the middleware
    must be added before any other so that it runs innermost.
    """
    # Each ``ignore``: Starlette types a handler as taking ``Exception``,
    # while these narrow to the class they are registered for. Starlette
    # dispatches on that class, so the narrowing is exactly right at runtime.
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(SQLAlchemyError, database_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]
    app.add_middleware(UnexpectedErrorMiddleware)
