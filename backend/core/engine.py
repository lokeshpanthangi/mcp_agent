import hashlib
import json

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama
from langgraph.prebuilt import create_react_agent

from config import settings

# Agents are stateless w.r.t. conversation (history is passed on each invoke),
# so they can be cached and shared by (mcp tools + prompt + api key).
_agent_cache: dict[str, object] = {}


def make_model(api_key: str | None) -> ChatOllama:
    client_kwargs = {}
    if api_key:
        client_kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}
    return ChatOllama(
        model=settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        num_predict=settings.MAX_TOKENS,
        reasoning=True,  # reasoning models (e.g. gpt-oss) stream their thinking
        client_kwargs=client_kwargs,
    )


async def get_agent(mcp_config: dict, system_prompt: str, api_key: str | None):
    """Build (or reuse) a LangGraph agent for the given tools + prompt + key.

    mcp_config is the MultiServerMCPClient shape:
        {"server_name": {"url": ..., "transport": ..., "headers": {...}?}}
    An empty dict yields a plain chat agent with no tools.
    All three inputs are plain data — the engine stays DB/HTTP-agnostic.
    """
    fingerprint = {"mcp": mcp_config, "prompt": system_prompt, "key": api_key}
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    if key in _agent_cache:
        return _agent_cache[key]

    tools = []
    if mcp_config:
        client = MultiServerMCPClient(mcp_config)
        tools = await client.get_tools()

    agent = create_react_agent(make_model(api_key), tools, prompt=system_prompt)
    _agent_cache[key] = agent
    return agent
