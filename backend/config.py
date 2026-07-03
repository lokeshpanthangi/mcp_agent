from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    DATABASE_URL: str

    # LLM (Ollama)
    OLLAMA_MODEL: str
    OLLAMA_BASE_URL: str
    OLLAMA_API_KEY: str | None = None

    # Agent
    MAX_TOKENS: int = 8000
    TOOL_TIMEOUT_SECONDS: int = 30

    # Server
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CORS_ORIGINS: str = "http://localhost:5173"


settings = Settings()
