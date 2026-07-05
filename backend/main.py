from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import agent as agent_api
from api import auth as auth_api
from api import mcp as mcp_api
from api import settings as settings_api
from config import settings
from database.db import create_db_and_tables


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    create_db_and_tables()
    yield


app = FastAPI(title="MCP Agent", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_api.router)
app.include_router(mcp_api.router)
app.include_router(agent_api.router)
app.include_router(settings_api.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.OLLAMA_MODEL}
