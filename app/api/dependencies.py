"""Request-scoped dependencies shared by every endpoint module."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import decode_access_token, is_user_active
from app.database import SessionFactory
from app.errors import UnauthenticatedError
from app.models import User


async def get_db() -> AsyncIterator[AsyncSession]:
    """One session per request; nothing commits unless the endpoint does.

    The explicit rollback is what ``async with`` would do anyway — spelled
    out so the contract is obvious and survives a handler that swallows
    an exception before control returns here.
    """
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


DbSession = Annotated[AsyncSession, Depends(get_db)]

# ``auto_error=False`` so a missing header reaches ``get_current_user`` and
# collapses into the same 401 as every other failure.
bearer_scheme = HTTPBearer(auto_error=False)
BearerCredentials = Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)]


async def _resolve_user(db: AsyncSession, credentials: HTTPAuthorizationCredentials | None) -> User:
    """Resolve the caller from the bearer token.

    Absent, malformed, expired or revoked token, unknown or disabled user —
    every refusal raises the same :class:`UnauthenticatedError`; telling a
    caller *why* is free reconnaissance.
    """
    unauthenticated = UnauthenticatedError("Could not validate credentials.")
    if credentials is None:
        raise unauthenticated

    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise unauthenticated

    user = await db.get(User, claims.user_id)
    if user is None or user.token_version != claims.token_version or not is_user_active(user):
        raise unauthenticated
    return user


async def get_current_user(db: DbSession, credentials: BearerCredentials) -> User:
    return await _resolve_user(db, credentials)


async def get_streaming_user(credentials: BearerCredentials) -> User:
    """The caller, for an endpoint whose response outlives the request (SSE).

    ``get_db`` keeps its session checked out until the response ends, which
    for a stream is minutes or hours of one pooled connection doing nothing.
    This opens a session just for the lookup and closes it before the
    stream starts. A streaming endpoint that needs the database later opens
    its own short session the same way.
    """
    async with SessionFactory() as db:
        return await _resolve_user(db, credentials)


CurrentUser = Annotated[User, Depends(get_current_user)]
StreamingUser = Annotated[User, Depends(get_streaming_user)]
