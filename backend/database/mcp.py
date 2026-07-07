import json

from sqlmodel import Session, select

from database.models import McpServer, OAuthState

CODE_PREFIX = "code:"  # connector_key prefix marking a server defined in servers.json


def create_mcp_server(
    session: Session,
    user_id: int,
    name: str,
    url: str,
    transport: str,
    headers_json: str | None,
) -> McpServer:
    server = McpServer(
        user_id=user_id, name=name, url=url, transport=transport, headers_json=headers_json
    )
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


def list_mcp_servers_for_user(session: Session, user_id: int) -> list[McpServer]:
    stmt = (
        select(McpServer)
        .where(McpServer.user_id == user_id)
        .order_by(McpServer.created_at.desc(), McpServer.id.desc())
    )
    return list(session.exec(stmt).all())


def get_mcp_server(session: Session, server_id: int) -> McpServer | None:
    return session.get(McpServer, server_id)


def delete_mcp_server(session: Session, server: McpServer) -> None:
    session.delete(server)
    session.commit()


def update_server_snapshots(
    session: Session,
    server: McpServer,
    tools_snapshot_json: str | None,
    prompts_snapshot_json: str | None,
) -> McpServer:
    server.tools_snapshot_json = tools_snapshot_json
    server.prompts_snapshot_json = prompts_snapshot_json
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


def update_server_transport(session: Session, server: McpServer, transport: str) -> McpServer:
    server.transport = transport
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


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


def get_server_by_connector(session: Session, user_id: int, connector_key: str) -> McpServer | None:
    return session.exec(
        select(McpServer).where(
            McpServer.user_id == user_id, McpServer.connector_key == connector_key
        )
    ).first()


def upsert_connector_server(
    session: Session,
    user_id: int,
    connector_key: str,
    name: str,
    url: str,
    transport: str,
    headers_json: str | None,
    oauth: dict,
) -> McpServer:
    """Create or update the McpServer row backing a connector."""
    server = get_server_by_connector(session, user_id, connector_key)
    if server is None:
        server = McpServer(user_id=user_id, name=name, url=url, transport=transport)
    server.headers_json = headers_json
    server.connector_key = connector_key
    server.oauth_refresh_token = oauth.get("refresh_token")
    server.oauth_token_endpoint = oauth.get("token_endpoint")
    server.oauth_client_id = oauth.get("client_id")
    server.oauth_client_secret = oauth.get("client_secret")
    server.oauth_expires_at = oauth.get("expires_at")
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


def update_server_oauth_token(
    session: Session,
    server: McpServer,
    headers_json: str,
    refresh_token: str | None,
    expires_at,
) -> McpServer:
    server.headers_json = headers_json
    if refresh_token:
        server.oauth_refresh_token = refresh_token
    server.oauth_expires_at = expires_at
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


def set_server_oauth(session: Session, server: McpServer, headers_json: str, oauth: dict) -> McpServer:
    """Store a full OAuth grant (token + refresh bookkeeping) on an existing row."""
    server.headers_json = headers_json
    server.oauth_refresh_token = oauth.get("refresh_token")
    server.oauth_token_endpoint = oauth.get("token_endpoint")
    server.oauth_client_id = oauth.get("client_id")
    server.oauth_client_secret = oauth.get("client_secret")
    server.oauth_expires_at = oauth.get("expires_at")
    session.add(server)
    session.commit()
    session.refresh(server)
    return server


# ── code-defined servers (servers.json) ──────────────────────────
def sync_code_servers(session: Session, user_id: int) -> None:
    """Mirror servers.json into this user's rows so they show + run like any other.

    Each JSON entry becomes an McpServer tagged connector_key="code:<key>". Existing
    per-tool toggles are kept; code rows whose key left the JSON are pruned.
    """
    from mcp_servers.catalog import load_code_servers

    entries = load_code_servers()
    wanted = set()
    for e in entries:
        connector_key = CODE_PREFIX + e["key"]
        wanted.add(connector_key)
        server = get_server_by_connector(session, user_id, connector_key)
        if server is None:
            server = McpServer(user_id=user_id, connector_key=connector_key)
        server.name = e["name"]
        if "command" in e:
            # Local stdio server (spawned as a subprocess) — no URL or headers.
            args = e.get("args") or []
            server.transport = "stdio"
            server.command = e["command"]
            server.args_json = json.dumps(args)
            server.url = f"{e['command']} {' '.join(args)}".strip()
            server.headers_json = None
        else:
            server.url = e["url"]
            server.transport = e.get("transport", "streamable_http")
            server.headers_json = json.dumps(e["headers"]) if e.get("headers") else None
            server.command = None
            server.args_json = None
        session.add(server)

    for server in list_mcp_servers_for_user(session, user_id):
        if (server.connector_key or "").startswith(CODE_PREFIX) and server.connector_key not in wanted:
            session.delete(server)
    session.commit()


# ── OAuth flow state ─────────────────────────────────────────────
def create_oauth_state(session: Session, state: OAuthState) -> OAuthState:
    session.add(state)
    session.commit()
    session.refresh(state)
    return state


def get_oauth_state(session: Session, state: str) -> OAuthState | None:
    return session.get(OAuthState, state)


def delete_oauth_state(session: Session, state: OAuthState) -> None:
    session.delete(state)
    session.commit()
