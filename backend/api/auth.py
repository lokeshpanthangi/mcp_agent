import secrets

from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlmodel import Session

from api.deps import get_current_user
from database.db import get_session
from database.models import User
from database.users import create_user, get_user_by_email, save_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr


class LoginResponse(BaseModel):
    token: str
    user_id: int
    email: str


class MeResponse(BaseModel):
    user_id: int
    email: str


def _login(session: Session, email: str) -> tuple[User, str]:
    user = get_user_by_email(session, email) or create_user(session, email)
    token = secrets.token_urlsafe(32)
    save_token(session, token, user.id)
    return user, token


@router.post("/login", response_model=LoginResponse)
def login_route(body: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    user, token = _login(session, body.email)
    return LoginResponse(token=token, user_id=user.id, email=user.email)


@router.get("/me", response_model=MeResponse)
def me_route(user: User = Depends(get_current_user)) -> MeResponse:
    return MeResponse(user_id=user.id, email=user.email)
