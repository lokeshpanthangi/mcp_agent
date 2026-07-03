from sqlmodel import Field, Session, SQLModel


class UserSettings(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    system_prompt: str | None = None
    ollama_api_key: str | None = None


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
