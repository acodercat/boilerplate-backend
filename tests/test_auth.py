"""Passwords, access tokens and the ``CurrentUser`` dependency — offline,
against a stand-in session."""

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.dependencies import get_current_user
from app.auth import (
    authenticate_user,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.common.password import BCRYPT_MAX_BYTES
from app.config import settings
from app.errors import UnauthenticatedError
from app.models import User, UserStatus
from tests.factories import make_user


@dataclass
class _FakeSession:
    """Answers ``get`` / ``scalar`` from a fixed set of users."""

    users: dict[int, User] = field(default_factory=dict)

    async def get(self, _model, user_id: int) -> User | None:
        return self.users.get(user_id)

    async def scalar(self, _stmt) -> User | None:
        return None


def _encode(payload: dict[str, Any], key: str = settings.secret_key) -> str:
    return jwt.encode(payload, key, algorithm=settings.jwt_algorithm)


def _in_an_hour() -> datetime:
    return datetime.now(UTC) + timedelta(hours=1)


# --- passwords ------------------------------------------------------------


async def test_password_round_trip():
    password_hash = await hash_password("correct horse")
    assert await verify_password("correct horse", password_hash)
    assert not await verify_password("wrong horse", password_hash)


async def test_password_past_bcrypt_bound_never_matches():
    password_hash = await hash_password("x" * BCRYPT_MAX_BYTES)
    assert not await verify_password("x" * (BCRYPT_MAX_BYTES + 1), password_hash)


async def test_malformed_hash_does_not_raise():
    assert not await verify_password("anything", "not-a-bcrypt-hash")


async def test_unknown_username_is_refused():
    assert await authenticate_user(_FakeSession(), "nobody", "pw") is None


# --- tokens ---------------------------------------------------------------


async def test_token_round_trip():
    user = await make_user(token_version=3)
    claims = decode_access_token(create_access_token(user).token)
    assert claims is not None
    assert (claims.user_id, claims.token_version) == (1, 3)


@pytest.mark.parametrize(
    "token",
    [
        pytest.param(
            _encode(
                {"sub": "1", "token_version": 0, "exp": _in_an_hour()},
                key="another-key-of-at-least-32-characters",
            ),
            id="wrong-signature",
        ),
        pytest.param(
            _encode(
                {"sub": "1", "token_version": 0, "exp": datetime.now(UTC) - timedelta(seconds=1)}
            ),
            id="expired",
        ),
        pytest.param(_encode({"sub": "1", "token_version": 0}), id="no-expiry"),
        pytest.param(
            _encode({"sub": "alice", "token_version": 0, "exp": _in_an_hour()}),
            id="non-numeric-sub",
        ),
        pytest.param(_encode({"sub": "1", "exp": _in_an_hour()}), id="no-token-version"),
        pytest.param("not-a-jwt", id="garbage"),
    ],
)
def test_invalid_tokens_are_refused(token):
    assert decode_access_token(token) is None


# --- CurrentUser ----------------------------------------------------------


def _bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


async def test_current_user_resolves():
    user = await make_user()
    token = create_access_token(user).token
    assert await get_current_user(_FakeSession({1: user}), _bearer(token)) is user


@pytest.mark.parametrize("case", ["missing_header", "revoked", "disabled", "deleted"])
async def test_current_user_refusals_are_identical(case):
    user = await make_user()
    db = _FakeSession({1: user})
    credentials: HTTPAuthorizationCredentials | None = _bearer(create_access_token(user).token)
    if case == "missing_header":
        credentials = None
    elif case == "revoked":
        user.token_version += 1
    elif case == "disabled":
        user.status = UserStatus.DISABLED
    elif case == "deleted":
        db.users.clear()

    with pytest.raises(UnauthenticatedError):
        await get_current_user(db, credentials)
