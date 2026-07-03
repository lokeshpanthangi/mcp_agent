import json

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import AnyHttpUrl, BaseModel
from sqlmodel import Session, select

from app.auth import get_current_user
from app.db import get_session
from app.models import McpServer, User

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
def attach_mcp(
    body: McpServerCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> McpServerResponse:
    server = McpServer(
        user_id=user.id,
        name=body.name,
        url=str(body.url),
        transport=body.transport,
        headers_json=json.dumps(body.headers) if body.headers else None,
    )
    session.add(server)
    session.commit()
    session.refresh(server)
    return McpServerResponse(id=server.id, name=server.name, url=server.url, transport=server.transport)


@router.get("", response_model=list[McpServerResponse])
def list_mcp(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> list[McpServerResponse]:
    servers = session.exec(select(McpServer).where(McpServer.user_id == user.id)).all()
    return [
        McpServerResponse(id=s.id, name=s.name, url=s.url, transport=s.transport)
        for s in servers
    ]


@router.delete("/{server_id}", status_code=status.HTTP_204_NO_CONTENT)
def detach_mcp(
    server_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    server = session.get(McpServer, server_id)
    if server is None or server.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "MCP server not found")
    session.delete(server)
    session.commit()
