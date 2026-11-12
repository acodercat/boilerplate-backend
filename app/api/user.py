"""User accounts — the reference slice.

- ``POST  /users``         — register.
- ``GET   /users``         — list accounts, paginated.
- ``GET   /me``            — the caller.
- ``PATCH /me``            — update the caller's profile.
- ``PUT   /me/password``   — change the caller's password.

A new resource copies this shape: rules in ``app/services/``, plain reads
inline, the endpoint commits once at the end.
"""

from typing import Annotated

from fastapi import APIRouter, Query, status
from sqlalchemy import func, select

from app.api.dependencies import CurrentUser, DbSession
from app.common.pagination import paginate
from app.models import User
from app.schemas.pagination import PaginatedResponse, PaginationMeta
from app.schemas.user import PasswordChange, UserCreate, UserResponse, UserUpdate
from app.services import user as user_service

router = APIRouter(tags=["users"])


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def register(db: DbSession, body: UserCreate) -> UserResponse:
    user = await user_service.register(
        db, username=body.username, name=body.name, password=body.password
    )
    await db.commit()
    return UserResponse.model_validate(user)


@router.get("/users")
async def list_users(
    db: DbSession,
    _: CurrentUser,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> PaginatedResponse[UserResponse]:
    """Any signed-in caller may list accounts. Tighten this before relying on
    it — it is here to show the pagination pattern."""
    total = await db.scalar(select(func.count()).select_from(User)) or 0
    rows = await db.scalars(paginate(select(User).order_by(User.id), page, page_size))
    return PaginatedResponse(
        items=[UserResponse.model_validate(row) for row in rows],
        meta=PaginationMeta(total=total, page=page, page_size=page_size),
    )


@router.get("/me")
async def read_me(user: CurrentUser) -> UserResponse:
    return UserResponse.model_validate(user)


@router.patch("/me")
async def update_me(db: DbSession, user: CurrentUser, body: UserUpdate) -> UserResponse:
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(user, field, value)
    await db.commit()
    return UserResponse.model_validate(user)


@router.put("/me/password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(db: DbSession, user: CurrentUser, body: PasswordChange) -> None:
    """Every token issued before this call stops working, this one included."""
    await user_service.change_password(
        user, current_password=body.current_password, new_password=body.new_password
    )
    await db.commit()
