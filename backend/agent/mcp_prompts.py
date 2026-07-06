"""Resolve MCP slash-commands (/prompt-name) via the MCP get_prompt API."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_mcp_adapters.client import MultiServerMCPClient

from agent.mcp_context import server_usable_in_chat
from config import settings
from database.models import McpServer

# /prompt rest…  or  /ServerName/prompt rest…  (prompt names may contain spaces)
_KV_RE = re.compile(r"(\w+)=([^\s]+(?:\s+[^\s=]+)*)")


@dataclass
class _SlashCatalogEntry:
    path: str
    server_hint: str | None
    prompt_name: str


def _slash_catalog(servers: list[McpServer]) -> list[_SlashCatalogEntry]:
    """Build match paths for every usable prompt, longest paths first."""
    index = _prompt_index(servers)
    entries: list[_SlashCatalogEntry] = []
    for prompt_name, matches in index.items():
        ambiguous = len(matches) > 1
        for server, _prompt in matches:
            path = f"{server.name}/{prompt_name}" if ambiguous else prompt_name
            entries.append(
                _SlashCatalogEntry(
                    path=path,
                    server_hint=server.name if ambiguous else None,
                    prompt_name=prompt_name,
                )
            )
    entries.sort(key=lambda e: len(e.path), reverse=True)
    return entries


def parse_slash_command(
    text: str,
    servers: list[McpServer] | None = None,
) -> tuple[str | None, str | None, str] | None:
    """Return (prompt_name, server_hint, trailing_text) when text is a slash-command."""
    stripped = text.strip()
    if not stripped.startswith("/") or stripped.startswith("//"):
        return None

    body = stripped[1:]
    if servers:
        for entry in _slash_catalog(servers):
            prefix = entry.path
            if len(body) < len(prefix):
                continue
            if body[: len(prefix)].casefold() != prefix.casefold():
                continue
            rest = body[len(prefix) :]
            if rest and not rest.startswith(" "):
                continue
            return entry.prompt_name, entry.server_hint, rest.strip()

    # Fallback when no catalog is available (e.g. unit tests).
    if "/" in body:
        server_hint, _, prompt_part = body.partition("/")
        prompt_name, _, trailing = prompt_part.partition(" ")
        return prompt_name or None, server_hint or None, trailing.strip()
    prompt_name, _, trailing = body.partition(" ")
    return prompt_name or None, None, trailing.strip()


@dataclass
class SlashResolution:
    """Result of resolving a user slash-command."""

    prompt_name: str
    server_name: str
    messages: list[tuple[str, str]]
    trailing_text: str = ""
    error: str | None = None


def _prompt_index(servers: list[McpServer]) -> dict[str, list[tuple[McpServer, dict]]]:
    index: dict[str, list[tuple[McpServer, dict]]] = {}
    for server in servers:
        if not server_usable_in_chat(server):
            continue
        prompts = json.loads(server.prompts_snapshot_json) if server.prompts_snapshot_json else []
        for prompt in prompts:
            index.setdefault(prompt["name"], []).append((server, prompt))
    return index


def _pick_server(
    prompt_name: str,
    server_hint: str | None,
    index: dict[str, list[tuple[McpServer, dict]]],
) -> tuple[McpServer, dict] | str:
    matches = index.get(prompt_name)
    if not matches:
        return f"Unknown slash-command `/{prompt_name}`. Connect an MCP server that exposes this prompt."

    if server_hint:
        hint = server_hint.casefold()
        for server, prompt in matches:
            if server.name.casefold() == hint:
                return server, prompt
        names = ", ".join(s.name for s, _ in matches)
        return f"No connected server named `{server_hint}` exposes `/{prompt_name}`. Try: {names}"

    if len(matches) > 1:
        names = ", ".join(f"`/{s.name}/{prompt_name}`" for s, _ in matches)
        return f"`/{prompt_name}` is ambiguous. Specify the server: {names}"

    return matches[0]


def _build_arguments(prompt: dict, trailing: str, slash: str) -> dict[str, str] | str:
    arg_defs = prompt.get("arguments") or []
    if not arg_defs:
        return {}

    required = [a["name"] for a in arg_defs if a.get("required", False)]
    if not trailing:
        if required:
            if len(required) == 1:
                arg = required[0]
                return (
                    f"`{slash}` requires `{arg}`. "
                    f"Example: `{slash} your-{arg.replace('_', '-')}`"
                )
            names = ", ".join(f"`{n}`" for n in required)
            return f"`{slash}` requires: {names}. Example: `{slash} {' '.join(f'{n}=...' for n in required)}`"
        return {}

    if len(arg_defs) == 1:
        return {arg_defs[0]["name"]: trailing}

    if "=" in trailing:
        parsed = {k: v.strip() for k, v in _KV_RE.findall(trailing)}
        missing = [n for n in required if n not in parsed]
        if missing:
            return f"`{slash}` is missing: {', '.join(missing)}. Example: `{slash} {' '.join(f'{n}=...' for n in required)}`"
        return parsed

    parts = trailing.split()
    if len(parts) < len(required):
        names = ", ".join(f"`{n}`" for n in required)
        return f"`{slash}` requires {len(required)} argument(s): {names}."

    args: dict[str, str] = {}
    for i, arg_def in enumerate(arg_defs):
        if i < len(parts):
            args[arg_def["name"]] = parts[i]
    return args


def _to_role_content(messages: list[BaseMessage]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for msg in messages:
        if isinstance(msg, HumanMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            out.append(("user", content))
        elif isinstance(msg, AIMessage):
            content = msg.content if isinstance(msg.content, str) else str(msg.content)
            out.append(("assistant", content))
    return out


async def _enrich_prompt(
    client: MultiServerMCPClient,
    server_name: str,
    prompt: dict,
) -> dict:
    """Fill in argument metadata when the cached snapshot is missing or stale."""
    cached = prompt.get("arguments")
    if cached:
        return prompt
    try:
        async with client.session(server_name) as session:
            prompts_res = await session.list_prompts()
    except Exception:
        return prompt
    for item in prompts_res.prompts:
        if item.name != prompt["name"]:
            continue
        enriched = dict(prompt)
        enriched["arguments"] = [
            {
                "name": a.name,
                "description": a.description or "",
                "required": a.required,
            }
            for a in (item.arguments or [])
        ]
        return enriched
    return prompt


async def resolve_slash_command(
    message: str,
    servers: list[McpServer],
    mcp_config: dict,
) -> SlashResolution | None:
    """If `message` is /prompt, fetch it from MCP and return expanded chat messages."""
    parsed = parse_slash_command(message, servers)
    if parsed is None:
        return None

    prompt_name, server_hint, trailing = parsed
    index = _prompt_index(servers)
    picked = _pick_server(prompt_name, server_hint, index)
    if isinstance(picked, str):
        return SlashResolution(
            prompt_name=prompt_name,
            server_name=server_hint or "",
            messages=[],
            error=picked,
        )

    server, prompt = picked
    client = MultiServerMCPClient({server.name: mcp_config[server.name]})
    prompt = await _enrich_prompt(client, server.name, prompt)

    ambiguous = len(index.get(prompt_name, [])) > 1
    slash = f"/{server.name}/{prompt_name}" if ambiguous else f"/{prompt_name}"

    args_result = _build_arguments(prompt, trailing, slash)
    if isinstance(args_result, str):
        return SlashResolution(
            prompt_name=prompt_name,
            server_name=server.name,
            messages=[],
            error=args_result,
        )

    trailing_text = ""
    arg_defs = prompt.get("arguments") or []
    if trailing and not arg_defs:
        trailing_text = trailing
    elif trailing and arg_defs and len(arg_defs) == 1:
        # Single-arg prompts consume all trailing text as the argument.
        trailing_text = ""
    elif trailing and arg_defs and len(arg_defs) > 1 and "=" not in trailing:
        parts = trailing.split()
        if len(parts) > len(arg_defs):
            trailing_text = " ".join(parts[len(arg_defs) :])

    if server.name not in mcp_config:
        return SlashResolution(
            prompt_name=prompt_name,
            server_name=server.name,
            messages=[],
            error=f"Server `{server.name}` is not available for chat.",
        )

    try:
        lc_messages = await asyncio.wait_for(
            client.get_prompt(server.name, prompt_name, arguments=args_result or None),
            timeout=settings.TOOL_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        return SlashResolution(
            prompt_name=prompt_name,
            server_name=server.name,
            messages=[],
            error=f"Timed out loading `/{prompt_name}` from {server.name}.",
        )
    except Exception as exc:  # noqa: BLE001
        return SlashResolution(
            prompt_name=prompt_name,
            server_name=server.name,
            messages=[],
            error=f"Failed to load `/{prompt_name}` from {server.name}: {exc}",
        )

    return SlashResolution(
        prompt_name=prompt_name,
        server_name=server.name,
        messages=_to_role_content(lc_messages),
        trailing_text=trailing_text,
    )
