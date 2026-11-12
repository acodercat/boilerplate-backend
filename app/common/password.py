"""The bcrypt input bound shared by every schema that accepts a new password."""

from typing import Annotated

from pydantic import AfterValidator, Field

BCRYPT_MAX_BYTES = 72
"""bcrypt reads at most 72 bytes, and bcrypt 5 raises on longer input rather
than truncating it. The bound is in UTF-8 bytes, not characters: 25 CJK
characters are 75 bytes."""


def fits_bcrypt(password: str) -> str:
    """Return ``password`` unchanged, or refuse it past the byte bound."""
    if len(password.encode()) > BCRYPT_MAX_BYTES:
        raise ValueError(f"Password must be at most {BCRYPT_MAX_BYTES} bytes in UTF-8")
    return password


NewPassword = Annotated[str, Field(min_length=8), AfterValidator(fits_bcrypt)]
"""A password being set. Not for sign-in, which must accept whatever was set
before a policy change."""
