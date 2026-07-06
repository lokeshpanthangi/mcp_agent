from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlmodel import Session

from adapters.ollama import sync_models_to_db
from api.deps import get_current_user
from database.db import get_session
from database.models import User
from database.ollama_models import list_models_from_db, model_count
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
    family: str | None = None
    parameter_size: str | None = None
    size: int | None = None


class ModelUpdate(BaseModel):
    model: str


def _rows_to_api(rows) -> list[dict]:
    return [
        {
            "name": r.name,
            "reasoning": r.reasoning,
            "family": r.family,
            "parameter_size": r.parameter_size,
            "size": r.size,
        }
        for r in rows
    ]


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
    q: str | None = Query(default=None, max_length=100),
    refresh: bool = Query(default=False),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Models stored in the DB (synced from Ollama). Pass refresh=true to re-pull."""
    eff = get_effective_settings(session, user.id)
    if refresh or model_count(session) == 0:
        try:
            await sync_models_to_db(session, eff["api_key"])
        except Exception as exc:  # noqa: BLE001
            if model_count(session) == 0:
                raise HTTPException(
                    status.HTTP_502_BAD_GATEWAY, f"Could not sync models: {exc}"
                ) from exc

    rows = list_models_from_db(session, q)
    return _rows_to_api(rows)


@router.post("/models/sync", response_model=list[ModelInfo])
async def sync_models_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    """Force a fresh pull from Ollama into the database."""
    eff = get_effective_settings(session, user.id)
    try:
        await sync_models_to_db(session, eff["api_key"])
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Could not sync models: {exc}") from exc
    return _rows_to_api(list_models_from_db(session))


@router.put("/model", response_model=SettingsResponse)
def set_model_route(
    body: ModelUpdate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    set_user_model(session, user.id, body.model)
    return get_settings_for_display(session, user.id)
