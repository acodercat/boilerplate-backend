from datetime import datetime
from enum import StrEnum

from sqlalchemy import TIMESTAMP, Enum as SAEnum, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserStatus(StrEnum):
    """Only ``ACTIVE`` passes :func:`app.auth.is_user_active`, checked at
    sign-in and on every authenticated request."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class User(Base):
    __tablename__ = "user"
    # Read database-generated values back with ``RETURNING`` on insert and
    # update; otherwise touching ``updated_at`` after a flush would lazy-load,
    # which an async session cannot do.
    __mapper_args__ = {"eager_defaults": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Stable login identifier; ``name`` is the freely editable display name.
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    password_hash: Mapped[str] = mapped_column(String(255))
    status: Mapped[UserStatus] = mapped_column(
        SAEnum(UserStatus, name="user_status"), server_default=UserStatus.ACTIVE.value
    )
    # Every issued token carries the version it was minted against; bumping
    # this revokes all of them at once (see :func:`app.auth.revoke_tokens`).
    token_version: Mapped[int] = mapped_column(Integer, server_default=text("0"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )
