import json

from fastapi import HTTPException, status
from sqlmodel import Session

from api.mcp.database import (
    McpServer,
    create_mcp_server,
    delete_mcp_server,
    get_mcp_server,
    list_mcp_servers_for_user,
)


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
    server = get_mcp_server(session, server_id)
    if server is None or server.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP server not found")
    delete_mcp_server(session, server)
