from fastapi import APIRouter

from app.api.dependencies import DbSession
from app.auth import authenticate_user, create_access_token, is_user_active
from app.errors import InvalidCredentialsError
from app.schemas.auth import AccessTokenResponse, SignInRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/access-tokens")
async def sign_in(db: DbSession, body: SignInRequest) -> AccessTokenResponse:
    """Exchange a username and password for an access token.

    An unknown username, a wrong password and a disabled account all get
    the same 401, so a lockout never confirms that an account exists.
    """
    user = await authenticate_user(db, body.username, body.password)
    if user is None or not is_user_active(user):
        raise InvalidCredentialsError("Incorrect username or password.")
    token = create_access_token(user)
    return AccessTokenResponse(access_token=token.token, expires_at=token.expires_at)
