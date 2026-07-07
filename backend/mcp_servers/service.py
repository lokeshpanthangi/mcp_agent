import json
import logging
import math
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, status
from sqlmodel import Session

from adapters import oauth as mcp_oauth
from adapters.mcp_client import infer_transport, inspect_server, inspect_server_with_fallback
from config import settings
from database.mcp import (
    create_mcp_server,
    create_oauth_state,
    delete_mcp_server,
    delete_oauth_state,
    get_mcp_server,
    get_oauth_state,
    get_server_by_connector,
    list_mcp_servers_for_user,
    set_server_oauth,
    sync_code_servers,
    update_server_disabled_tools,
    update_server_headers,
    update_server_oauth_token,
    update_server_snapshots,
    update_server_transport,
    upsert_connector_server,
)
from database.models import McpServer, OAuthState
from agent.mcp_context import server_usable_in_chat
from mcp_servers.connectors import CONNECTORS, CONNECTORS_BY_KEY

logger = logging.getLogger(__name__)

SERVER_PREFIX = "server:"  # OAuthState.connector_key marker for an attached-by-URL server


# ── shared helpers ───────────────────────────────────────────────
def config_entry(server: McpServer) -> dict:
    """The single-server MultiServerMCPClient config shape for a stored row."""
    if server.transport == "stdio":
        return {
            "command": server.command,
            "args": json.loads(server.args_json) if server.args_json else [],
            "transport": "stdio",
        }
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


def user_servers(session: Session, user_id: int) -> list[McpServer]:
    """A user's servers, with code-defined (servers.json) ones synced in first."""
    sync_code_servers(session, user_id)
    return list_mcp_servers_for_user(session, user_id)


def list_mcp_commands(session: Session, user_id: int) -> list[dict]:
    """Slash-commands available in chat from connected MCP prompt snapshots."""
    servers = user_servers(session, user_id)
    usable = [s for s in servers if server_usable_in_chat(s)]

    raw: list[tuple[McpServer, dict]] = []
    name_counts: dict[str, int] = {}
    for server in usable:
        prompts = json.loads(server.prompts_snapshot_json) if server.prompts_snapshot_json else []
        for prompt in prompts:
            name_counts[prompt["name"]] = name_counts.get(prompt["name"], 0) + 1
            raw.append((server, prompt))

    commands: list[dict] = []
    for server, prompt in raw:
        ambiguous = name_counts[prompt["name"]] > 1
        slash = f"/{server.name}/{prompt['name']}" if ambiguous else f"/{prompt['name']}"
        arguments = prompt.get("arguments") or []
        required = [a["name"] for a in arguments if a.get("required")]
        if not required:
            usage = slash
        elif len(required) == 1:
            usage = f"{slash} <{required[0]}>"
        else:
            usage = f"{slash} " + " ".join(f"{name}=..." for name in required)
        commands.append(
            {
                "name": prompt["name"],
                "server": server.name,
                "description": prompt.get("description") or "",
                "slash": slash,
                "usage": usage,
                "arguments": arguments,
            }
        )

    commands.sort(key=lambda c: (c["name"].lower(), c["server"].lower()))
    return commands


# ── CRUD ─────────────────────────────────────────────────────────
def attach_mcp_server(
    session: Session,
    user_id: int,
    name: str,
    url: str,
    transport: str | None,
    headers: dict[str, str] | None,
) -> McpServer:
    headers_json = json.dumps(headers) if headers else None
    resolved_transport = transport or infer_transport(url)
    return create_mcp_server(session, user_id, name, url, resolved_transport, headers_json)


def list_mcp_servers(session: Session, user_id: int) -> list[McpServer]:
    return user_servers(session, user_id)


def detach_mcp_server(session: Session, user_id: int, server_id: int) -> None:
    detach = _owned_server(session, user_id, server_id)
    delete_mcp_server(session, detach)


