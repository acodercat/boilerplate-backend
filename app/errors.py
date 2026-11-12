"""Typed application errors.

Wire shape (nested envelope)::

    {"error": {"type": "<snake_case_kind>", "message": "<english>",
               "details": <optional structured payload>}}

The service layer raises :class:`AppError` subclasses directly and the
endpoint layer does **not** catch them: :mod:`app.exception_handlers`
serializes any uncaught one into the envelope above. The class attribute
``status_code`` decides the HTTP status, so there is no reason → status
translation table anywhere else.

``error_type`` is the **stable contract** with clients: they read
``error.type`` and resolve localized copy from their own catalog.
``message`` is an English, developer-facing fallback.

How many kinds is the right number: one per distinct thing the caller
would *do next*, not one per place a check fails. Two conditions that
send someone to the same fix belong under one type.

To add an error kind:

1. Subclass :class:`AppError` here with ``status_code`` + ``error_type``.
2. ``raise NewKindError("english fallback")`` where the condition is
   detected. If the client's sentence needs a number to be actionable,
   pass it in ``details``.
3. Add the localized copy on the client under the same ``error_type``.
"""

from typing import Any, ClassVar

from fastapi import status


class AppError(Exception):
    """Base for every typed application error.

    ``details`` is the same envelope slot the request-validation handler
    fills. Keep its keys stable, name them for what they mean, and put
    nothing in it a user should not read.
    """

    status_code: ClassVar[int] = status.HTTP_400_BAD_REQUEST
    error_type: ClassVar[str] = "bad_request"

    def __init__(self, message: str, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


# --- Authentication -------------------------------------------------------


class UnauthenticatedError(AppError):
    """The bearer token is absent, invalid, expired or revoked. Every cause
    answers identically: telling a caller *why* their token was refused is
    free reconnaissance."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "unauthenticated"


class InvalidCredentialsError(AppError):
    """Sign-in refused. A wrong password, an unknown username and a disabled
    account all answer this, so a lockout never reveals the account exists."""

    status_code = status.HTTP_401_UNAUTHORIZED
    error_type = "invalid_credentials"


# --- Users ----------------------------------------------------------------


class UsernameTakenError(AppError):
    status_code = status.HTTP_409_CONFLICT
    error_type = "username_taken"


class IncorrectPasswordError(AppError):
    """The current password given to authorize a change does not match."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "incorrect_password"


class SamePasswordError(AppError):
    """Refused no-op: a silent accept would still revoke every other
    session for nothing."""

    status_code = status.HTTP_400_BAD_REQUEST
    error_type = "same_password"
