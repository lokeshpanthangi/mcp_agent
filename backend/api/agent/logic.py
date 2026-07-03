import asyncio
import json
from collections.abc import AsyncIterator, Awaitable
from typing import TypeVar

from fastapi import HTTPException, status
from sqlmodel import Session

from api.agent.database import (
    Conversation,
    Message,
    create_conversation,
    create_message,
    get_conversation,
    list_conversations_for_user,
    list_messages,
    set_conversation_title,
)
from api.mcp.database import McpServer, list_mcp_servers_for_user
from api.settings.logic import get_effective_settings
from config import settings
from core.engine import get_agent
from database import engine

T = TypeVar("T")


async def _with_timeout(awaitable: Awaitable[T], timeout: float) -> T:
    """Like asyncio.wait_for, but doesn't block on the cancelled task's own
    cleanup. Some libraries (e.g. MCP session teardown) don't cancel cleanly,
    and asyncio.wait_for on 3.11+ waits for that cleanup before raising -
    which can hang far longer than the timeout itself.
    """
    task = asyncio.ensure_future(awaitable)
    _, pending = await asyncio.wait({task}, timeout=timeout)
    if task in pending:
        task.cancel()  # fire-and-forget - don't await its cleanup
        raise TimeoutError
    return task.result()


def start_conversation(session: Session, user_id: int) -> Conversation:
    return create_conversation(session, user_id)


def list_conversations(session: Session, user_id: int) -> list[Conversation]:
    return list_conversations_for_user(session, user_id)


def get_conversation_messages(session: Session, user_id: int, conversation_id: int) -> list[Message]:
    conv = get_conversation(session, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")
    return list_messages(session, conversation_id)


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _mcp_config(servers: list[McpServer]) -> dict:
    config = {}
    for s in servers:
        entry: dict = {"url": s.url, "transport": s.transport}
        if s.headers_json:
            entry["headers"] = json.loads(s.headers_json)
        config[s.name] = entry
    return config


async def chat_stream(
    session: Session, user_id: int, conversation_id: int, message: str
) -> AsyncIterator[str]:
    conv = get_conversation(session, conversation_id)
    if conv is None or conv.user_id != user_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Conversation not found")

    create_message(session, conversation_id, "user", message)
    history = [(m.role, m.content) for m in list_messages(session, conversation_id)]

    # First user message becomes the conversation title.
    if len(history) == 1:
        set_conversation_title(session, conv, message[:60])

    servers = list_mcp_servers_for_user(session, user_id)
    eff = get_effective_settings(session, user_id)
    try:
        agent = await _with_timeout(
            get_agent(_mcp_config(servers), eff["system_prompt"], eff["api_key"]),
            settings.TOOL_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Timed out loading MCP tools") from exc
    except Exception as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, f"Failed to load MCP tools: {exc}") from exc

    async def stream() -> AsyncIterator[str]:
        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        events = agent.astream_events({"messages": history}, version="v2")
        try:
            while True:
                try:
                    ev = await _with_timeout(anext(events), settings.TOOL_TIMEOUT_SECONDS)
                except StopAsyncIteration:
                    break

                kind = ev["event"]
                if kind == "on_chat_model_stream":
                    chunk = ev["data"]["chunk"]
                    reasoning = chunk.additional_kwargs.get("reasoning_content")
                    if reasoning:
                        reasoning_parts.append(reasoning)
                        yield _sse("reasoning", {"text": reasoning})
                    if chunk.content:
                        answer_parts.append(chunk.content)
                        yield _sse("token", {"text": chunk.content})
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

        # Fresh session: the request-scoped one is closed once streaming begins.
        with Session(engine) as db:
            create_message(
                db,
                conversation_id,
                "assistant",
                "".join(answer_parts),
                reasoning="".join(reasoning_parts) or None,
            )

        yield _sse("done", {})

    return stream()
