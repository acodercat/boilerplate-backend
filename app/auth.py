"""Password hashing and access tokens — no HTTP here.

A token carries the user id (``sub``) and the ``token_version`` it was
minted against. Bumping ``user.token_version`` (:func:`revoke_tokens`)
invalidates every token issued before, which is how a password change
signs the account out everywhere. The request-side check lives in
:func:`app.api.dependencies.get_current_user`.
"""

import asyncio
import functools
import logging
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.password import BCRYPT_MAX_BYTES
from app.config import settings
from app.models import User, UserStatus

logger = logging.getLogger(__name__)


# --- Passwords ------------------------------------------------------------


def _hash_password_sync(password: str) -> str:
    salt = bcrypt.gensalt(rounds=settings.bcrypt_rounds)
    return bcrypt.hashpw(password.encode(), salt).decode()


def _verify_password_sync(password: str, password_hash: str) -> bool:
    if len(password.encode()) > BCRYPT_MAX_BYTES:
        # bcrypt 5 raises on such input, and no stored hash can match it.
        return False
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        logger.warning("Malformed bcrypt hash encountered during verification")
        return False


async def hash_password(password: str) -> str:
    """bcrypt off the event loop — a round costs ~250ms at the default cost."""
    return await asyncio.to_thread(_hash_password_sync, password)


async def verify_password(password: str, password_hash: str) -> bool:
    return await asyncio.to_thread(_verify_password_sync, password, password_hash)


@functools.cache
def _absent_account_hash() -> str:
    return _hash_password_sync(secrets.token_urlsafe(16))


async def authenticate_user(db: AsyncSession, username: str, password: str) -> User | None:
    """Return the user iff the password matches, regardless of status.

    An unknown username still runs one bcrypt round against a throwaway
    hash, so response time cannot tell "no such account" from "wrong
    password". Status is the caller's to check via :func:`is_user_active`.
    """
    user = await db.scalar(select(User).where(User.username == username))
    if user is None:
        await verify_password(password, await asyncio.to_thread(_absent_account_hash))
        return None
    return user if await verify_password(password, user.password_hash) else None


def is_user_active(user: User) -> bool:
    return user.status is UserStatus.ACTIVE


# --- Access tokens --------------------------------------------------------


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenClaims:
    user_id: int
    token_version: int


def create_access_token(user: User) -> AccessToken:
    expires_at = datetime.now(UTC) + timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": str(user.id), "token_version": user.token_version, "exp": expires_at}
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return AccessToken(token=token, expires_at=expires_at)


def decode_access_token(token: str) -> TokenClaims | None:
    """Verify signature and expiry; ``None`` on any failure, including
    missing or ill-typed claims, so the caller raises one indistinguishable
    401."""
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            # PyJWT checks ``exp`` only when present; a token without one
            # would never expire.
            options={"require": ["exp", "sub"]},
        )
    except jwt.InvalidTokenError as exc:
        logger.info("Rejected token: %s", type(exc).__name__)
        return None

    sub = payload["sub"]
    token_version = payload.get("token_version")
    if not isinstance(sub, str) or not sub.isdigit() or not isinstance(token_version, int):
        return None
    return TokenClaims(user_id=int(sub), token_version=token_version)


def revoke_tokens(user: User) -> None:
    """Invalidate every token issued to ``user`` so far. Caller commits."""
    user.token_version += 1
