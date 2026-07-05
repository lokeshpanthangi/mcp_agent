from sqlmodel import Session

from agent.prompts import SYSTEM_PROMPT
from config import settings as cfg
from database.models import UserSettings


def get_user_settings(session: Session, user_id: int) -> UserSettings | None:
    return session.get(UserSettings, user_id)


def _get_or_create(session: Session, user_id: int) -> UserSettings:
    return session.get(UserSettings, user_id) or UserSettings(user_id=user_id)


def get_effective_settings(session: Session, user_id: int) -> dict:
    """Resolved values the agent actually runs with (defaults applied).

    Prompt/model fall back to the built-in / .env defaults; the API key falls
    back to the server's shared .env key. The .env key is never exposed to the UI.
    """
    row = get_user_settings(session, user_id)
    prompt = row.system_prompt if row and row.system_prompt else SYSTEM_PROMPT
    api_key = row.ollama_api_key if row and row.ollama_api_key else cfg.OLLAMA_API_KEY
    model = row.model if row and row.model else cfg.OLLAMA_MODEL
    return {"system_prompt": prompt, "api_key": api_key, "model": model}


def get_settings_for_display(session: Session, user_id: int) -> dict:
    """What the settings UI shows. Only the user's OWN custom key is returned
    (empty if unset) — never the server's shared .env key.
    """
    row = get_user_settings(session, user_id)
    prompt = row.system_prompt if row and row.system_prompt else SYSTEM_PROMPT
    api_key = row.ollama_api_key if row and row.ollama_api_key else ""
    model = row.model if row and row.model else cfg.OLLAMA_MODEL
    return {
        "system_prompt": prompt,
        "ollama_api_key": api_key,
        "default_prompt": SYSTEM_PROMPT,
        "model": model,
    }


def save_settings(session: Session, user_id: int, system_prompt: str, ollama_api_key: str) -> None:
    # Empty means "use the default" — store NULL, not an empty string. `model` is
    # managed separately (from the chat bar), so it's left untouched here.
    row = _get_or_create(session, user_id)
    row.system_prompt = system_prompt.strip() or None
    row.ollama_api_key = ollama_api_key.strip() or None
    session.add(row)
    session.commit()


def set_user_model(session: Session, user_id: int, model: str) -> None:
    row = _get_or_create(session, user_id)
    row.model = model.strip() or None
    session.add(row)
    session.commit()
