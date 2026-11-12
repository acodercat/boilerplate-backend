"""Every model, imported here so ``Base.metadata`` is complete for alembic."""

from app.models.user import User, UserStatus

__all__ = ["User", "UserStatus"]
