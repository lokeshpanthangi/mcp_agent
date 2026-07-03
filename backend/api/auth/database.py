from datetime import datetime, timezone

from sqlmodel import Field, Session, SQLModel, select


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True)
    created_at: datetime = Field(default_factory=utcnow)


class AuthToken(SQLModel, table=True):
    token: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    created_at: datetime = Field(default_factory=utcnow)


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
