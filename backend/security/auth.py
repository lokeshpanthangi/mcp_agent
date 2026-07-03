import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from api.auth.database import User, get_user_by_token
from database import get_session

bearer_scheme = HTTPBearer()


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    user = get_user_by_token(session, credentials.credentials)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing token")
    return user
