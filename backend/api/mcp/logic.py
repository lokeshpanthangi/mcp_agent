import json

from fastapi import HTTPException, status
from sqlmodel import Session

from api.mcp.database import (
    McpServer,
    create_mcp_server,
    delete_mcp_server,
    get_mcp_server,
    list_mcp_servers_for_user,
    update_server_disabled_tools,
    update_server_headers,
)
from config import settings
from core.mcp_client import inspect_server


# ── shared helpers ───────────────────────────────────────────────
def config_entry(server: McpServer) -> dict:
    """The single-server MultiServerMCPClient config shape for a stored row."""
    entry: dict = {"url": server.url, "transport": server.transport}
    if server.headers_json:
        entry["headers"] = json.loads(server.headers_json)
    return entry


def _disabled_set(server: McpServer) -> set[str]:
    return set(json.loads(server.disabled_tools_json)) if server.disabled_tools_json else set()


def disabled_tool_names(servers: list[McpServer]) -> set[str]:
    """Union of every tool name turned OFF across a user's servers."""
    names: set[str] = set()
    for s in servers:
        names |= _disabled_set(s)
    return names


def _owned_server(session: Session, user_id: int, server_id: int) -> McpServer:
    server = get_mcp_server(session, server_id)
    if server is None or server.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP server not found")
    return server


# ── CRUD ─────────────────────────────────────────────────────────
def attach_mcp_server(
    session: Session,
    user_id: int,
    name: str,
    url: str,
    transport: str,
    headers: dict[str, str] | None,
) -> McpServer:
    headers_json = json.dumps(headers) if headers else None
    return create_mcp_server(session, user_id, name, url, transport, headers_json)


def list_mcp_servers(session: Session, user_id: int) -> list[McpServer]:
    return list_mcp_servers_for_user(session, user_id)


def detach_mcp_server(session: Session, user_id: int, server_id: int) -> None:
    detach = _owned_server(session, user_id, server_id)
    delete_mcp_server(session, detach)


# ── inspection / connect / tool toggling ─────────────────────────
async def inspect_mcp_server(session: Session, user_id: int, server_id: int) -> dict:
    """Connect to the server and return its tools (with per-tool enabled state)
    and prompts, or a needs_auth / error signal.
    """
    server = _owned_server(session, user_id, server_id)
    result = await inspect_server(server.name, config_entry(server), settings.TOOL_TIMEOUT_SECONDS)

    disabled = _disabled_set(server)
    tools = [
        {**t, "enabled": t["name"] not in disabled} for t in result["tools"]
    ]
    return {
        "id": server.id,
        "name": server.name,
        "url": server.url,
        "ok": result["ok"],
        "needs_auth": result["needs_auth"],
        "error": result["error"],
        "tools": tools,
        "prompts": result["prompts"],
    }


async def connect_mcp_server(
    session: Session, user_id: int, server_id: int, headers: dict[str, str]
) -> dict:
    """Save auth headers (e.g. a bearer token) on the server, then re-inspect."""
    server = _owned_server(session, user_id, server_id)
    update_server_headers(session, server, json.dumps(headers) if headers else None)
    return await inspect_mcp_server(session, user_id, server_id)


def toggle_tool(
    session: Session, user_id: int, server_id: int, tool_name: str, enabled: bool
) -> None:
    server = _owned_server(session, user_id, server_id)
    disabled = _disabled_set(server)
    if enabled:
        disabled.discard(tool_name)
    else:
        disabled.add(tool_name)
    update_server_disabled_tools(
        session, server, json.dumps(sorted(disabled)) if disabled else None
    )
