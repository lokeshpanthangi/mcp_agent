import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session, select

from app.db import get_session
from app.models import AuthToken, User

bearer_scheme = HTTPBearer()


def create_token_for_user(email: str, session: Session) -> tuple[User, str]:
    user = session.exec(select(User).where(User.email == email)).first()
    if user is None:
        user = User(email=email)
        session.add(user)
        session.commit()
        session.refresh(user)

    token = secrets.token_urlsafe(32)
    session.add(AuthToken(token=token, user_id=user.id))
    session.commit()

    return user, token


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    session: Session = Depends(get_session),
) -> User:
    auth_token = session.get(AuthToken, credentials.credentials)
    if auth_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing token")

    user = session.get(User, auth_token.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing token")

    return user
