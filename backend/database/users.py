from sqlmodel import Session, select

from database.models import AuthToken, User


def get_user_by_email(session: Session, email: str) -> User | None:
    return session.exec(select(User).where(User.email == email)).first()


def create_user(session: Session, email: str) -> User:
    user = User(email=email)
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def save_token(session: Session, token: str, user_id: int) -> AuthToken:
    auth_token = AuthToken(token=token, user_id=user_id)
    session.add(auth_token)
    session.commit()
    return auth_token


def get_user_by_token(session: Session, token: str) -> User | None:
    auth_token = session.get(AuthToken, token)
    if auth_token is None:
        return None
    return session.get(User, auth_token.user_id)
