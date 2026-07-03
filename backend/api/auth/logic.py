from sqlmodel import Session

from api.auth.database import User, create_user, get_user_by_email, save_token
from security.auth import generate_token


def login(session: Session, email: str) -> tuple[User, str]:
    user = get_user_by_email(session, email)
    if user is None:
        user = create_user(session, email)

    token = generate_token()
    save_token(session, token, user.id)
    return user, token


def get_me(user: User) -> User:
    return user
