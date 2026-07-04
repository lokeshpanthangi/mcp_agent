import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

_AUTH_HINTS = ("401", "403", "unauthorized", "authentication", "forbidden", "www-authenticate")


def _looks_like_auth_error(exc: Exception) -> bool:
    msg = str(exc).lower()
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
                {"name": p.name, "description": p.description or ""} for p in prompts_res.prompts
            ]
        except Exception:
            pass  # server may not support prompts - that's fine
    return {"ok": True, "needs_auth": False, "error": None, "tools": tools, "prompts": prompts}


async def inspect_server(name: str, config_entry: dict, timeout: float) -> dict:
    """Connect to one MCP server and list its tools + prompts.

    Returns a dict: {ok, needs_auth, error, tools, prompts}. Never raises -
    connection/auth/timeout failures are reported in the return value so the
    UI can show a Connect button or an error instead of a 500.
    """
    task = asyncio.ensure_future(_inspect(name, config_entry))
    _, pending = await asyncio.wait({task}, timeout=timeout)
    if task in pending:
        task.cancel()  # fire-and-forget - don't await a possibly-stuck teardown
        return {
            "ok": False,
            "needs_auth": False,
            "error": "Timed out connecting to the MCP server.",
            "tools": [],
            "prompts": [],
        }
    try:
        return task.result()
    except Exception as exc:  # noqa: BLE001 - report every failure to the caller
        return {
            "ok": False,
            "needs_auth": _looks_like_auth_error(exc),
            "error": str(exc)[:300],
            "tools": [],
            "prompts": [],
        }
