"""Unsaved model instances for offline tests."""

from typing import Any

from app.auth import hash_password
from app.models import User, UserStatus


async def make_user(password: str = "correct horse", **overrides: Any) -> User:
    values = {
        "id": 1,
        "username": "alice",
        "name": "Alice",
        "password_hash": await hash_password(password),
        "status": UserStatus.ACTIVE,
        "token_version": 0,
    }
    return User(**(values | overrides))
