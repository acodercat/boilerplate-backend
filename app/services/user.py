"""User account rules. Functions here flush and never commit — the endpoint
owns the transaction, so a refusal anywhere rolls the whole request back."""

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import hash_password, revoke_tokens, verify_password
from app.errors import IncorrectPasswordError, SamePasswordError, UsernameTakenError
from app.models import User

_USERNAME_CONSTRAINT = "uq_user_username"


async def register(db: AsyncSession, *, username: str, name: str, password: str) -> User:
    """Create an active account.

    Uniqueness is left to the constraint rather than checked first: a
    read-then-insert would still race. Only a violation of *that*
    constraint means the name is taken; any other propagates as the
    generic 409.
    """
    user = User(username=username, name=name, password_hash=await hash_password(password))
    db.add(user)
    try:
        await db.flush()
    except IntegrityError as exc:
        if _violated_constraint(exc) == _USERNAME_CONSTRAINT:
            raise UsernameTakenError(f"Username {username!r} is already taken.") from exc
        raise
    return user


async def change_password(user: User, *, current_password: str, new_password: str) -> None:
    """Replace the password and sign the account out everywhere."""
    if not await verify_password(current_password, user.password_hash):
        raise IncorrectPasswordError("The current password is incorrect.")
    if current_password == new_password:
        raise SamePasswordError("The new password must differ from the current one.")
    user.password_hash = await hash_password(new_password)
    revoke_tokens(user)


def _violated_constraint(exc: IntegrityError) -> str | None:
    """The constraint Postgres reported, as named by ``Base``'s naming convention."""
    diag = getattr(exc.orig, "diag", None)
    return getattr(diag, "constraint_name", None)
