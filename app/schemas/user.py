from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.common.password import NewPassword


class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=255)
    password: NewPassword


class UserUpdate(BaseModel):
    """Partial update; the endpoint applies only the fields that were sent.

    ``None`` is only the "not sent" default. An explicit ``null`` is refused,
    since the column is NOT NULL and would otherwise reach the database.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)

    @field_validator("name")
    @classmethod
    def _not_null(cls, value: str | None) -> str:
        if value is None:
            raise ValueError("must not be null")
        return value


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1)
    new_password: NewPassword


class UserResponse(BaseModel):
    """``status`` is omitted: an authenticated caller is by definition active."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    name: str
    created_at: datetime
    updated_at: datetime