# ── inspection / connect / tool toggling ─────────────────────────
async def inspect_mcp_server(session: Session, user_id: int, server_id: int) -> dict:
    """Connect to the server and return its tools (with per-tool enabled state)
    and prompts, or a needs_auth / error signal.
    """
    server = _owned_server(session, user_id, server_id)

    if server.transport == "stdio":
        # Local subprocess — no URL, headers, or OAuth to consider.
        result = await inspect_server(server.name, config_entry(server), settings.TOOL_TIMEOUT_SECONDS)
        disabled = _disabled_set(server)
        tools = [{**t, "enabled": t["name"] not in disabled} for t in result["tools"]]
        if result["ok"]:
            update_server_snapshots(
                session,
                server,
                json.dumps(result["tools"]),
                json.dumps(result["prompts"]) if result["prompts"] else None,
            )
        return {
            "id": server.id,
            "name": server.name,
            "url": server.url,
            "ok": result["ok"],
            "needs_auth": False,
            "supports_oauth": False,
            "error": result["error"],
            "tools": tools,
            "prompts": result["prompts"],
        }

    connector = CONNECTORS_BY_KEY.get(server.connector_key or "") or {}
    headers = json.loads(server.headers_json) if server.headers_json else None

    # Catalog token connectors without credentials — prompt for a PAT.
    if not server.headers_json and connector.get("auth") == "token":
        return _needs_auth_inspect(server, supports_oauth=False)

    # OAuth with Dynamic Client Registration — offer Login before probing.
    if not server.headers_json and await _oauth_login_available(server.url):
        return _needs_auth_inspect(server, supports_oauth=True)

    result, transport = await inspect_server_with_fallback(
        server.name, server.url, headers, settings.TOOL_TIMEOUT_SECONDS
    )
    if transport != server.transport:
        update_server_transport(session, server, transport)

    disabled = _disabled_set(server)
    tools = [{**t, "enabled": t["name"] not in disabled} for t in result["tools"]]

    supports_oauth = False
    if result["needs_auth"] and not server.headers_json:
        supports_oauth = await _oauth_login_available(server.url)

    if result["ok"]:
        update_server_snapshots(
            session,
            server,
            json.dumps(result["tools"]),
            json.dumps(result["prompts"]) if result["prompts"] else None,
        )

    return {
        "id": server.id,
        "name": server.name,
        "url": server.url,
        "ok": result["ok"],
        "needs_auth": result["needs_auth"],
        "supports_oauth": supports_oauth,
        "error": result["error"],
        "tools": tools,
        "prompts": result["prompts"],
    }


def _needs_auth_inspect(server: McpServer, *, supports_oauth: bool) -> dict:
    """Inspect response for a server that still needs authentication."""
    return {
        "id": server.id,
        "name": server.name,
        "url": server.url,
        "ok": False,
        "needs_auth": True,
        "supports_oauth": supports_oauth,
        "error": None,
        "tools": [],
        "prompts": [],
    }


async def _oauth_login_available(url: str) -> bool:
    """True when OAuth login via popup is supported (Dynamic Client Registration)."""
    try:
        meta = await mcp_oauth.discover(url)
        return bool(meta.get("registration_endpoint"))
    except Exception:  # noqa: BLE001
        return False


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


# ── OAuth connectors ─────────────────────────────────────────────
def _redirect_uri() -> str:
    return settings.PUBLIC_BASE_URL.rstrip("/") + "/mcp/oauth/callback"


def _connector_connected(c: dict, server: McpServer | None) -> bool:
    """Whether this user has finished connecting a catalog connector."""
    if server is None:
        return False
    auth = c.get("auth", "oauth")
    if auth == "open":
        return True
    if auth == "token":
        return bool(server.headers_json)
    return bool(server.headers_json)


def _connector_row(session: Session, user_id: int, c: dict) -> dict:
    server = get_server_by_connector(session, user_id, c["key"])
    return {
        **c,
        "connected": _connector_connected(c, server),
        "server_id": server.id if server else None,
    }


def list_connectors(
    session: Session, user_id: int, *, page: int = 1, limit: int = 12
) -> dict:
    """Paginated connector catalog with per-user connected state."""
    total = len(CONNECTORS)
    pages = max(1, math.ceil(total / limit)) if total else 1
    page = max(1, min(page, pages))
    start = (page - 1) * limit
    chunk = CONNECTORS[start : start + limit]
    return {
        "items": [_connector_row(session, user_id, c) for c in chunk],
        "total": total,
        "page": page,
        "pages": pages,
        "limit": limit,
    }


async def connect_connector(session: Session, user_id: int, connector_key: str) -> dict:
    """Start connecting a connector.

    OAuth connectors return {"authorization_url": ...} to open a popup; token
    connectors create their server row and return {"server_id": ...} so the UI
    can prompt for a personal access token via the normal Connect flow.
    """
    connector = CONNECTORS_BY_KEY.get(connector_key)
    if connector is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown connector")
    if connector.get("auth") in ("token", "open"):
        server = _ensure_connector_server(session, user_id, connector)
        return {"server_id": server.id}
    if not await _oauth_login_available(connector["url"]):
        # OAuth without Dynamic Client Registration (Box, Plaid, …) — paste a token.
        server = _ensure_connector_server(session, user_id, connector)
        return {"server_id": server.id}
    return {"authorization_url": await start_connector_oauth(session, user_id, connector)}


def _ensure_connector_server(session: Session, user_id: int, connector: dict) -> McpServer:
    """The (possibly not-yet-authenticated) server row backing a token connector."""
    existing = get_server_by_connector(session, user_id, connector["key"])
    if existing is not None:
        return existing
    return upsert_connector_server(
        session,
        user_id,
        connector["key"],
        connector["name"],
        connector["url"],
        connector["transport"],
        None,  # no auth header yet — the user pastes a token next
        {},
    )


