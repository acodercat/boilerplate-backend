"""``app.services.user`` — registration conflicts and password changes."""

from types import SimpleNamespace

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth import verify_password
from app.errors import IncorrectPasswordError, SamePasswordError, UsernameTakenError
from app.services import user as user_service
from tests.factories import make_user


class _FailingFlushSession:
    """A session whose flush violates the named constraint."""

    def __init__(self, constraint_name: str) -> None:
        diag = SimpleNamespace(constraint_name=constraint_name)
        self._error = IntegrityError("INSERT", {}, SimpleNamespace(diag=diag))

    def add(self, _row) -> None:
        pass

    async def flush(self) -> None:
        raise self._error


async def test_register_maps_username_constraint_to_typed_error():
    with pytest.raises(UsernameTakenError):
        await user_service.register(
            _FailingFlushSession("uq_user_username"),
            username="alice",
            name="Alice",
            password="password-one",
        )


async def test_register_lets_other_constraint_violations_through():
    with pytest.raises(IntegrityError):
        await user_service.register(
            _FailingFlushSession("ck_user_something_else"),
            username="alice",
            name="Alice",
            password="password-one",
        )


async def test_change_password_revokes_tokens():
    user = await make_user("old password")
    await user_service.change_password(
        user, current_password="old password", new_password="new password"
    )
    assert user.token_version == 1
    assert await verify_password("new password", user.password_hash)


async def test_change_password_requires_current():
    user = await make_user("old password")
    with pytest.raises(IncorrectPasswordError):
        await user_service.change_password(
            user, current_password="guess", new_password="new password"
        )


async def test_change_password_refuses_no_op():
    user = await make_user("old password")
    with pytest.raises(SamePasswordError):
        await user_service.change_password(
            user, current_password="old password", new_password="old password"
        )
    assert user.token_version == 0
