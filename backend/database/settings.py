from sqlmodel import Session

from agent.prompts import SYSTEM_PROMPT
from config import settings as cfg
from database.models import UserSettings


def get_user_settings(session: Session, user_id: int) -> UserSettings | None:
    return session.get(UserSettings, user_id)


def upsert_user_settings(
    session: Session,
    user_id: int,
    system_prompt: str | None,
    ollama_api_key: str | None,
) -> UserSettings:
    row = session.get(UserSettings, user_id)
    if row is None:
        row = UserSettings(user_id=user_id)
    row.system_prompt = system_prompt
    row.ollama_api_key = ollama_api_key
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def get_effective_settings(session: Session, user_id: int) -> dict:
    """Resolved values the agent actually runs with (defaults applied).

    Prompt falls back to the built-in default; the API key falls back to the
    server's shared .env key. The .env key is never exposed to the UI.
    """
    row = get_user_settings(session, user_id)
    prompt = row.system_prompt if row and row.system_prompt else SYSTEM_PROMPT
    api_key = row.ollama_api_key if row and row.ollama_api_key else cfg.OLLAMA_API_KEY
    return {"system_prompt": prompt, "api_key": api_key}


def get_settings_for_display(session: Session, user_id: int) -> dict:
    """What the settings UI shows. Only the user's OWN custom key is returned
    (empty if unset) — never the server's shared .env key.
    """
    row = get_user_settings(session, user_id)
    prompt = row.system_prompt if row and row.system_prompt else SYSTEM_PROMPT
    api_key = row.ollama_api_key if row and row.ollama_api_key else ""
    return {"system_prompt": prompt, "ollama_api_key": api_key, "default_prompt": SYSTEM_PROMPT}


def save_settings(session: Session, user_id: int, system_prompt: str, ollama_api_key: str) -> None:
    # Empty means "use the default" — store NULL, not an empty string.
    prompt = system_prompt.strip() or None
    key = ollama_api_key.strip() or None
    upsert_user_settings(session, user_id, prompt, key)
