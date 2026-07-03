from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlmodel import Session

from api.auth.database import User
from api.auth.logic import get_me, login
from database import get_session
from security.auth import get_current_user

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


@router.post("/login", response_model=LoginResponse)
def login_route(body: LoginRequest, session: Session = Depends(get_session)) -> LoginResponse:
    user, token = login(session, body.email)
    return LoginResponse(token=token, user_id=user.id, email=user.email)


@router.get("/me", response_model=MeResponse)
def me_route(user: User = Depends(get_current_user)) -> MeResponse:
    result = get_me(user)
    return MeResponse(user_id=result.id, email=result.email)
