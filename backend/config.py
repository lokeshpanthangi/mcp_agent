from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str

    # LLM (Ollama)
    OLLAMA_MODEL: str
    OLLAMA_BASE_URL: str
    OLLAMA_API_KEY: str | None = None
    OLLAMA_EMBED_MODEL: str = "nomic-embed-text"  # embeds tool descriptions for retrieval

    # Agent
    MAX_TOKENS: int = 8000
    TOOL_TIMEOUT_SECONDS: int = 30
    # Show the agent only the TOOL_TOPK most query-relevant tools per message
    # (semantic retrieval) instead of binding every tool at once.
    TOOL_TOPK: int = 10

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173"

    # OAuth (MCP connectors)
    PUBLIC_BASE_URL: str = "http://localhost:8000"  # where the OAuth callback is reachable
    FRONTEND_URL: str = "http://localhost:5173"  # where to send the user after connecting


settings = Settings()
