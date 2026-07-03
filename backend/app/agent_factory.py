import hashlib
import json

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from app.config import settings
from app.models import McpServer

_agent_cache: dict[tuple[int, str], object] = {}


def make_model() -> ChatOllama:
    client_kwargs = {}
    if settings.OLLAMA_API_KEY:
        client_kwargs["headers"] = {"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"}
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        num_predict=settings.MAX_TOKENS,
        client_kwargs=client_kwargs,
    )


def _mcp_config(servers: list[McpServer]) -> dict:
    config = {}
    for s in servers:
        entry: dict = {"url": s.url, "transport": s.transport}
        if s.headers_json:
            entry["headers"] = json.loads(s.headers_json)
        config[s.name] = entry
    return config


def _cache_key(user_id: int, servers: list[McpServer]) -> tuple[int, str]:
    fingerprint = json.dumps(_mcp_config(servers), sort_keys=True)
    return user_id, hashlib.sha256(fingerprint.encode()).hexdigest()


async def get_agent(user_id: int, servers: list[McpServer]):
    key = _cache_key(user_id, servers)
    if key in _agent_cache:
        return _agent_cache[key]

    tools = []
    if servers:
        client = MultiServerMCPClient(_mcp_config(servers))
        tools = await client.get_tools()

    agent = create_react_agent(make_model(), tools, prompt=settings.SYSTEM_PROMPT)
    _agent_cache[key] = agent
    return agent
