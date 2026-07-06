import json
from collections.abc import AsyncIterator

from fastapi import HTTPException, status
from sqlmodel import Session

from agent.engine import get_agent
from agent.mcp_context import build_mcp_commands_section, server_usable_in_chat
from agent.mcp_prompts import resolve_slash_command
from database.conversations import (
    create_conversation,
    create_message,
    get_conversation,
    list_conversations_for_user,
    list_messages,
    set_conversation_title,
)
from database.db import engine
from database.models import Conversation, Message
from database.settings import get_effective_settings
from mcp_servers.service import (
    config_entry,
    disabled_tool_names,
    refresh_expired_tokens,
    user_servers,
)


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

    servers = user_servers(session, user_id)  # includes code-defined servers.json
    await refresh_expired_tokens(session, servers)  # silently refresh OAuth tokens
    active = [s for s in servers if server_usable_in_chat(s)]
    mcp_config = {s.name: config_entry(s) for s in active}
    disabled = disabled_tool_names(servers)
    eff = get_effective_settings(session, user_id)

    # Broken/slow servers are skipped inside get_agent, so a single bad server
    # never fails the whole chat. The system prompt rides along as a system
    # message (the agent itself is prompt-agnostic and cached across users).
    agent = await get_agent(mcp_config, eff["api_key"], eff["model"], disabled)
    mcp_section = build_mcp_commands_section(servers)
    system = eff["system_prompt"] + mcp_section

    slash = await resolve_slash_command(message, active, mcp_config)
    if slash and slash.error:
        async def error_stream() -> AsyncIterator[str]:
            yield _sse("error", {"message": slash.error})
            with Session(engine) as db:
                create_message(db, conversation_id, "assistant", slash.error)
            yield _sse("done", {})

        return error_stream()

    if slash and slash.messages:
        prior = history[:-1]
        expanded = list(slash.messages)
        if slash.trailing_text:
            expanded.append(("user", slash.trailing_text))
        messages = [("system", system), *prior, *expanded]
        slash_meta = {"name": slash.prompt_name, "server": slash.server_name}
    else:
        messages = [("system", system), *history]
        slash_meta = None

    async def stream() -> AsyncIterator[str]:
        if slash_meta:
            yield _sse("mcp_prompt", slash_meta)
        answer_parts: list[str] = []
        reasoning_parts: list[str] = []
        try:
            async for ev in agent.astream_events({"messages": messages}, version="v2"):
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
