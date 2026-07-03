import hashlib
import json

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from config import settings
from prompts import SYSTEM_PROMPT

# Agents are stateless w.r.t. conversation (history is passed on each invoke),
# so they can be cached and shared by their MCP tool set alone.
_agent_cache: dict[str, object] = {}


def make_model() -> ChatOllama:
    client_kwargs = {}
    if settings.OLLAMA_API_KEY:
        client_kwargs["headers"] = {"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"}
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        num_predict=settings.MAX_TOKENS,
        reasoning=True,  # reasoning models (e.g. gpt-oss) stream their thinking
        client_kwargs=client_kwargs,
    )


async def get_agent(mcp_config: dict):
    """Build (or reuse) a LangGraph agent for the given MCP server config.

    mcp_config is the MultiServerMCPClient shape:
        {"server_name": {"url": ..., "transport": ..., "headers": {...}?}}
    An empty dict yields a plain chat agent with no tools.
    """
    key = hashlib.sha256(json.dumps(mcp_config, sort_keys=True).encode()).hexdigest()
    if key in _agent_cache:
        return _agent_cache[key]

    tools = []
    if mcp_config:
        client = MultiServerMCPClient(mcp_config)
        tools = await client.get_tools()

    agent = create_react_agent(make_model(), tools, prompt=SYSTEM_PROMPT)
    _agent_cache[key] = agent
    return agent
