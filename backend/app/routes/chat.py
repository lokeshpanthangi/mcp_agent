import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from typing import TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlmodel import Session, select

from app.agent_factory import get_agent
from app.auth import get_current_user
from app.config import settings
from app.db import engine, get_session
from app.models import Conversation, McpServer, Message, User

router = APIRouter(tags=["chat"])

T = TypeVar("T")


class ChatRequest(BaseModel):
    conversation_id: int
    message: str


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _with_timeout(awaitable: Awaitable[T], timeout: float) -> T:
    """Like asyncio.wait_for, but doesn't block on the cancelled task's own
    cleanup finishing. Some libraries (e.g. MCP session teardown) don't
    cancel cleanly, and asyncio.wait_for on 3.11+ waits for that cleanup
    before raising - which can hang far longer than the timeout itself.
    """
    task = asyncio.ensure_future(awaitable)
    done, pending = await asyncio.wait({task}, timeout=timeout)
    if task in pending:
        task.cancel()  # fire-and-forget - don't wait for its cleanup
        raise TimeoutError
    return task.result()


@router.post("/chat")
async def chat(
    body: ChatRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> StreamingResponse:
    conv = session.get(Conversation, body.conversation_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    session.add(Message(conversation_id=conv.id, role="user", content=body.message))
    session.commit()

    history = session.exec(
        select(Message).where(Message.conversation_id == conv.id).order_by(Message.id)
    ).all()
    lc_messages = [(m.role, m.content) for m in history]

    servers = session.exec(select(McpServer).where(McpServer.user_id == user.id)).all()
    try:
        agent = await _with_timeout(get_agent(user.id, servers), settings.TOOL_TIMEOUT_SECONDS)
    except TimeoutError as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Timed out loading MCP tools") from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Failed to load MCP tools: {exc}") from exc

    async def event_stream() -> AsyncIterator[str]:
        answer_parts: list[str] = []
        events = agent.astream_events({"messages": lc_messages}, version="v2")
        try:
            while True:
                try:
                    ev = await _with_timeout(anext(events), settings.TOOL_TIMEOUT_SECONDS)
                except StopAsyncIteration:
                    break

                kind = ev["event"]
                if kind == "on_chat_model_stream":
                    chunk = ev["data"]["chunk"].content
                    if chunk:
                        answer_parts.append(chunk)
                        yield _sse("token", {"text": chunk})
                elif kind == "on_tool_start":
                    yield _sse("tool_call", {"name": ev["name"], "input": ev["data"].get("input")})
                elif kind == "on_tool_end":
                    yield _sse("tool_result", {"name": ev["name"], "output": str(ev["data"].get("output"))})
        except TimeoutError:
            yield _sse("error", {"message": "Timed out waiting for a response or tool result."})
            yield _sse("done", {})
            return
        except Exception as exc:  # noqa: BLE001 - surface any agent/tool failure to the client
            yield _sse("error", {"message": str(exc)})
            yield _sse("done", {})
            return

        with Session(engine) as db:
            db.add(Message(conversation_id=conv.id, role="assistant", content="".join(answer_parts)))
            db.commit()

        yield _sse("done", {})

    return StreamingResponse(event_stream(), media_type="text/event-stream")
