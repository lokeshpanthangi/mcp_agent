from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.agent import routes as agent_routes
from api.auth import routes as auth_routes
from api.mcp import routes as mcp_routes
from api.settings import routes as settings_routes
from config import settings
from database import create_db_and_tables


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
app.include_router(auth_routes.router)
app.include_router(mcp_routes.router)
app.include_router(agent_routes.router)
app.include_router(settings_routes.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "model": settings.OLLAMA_MODEL}
