from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class SignInRequest(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    # No length policy here: sign-in must accept any password that was valid
    # when it was set.
    password: str = Field(min_length=1)


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: datetime
