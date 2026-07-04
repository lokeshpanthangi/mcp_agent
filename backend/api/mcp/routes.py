from fastapi import APIRouter, Depends, status
from pydantic import AnyHttpUrl, BaseModel
from sqlmodel import Session

from api.auth.database import User
from api.mcp.logic import (
    attach_mcp_server,
    connect_mcp_server,
    detach_mcp_server,
    inspect_mcp_server,
    list_mcp_servers,
    toggle_tool,
)
from database import get_session
from security.auth import get_current_user

router = APIRouter(prefix="/mcp", tags=["mcp"])


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
