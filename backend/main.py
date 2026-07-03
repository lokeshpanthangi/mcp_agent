from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from config import settings
from database import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    yield


app = FastAPI(title="MCP Agent", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.OLLAMA_MODEL}
