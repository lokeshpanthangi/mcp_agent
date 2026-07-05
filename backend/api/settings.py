from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlmodel import Session

from adapters.ollama import list_models
from api.deps import get_current_user
from database.db import get_session
from database.models import User
from database.settings import (
    get_effective_settings,
    get_settings_for_display,
    save_settings,
    set_user_model,
)

router = APIRouter(prefix="/settings", tags=["settings"])


class SettingsResponse(BaseModel):
    system_prompt: str
    ollama_api_key: str
    default_prompt: str
    model: str


class SettingsUpdate(BaseModel):
    system_prompt: str
    ollama_api_key: str


class ModelInfo(BaseModel):
    name: str
    reasoning: bool


class ModelUpdate(BaseModel):
    model: str


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


@router.get("/models", response_model=list[ModelInfo])
async def list_models_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Every model available on Ollama (with reasoning flag), via the user's key."""
    eff = get_effective_settings(session, user.id)
    try:
        return await list_models(eff["api_key"])
    except Exception as exc:  # noqa: BLE001 - surface a clean error to the UI
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not list models: {exc}") from exc


@router.put("/model", response_model=SettingsResponse)
def set_model_route(
    body: ModelUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    set_user_model(session, user.id, body.model)
    return get_settings_for_display(session, user.id)
