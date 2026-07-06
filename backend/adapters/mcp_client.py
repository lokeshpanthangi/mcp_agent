import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

_AUTH_HINTS = ("401", "403", "unauthorized", "authentication", "forbidden", "www-authenticate")


def infer_transport(url: str) -> str:
    """Guess transport from URL path conventions."""
    lower = url.lower().rstrip("/")
    if lower.endswith("/sse") or "/sse/" in lower:
        return "sse"
    return "streamable_http"


def transport_candidates(url: str) -> list[str]:
    """Transports to try, most likely first."""
    primary = infer_transport(url)
    secondary = "sse" if primary == "streamable_http" else "streamable_http"
    return [primary, secondary]


def _exception_message(exc: BaseException) -> str:
    """Human-readable message, unwrapping ExceptionGroup/TaskGroup sub-errors."""
    parts: list[str] = []

    def walk(e: BaseException) -> None:
        if isinstance(e, BaseExceptionGroup):
            for sub in e.exceptions:
                walk(sub)
        else:
            parts.append(str(e))

    walk(exc)
    return " | ".join(dict.fromkeys(parts))[:300]


def _looks_like_auth_error(exc: BaseException) -> bool:
    msg = _exception_message(exc).lower()
    return any(h in msg for h in _AUTH_HINTS)


async def _inspect(name: str, config_entry: dict) -> dict:
    client = MultiServerMCPClient({name: config_entry})
    async with client.session(name) as session:
        tools_res = await session.list_tools()
        tools = [
            {
                "name": t.name,
                "description": t.description or "",
                "input_schema": t.inputSchema or {},
            }
            for t in tools_res.tools
        ]
        prompts = []
        try:
            prompts_res = await session.list_prompts()
            prompts = [
                {
                    "name": p.name,
                    "description": p.description or "",
                    "arguments": [
                        {
                            "name": a.name,
                            "description": a.description or "",
                            "required": a.required,
                        }
                        for a in (p.arguments or [])
                    ],
                }
                for p in prompts_res.prompts
            ]
        except Exception:
            pass
    return {"ok": True, "needs_auth": False, "error": None, "tools": tools, "prompts": prompts}


async def inspect_server(name: str, config_entry: dict, timeout: float) -> dict:
    """Connect to one MCP server and list its tools + prompts."""
    task = asyncio.ensure_future(_inspect(name, config_entry))
    _, pending = await asyncio.wait({task}, timeout=timeout)
    if task in pending:
        task.cancel()
        return {
            "ok": False,
            "needs_auth": False,
            "error": "Timed out connecting to the MCP server.",
            "tools": [],
            "prompts": [],
        }
    try:
        return task.result()
    except BaseException as exc:
        return {
            "ok": False,
            "needs_auth": _looks_like_auth_error(exc),
            "error": _exception_message(exc),
            "tools": [],
            "prompts": [],
        }


async def inspect_server_with_fallback(
    name: str, url: str, headers: dict | None, timeout: float
) -> tuple[dict, str]:
    """Try streamable HTTP and SSE; return the best result and working transport."""
    base: dict = {"url": url}
    if headers:
        base["headers"] = headers

    best_fail: dict | None = None
    best_transport = infer_transport(url)

    for transport in transport_candidates(url):
        entry = {**base, "transport": transport}
        result = await inspect_server(name, entry, timeout)
        if result["ok"] or result["needs_auth"]:
            return result, transport
        best_fail = result
        best_transport = transport

    return best_fail or {
        "ok": False,
        "needs_auth": False,
        "error": "Could not connect to the MCP server.",
        "tools": [],
        "prompts": [],
    }, best_transport
