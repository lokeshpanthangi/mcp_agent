"""All database tables in one place (SQLModel)."""

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


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


class Conversation(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    title: str = "New conversation"
    created_at: datetime = Field(default_factory=utcnow)


class Message(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    conversation_id: int = Field(foreign_key="conversation.id", index=True)
    role: str
    content: str
    reasoning: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class McpServer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    url: str
    transport: str = "streamable_http"
    headers_json: str | None = None
    disabled_tools_json: str | None = None  # JSON list of tool names turned OFF
    connector_key: str | None = None  # set for built-in connectors ("github") and code servers ("code:<key>")
    # OAuth bookkeeping (for connectors) — enables silent token refresh.
    oauth_refresh_token: str | None = None
    oauth_token_endpoint: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=utcnow)
    # Cached from last successful inspect — injected into the system prompt at chat time.
    tools_snapshot_json: str | None = None
    prompts_snapshot_json: str | None = None


class OAuthState(SQLModel, table=True):
    """Short-lived state for an in-flight OAuth authorization (start -> callback)."""

    state: str = Field(primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    connector_key: str
    mcp_url: str
    transport: str
    redirect_uri: str
    code_verifier: str
    client_id: str
    client_secret: str | None = None
    token_endpoint: str
    resource: str = ""  # canonical OAuth resource identifier (RFC 8707)
    scope: str | None = None
    created_at: datetime = Field(default_factory=utcnow)


class UserSettings(SQLModel, table=True):
    user_id: int = Field(foreign_key="user.id", primary_key=True)
    system_prompt: str | None = None
    ollama_api_key: str | None = None
    model: str | None = None  # chosen Ollama model (falls back to the .env default)


class OllamaModel(SQLModel, table=True):
    """Catalog of models synced from the Ollama API (/api/tags)."""

    name: str = Field(primary_key=True)
    reasoning: bool = False
    family: str | None = None
    parameter_size: str | None = None
    quantization_level: str | None = None
    size: int | None = None
    modified_at: str | None = None
    synced_at: datetime = Field(default_factory=utcnow)
