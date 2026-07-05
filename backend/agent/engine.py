import asyncio
import hashlib
import json
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langgraph.prebuilt import create_react_agent
from langgraph.store.memory import InMemoryStore
from langgraph_bigtool import create_agent as create_bigtool_agent

from config import settings

logger = logging.getLogger(__name__)

# Agents are stateless w.r.t. conversation (history is passed on each invoke),
# so they can be cached and shared by (mcp tools + api key). The system prompt
# is injected per-message, so it isn't part of the cache key.
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


def _make_embeddings(api_key: str | None) -> OllamaEmbeddings:
    client_kwargs = {"headers": {"Authorization": f"Bearer {api_key}"}} if api_key else {}
    return OllamaEmbeddings(
        model=settings.OLLAMA_EMBED_MODEL,
        base_url=settings.OLLAMA_BASE_URL,
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


def _bigtool_agent(model: ChatOllama, tools: list, api_key: str | None):
    """Compile an agent that shows the model only the query-relevant tools.

    Instead of binding every tool at once, the model gets a single `retrieve_tools`
    search tool; per message it pulls the TOOL_TOPK most relevant tools from a
    semantic index (their name + description embedded once, up front). Keeps the
    model's context lean and its tool choice sharp when many servers are attached.
    """
    embeddings = _make_embeddings(api_key)
    dims = len(embeddings.embed_query("tool retrieval dimension probe"))
    store = InMemoryStore(index={"embed": embeddings, "dims": dims, "fields": ["description"]})
    registry: dict[str, object] = {}
    for i, t in enumerate(tools):
        tool_id = str(i)  # index-based id — MCP tool names can collide across servers
        registry[tool_id] = t
        store.put(("tools",), tool_id, {"description": f"{t.name}: {t.description or ''}"})
    builder = create_bigtool_agent(model, registry, limit=settings.TOOL_TOPK)
    return builder.compile(store=store)


async def get_agent(
    mcp_config: dict,
    api_key: str | None,
    disabled_tools: set[str] | None = None,
):
    """Build (or reuse) an agent for the given tools + key.

    mcp_config is the MultiServerMCPClient shape:
        {"server_name": {"url": ..., "transport": ..., "headers": {...}?}}
    An empty dict yields a plain chat agent with no tools. `disabled_tools` is a
    set of MCP tool names to exclude (per-tool user toggles). The system prompt is
    supplied per-message by the caller, so it isn't needed here.
    All inputs are plain data — the engine stays DB/HTTP-agnostic.
    """
    disabled = disabled_tools or set()
    fingerprint = {"mcp": mcp_config, "key": api_key, "disabled": sorted(disabled)}
    key = hashlib.sha256(json.dumps(fingerprint, sort_keys=True).encode()).hexdigest()
    if key in _agent_cache:
        return _agent_cache[key]

    all_ok = True
    tools = []
    if mcp_config:
        tools, all_ok = await _load_tools(mcp_config, disabled)

    model = make_model(api_key)
    if tools:
        try:
            agent = _bigtool_agent(model, tools, api_key)
        except Exception as exc:  # noqa: BLE001 - retrieval is best-effort; never break chat
            logger.warning("Tool retrieval unavailable (%s); binding all %d tools.", exc, len(tools))
            agent = create_react_agent(model, tools)
    else:
        agent = create_react_agent(model, [])  # plain chat, no tools
    if all_ok:
        _agent_cache[key] = agent  # only cache a fully-loaded agent
    return agent