async def _begin_oauth(
    session: Session, user_id: int, *, name: str, url: str, transport: str, connector_key: str
) -> str:
    """Discover + register + build an authorization URL for any MCP server.

    Shared by catalog connectors and attached-by-URL servers; the target is
    remembered in the OAuthState's connector_key (a catalog key or "server:<id>").
    """
    redirect_uri = _redirect_uri()
    try:
        meta = await mcp_oauth.discover(url)
        scope = " ".join(meta["scopes_supported"]) or None
        if not meta.get("registration_endpoint"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                f"{name} does not support OAuth login. Paste an access token instead.",
            )
        reg = await mcp_oauth.register_client(meta["registration_endpoint"], redirect_uri, scope)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not start OAuth for {name}: {exc}"
        ) from exc

    verifier, challenge = mcp_oauth.new_pkce()
    state = secrets.token_urlsafe(32)
    create_oauth_state(
        session,
        OAuthState(
            state=state,
            user_id=user_id,
            connector_key=connector_key,
            mcp_url=url,
            transport=transport,
            redirect_uri=redirect_uri,
            code_verifier=verifier,
            client_id=reg["client_id"],
            client_secret=reg.get("client_secret"),
            token_endpoint=meta["token_endpoint"],
            resource=meta["resource"],
            scope=scope,
        ),
    )
    return mcp_oauth.build_authorization_url(
        meta["authorization_endpoint"],
        reg["client_id"],
        redirect_uri,
        challenge,
        state,
        scope,
        meta["resource"],
    )


async def start_connector_oauth(session: Session, user_id: int, connector: dict) -> str:
    """Begin the OAuth flow for a catalog connector; returns the authorization URL."""
    return await _begin_oauth(
        session,
        user_id,
        name=connector["name"],
        url=connector["url"],
        transport=connector["transport"],
        connector_key=connector["key"],
    )


async def start_server_oauth(session: Session, user_id: int, server_id: int) -> str:
    """Begin the OAuth flow for a user's attached-by-URL server; returns the auth URL."""
    server = _owned_server(session, user_id, server_id)
    if not await _oauth_login_available(server.url):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"{server.name} does not support OAuth login. Paste an access token instead.",
        )
    return await _begin_oauth(
        session,
        user_id,
        name=server.name,
        url=server.url,
        transport=server.transport,
        connector_key=f"{SERVER_PREFIX}{server.id}",
    )


async def handle_oauth_callback(session: Session, state_str: str, code: str) -> str:
    """Exchange the code for tokens and store the connector as an MCP server."""
    st = get_oauth_state(session, state_str)
    if st is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")

    token = await mcp_oauth.exchange_code(
        st.token_endpoint,
        code,
        st.redirect_uri,
        st.client_id,
        st.code_verifier,
        st.resource or st.mcp_url,
        st.client_secret,
    )
    headers_json = json.dumps({"Authorization": f"Bearer {token['access_token']}"})
    oauth = {
        "refresh_token": token.get("refresh_token"),
        "token_endpoint": st.token_endpoint,
        "client_id": st.client_id,
        "client_secret": st.client_secret,
        "expires_at": _expiry(token.get("expires_in")),
    }

    if st.connector_key.startswith(SERVER_PREFIX):
        # Attached-by-URL server: save the grant onto its existing row.
        server = get_mcp_server(session, int(st.connector_key[len(SERVER_PREFIX):]))
        if server is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP server no longer exists")
        set_server_oauth(session, server, headers_json, oauth)
        name = server.name
    else:
        # Catalog connector: create/update its backing row.
        connector = CONNECTORS_BY_KEY[st.connector_key]
        upsert_connector_server(
            session, st.user_id, st.connector_key, connector["name"],
            st.mcp_url, st.transport, headers_json, oauth,
        )
        name = connector["name"]

    delete_oauth_state(session, st)
    return name


async def refresh_expired_tokens(session: Session, servers: list[McpServer]) -> None:
    """Refresh any OAuth access tokens that are expired (or about to)."""
    now = datetime.now(timezone.utc)
    for server in servers:
        if not (server.oauth_refresh_token and server.oauth_expires_at):
            continue
        expires_at = server.oauth_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at - timedelta(seconds=60) > now:
            continue
        try:
            token = await mcp_oauth.refresh_access_token(
                server.oauth_token_endpoint,
                server.oauth_refresh_token,
                server.oauth_client_id,
                server.oauth_client_secret,
            )
            update_server_oauth_token(
                session,
                server,
                json.dumps({"Authorization": f"Bearer {token['access_token']}"}),
                token.get("refresh_token"),
                _expiry(token.get("expires_in")),
            )
        except Exception as exc:  # noqa: BLE001 - refresh failure just leaves the old token
            logger.warning("Token refresh failed for %r: %s", server.name, exc)


def _expiry(expires_in) -> datetime | None:
    if not expires_in:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
