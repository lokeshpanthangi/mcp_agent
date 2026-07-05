from fastapi import APIRouter, Depends, status
from fastapi.responses import HTMLResponse
from pydantic import AnyHttpUrl, BaseModel
from sqlmodel import Session

from api.deps import get_current_user
from database.db import get_session
from database.models import User
from mcp_servers.service import (
    attach_mcp_server,
    connect_connector,
    connect_mcp_server,
    detach_mcp_server,
    handle_oauth_callback,
    inspect_mcp_server,
    list_connectors,
    list_mcp_servers,
    toggle_tool,
)

router = APIRouter(prefix="/mcp", tags=["mcp"])


class ConnectorResponse(BaseModel):
    key: str
    name: str
    url: str
    transport: str
    description: str
    connected: bool
    server_id: int | None
    auth: str = "oauth"


class ConnectorAuthResponse(BaseModel):
    # OAuth connectors return an authorization_url to open in a popup; token
    # connectors return the server_id of the row awaiting a pasted token.
    authorization_url: str | None = None
    server_id: int | None = None


def _popup_close_html(message: str) -> str:
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{message}</title>
<style>body{{font-family:system-ui;background:#0f1015;color:#e7e7ea;display:grid;
place-items:center;height:100vh;margin:0}}.card{{text-align:center}}</style></head>
<body><div class="card"><h2>{message}</h2><p>You can close this window.</p></div>
<script>try{{window.opener&&window.opener.postMessage('mcp-oauth-done','*')}}catch(e){{}}
setTimeout(()=>window.close(),800);</script></body></html>"""


class McpServerCreate(BaseModel):
    name: str
    url: AnyHttpUrl
    transport: str = "streamable_http"
    headers: dict[str, str] | None = None


class McpServerResponse(BaseModel):
    id: int
    name: str
    url: str
    transport: str


class ToolInfo(BaseModel):
    name: str
    description: str
    input_schema: dict
    enabled: bool


class PromptInfo(BaseModel):
    name: str
    description: str


class InspectResponse(BaseModel):
    id: int
    name: str
    url: str
    ok: bool
    needs_auth: bool
    error: str | None
    tools: list[ToolInfo]
    prompts: list[PromptInfo]


class ConnectRequest(BaseModel):
    token: str


class ToolToggle(BaseModel):
    enabled: bool


@router.post("", response_model=McpServerResponse)
def attach_route(
    body: McpServerCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> McpServerResponse:
    server = attach_mcp_server(session, user.id, body.name, str(body.url), body.transport, body.headers)
    return McpServerResponse(id=server.id, name=server.name, url=server.url, transport=server.transport)


@router.get("", response_model=list[McpServerResponse])
def list_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[McpServerResponse]:
    servers = list_mcp_servers(session, user.id)
    return [
        McpServerResponse(id=s.id, name=s.name, url=s.url, transport=s.transport)
        for s in servers
    ]


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_route(
    server_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    detach_mcp_server(session, user.id, server_id)


@router.get("/{server_id}/inspect", response_model=InspectResponse)
async def inspect_route(
    server_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    return await inspect_mcp_server(session, user.id, server_id)


@router.post("/{server_id}/connect", response_model=InspectResponse)
async def connect_route(
    server_id: int,
    body: ConnectRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict:
    headers = {"Authorization": f"Bearer {body.token}"}
    return await connect_mcp_server(session, user.id, server_id, headers)


@router.put("/{server_id}/tools/{tool_name}", status_code=status.HTTP_204_NO_CONTENT)
def toggle_tool_route(
    server_id: int,
    tool_name: str,
    body: ToolToggle,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    toggle_tool(session, user.id, server_id, tool_name, body.enabled)


# ── OAuth connectors ─────────────────────────────────────────────
@router.get("/connectors", response_model=list[ConnectorResponse])
def connectors_route(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[dict]:
    return list_connectors(session, user.id)


@router.post("/connectors/{connector_key}/connect", response_model=ConnectorAuthResponse)
async def connector_connect_route(
    connector_key: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> ConnectorAuthResponse:
    result = await connect_connector(session, user.id, connector_key)
    return ConnectorAuthResponse(**result)


# The provider redirects the browser here — a top-level navigation with no
# bearer token. The user is identified by the (secret) OAuth state, not auth.
@router.get("/oauth/callback", response_class=HTMLResponse)
async def oauth_callback_route(
    session: Session = Depends(get_session),
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    if error:
        return HTMLResponse(_popup_close_html(f"Authorization failed: {error}"))
    if not code or not state:
        return HTMLResponse(_popup_close_html("Missing authorization code"))
    try:
        name = await handle_oauth_callback(session, state, code)
        return HTMLResponse(_popup_close_html(f"Connected to {name} ✓"))
    except Exception as exc:  # noqa: BLE001 - always render a closeable page
        return HTMLResponse(_popup_close_html(f"Could not connect: {exc}"))
