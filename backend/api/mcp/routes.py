from fastapi import APIRouter, Depends, status
from pydantic import AnyHttpUrl, BaseModel
from sqlmodel import Session

from api.auth.database import User
from api.mcp.logic import attach_mcp_server, detach_mcp_server, list_mcp_servers
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
