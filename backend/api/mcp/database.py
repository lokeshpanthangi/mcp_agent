from datetime import datetime, timezone

from sqlmodel import Field, Session, SQLModel, select


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class McpServer(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="user.id", index=True)
    name: str
    url: str
    transport: str = "streamable_http"
    headers_json: str | None = None
    disabled_tools_json: str | None = None  # JSON list of tool names turned OFF
    created_at: datetime = Field(default_factory=utcnow)


def create_mcp_server(
    session: Session,
    user_id: int,
    name: str,
    url: str,
    transport: str,
    headers_json: str | None,
) -> McpServer:
    server = McpServer(
        user_id=user_id,
        name=name,
        url=url,
        transport=transport,
        headers_json=headers_json,
    )
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


def list_mcp_servers_for_user(session: Session, user_id: int) -> list[McpServer]:
    return list(session.exec(select(McpServer).where(McpServer.user_id == user_id)).all())


def get_mcp_server(session: Session, server_id: int) -> McpServer | None:
    return session.get(McpServer, server_id)


def delete_mcp_server(session: Session, server: McpServer) -> None:
    session.delete(server)
    session.commit()


def update_server_headers(session: Session, server: McpServer, headers_json: str | None) -> McpServer:
    server.headers_json = headers_json
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


def update_server_disabled_tools(
    session: Session, server: McpServer, disabled_tools_json: str | None
) -> McpServer:
    server.disabled_tools_json = disabled_tools_json
    session.add(server)
    session.commit()
    session.refresh(server)
    return server
