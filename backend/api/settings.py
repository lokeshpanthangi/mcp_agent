from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session

from api.deps import get_current_user
from database.db import get_session
from database.models import User
from database.settings import get_settings_for_display, save_settings

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    system_prompt: str
    ollama_api_key: str
    default_prompt: str


class SettingsUpdate(BaseModel):
    system_prompt: str
    ollama_api_key: str


@router.get("", response_model=SettingsResponse)
def get_settings_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    return get_settings_for_display(session, user.id)


@router.put("", response_model=SettingsResponse)
def update_settings_route(
    body: SettingsUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    save_settings(session, user.id, body.system_prompt, body.ollama_api_key)
    return get_settings_for_display(session, user.id)
