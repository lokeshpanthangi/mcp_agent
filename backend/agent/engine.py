import asyncio
import hashlib
import json
import logging

from langchain.agents import create_agent
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama

from config import settings

logger = logging.getLogger(__name__)

# Agents are stateless w.r.t. conversation (history is passed on each invoke),
# so they can be cached and shared by (mcp tools + api key + disabled tools).
# The system prompt is injected per-message, so it isn't part of the cache key.
_agent_cache: dict[str, object] = {}


def make_model(api_key: str | None, model: str | None = None) -> ChatOllama:
    client_kwargs = {}
    if api_key:
        client_kwargs["headers"] = {"Authorization": f"Bearer {api_key}"}
    return ChatOllama(
        model=model or settings.OLLAMA_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
        num_predict=settings.MAX_TOKENS,
        reasoning=True,  # reasoning models (e.g. gpt-oss) stream their thinking
        client_kwargs=client_kwargs,
    )


async def _load_tools(mcp_config: dict, disabled: set[str]) -> tuple[list, bool]:
    """Load tools from every MCP server independently.

    A server that fails to connect (down, bad auth, unreachable) or that hangs
    past TOOL_TIMEOUT_SECONDS is skipped and logged — the working servers still
    contribute their tools. Without the timeout, a single unresponsive server
    would block tool loading forever and freeze the whole chat.

    Returns (tools, all_ok). `all_ok` is False if any server was skipped, so the
    caller can avoid caching a degraded agent (it retries next message).
    """
    tools = []
    all_ok = True
    for name, entry in mcp_config.items():
        try:
            client = MultiServerMCPClient({name: entry})
            server_tools = await asyncio.wait_for(
                client.get_tools(), timeout=settings.TOOL_TIMEOUT_SECONDS
            )
            tools.extend(t for t in server_tools if t.name not in disabled)
        except Exception as exc:  # noqa: BLE001 - one bad/slow server must not break the rest
            logger.warning("Skipping MCP server %r: %s", name, exc)
            all_ok = False
    return tools, all_ok


async def get_agent(
    mcp_config: dict,
    api_key: str | None,
    model: str | None = None,
    disabled_tools: set[str] | None = None,
):
    """Build (or reuse) a ReAct agent bound to every tool from the MCP servers.

    mcp_config is the MultiServerMCPClient shape:
        {"server_name": {"url": ..., "transport": ..., "headers": {...}?}}
    An empty dict yields a plain chat agent. `model` is the chosen Ollama model
    (defaults to the .env one). `disabled_tools` are per-tool user toggles to
    exclude. The system prompt is supplied per-message by the caller.
    """
    disabled = disabled_tools or set()
    fingerprint = {"mcp": mcp_config, "key": api_key, "model": model, "disabled": sorted(disabled)}
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    if key in _agent_cache:
        return _agent_cache[key]

    all_ok = True
    tools = []
    if mcp_config:
        tools, all_ok = await _load_tools(mcp_config, disabled)

    agent = create_agent(make_model(api_key, model), tools)
    if all_ok:
        _agent_cache[key] = agent  # only cache a fully-loaded agent
    return agent
