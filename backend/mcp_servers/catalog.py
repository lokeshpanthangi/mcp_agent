"""Loader for code-defined MCP servers (servers.json).

Developers add MCP servers here in code; they auto-load and show in the UI
alongside the ones users connect through the interface. Each entry:

    {"key": "weather", "name": "Weather", "url": "https://.../mcp",
     "transport": "streamable_http", "headers": {"Authorization": "Bearer ${TOKEN}"}}

`key`/`name`/`url` are required; `transport` defaults to "streamable_http";
`headers` is optional. Any ${ENV_VAR} inside a header value is filled from the
environment so secrets never live in the file.
"""

import json
import os
import re
from pathlib import Path

_SERVERS_FILE = Path(__file__).with_name("servers.json")
_ENV_REF = re.compile(r"\$\{([^}]+)\}")


def _expand_env(value: str) -> str:
    return _ENV_REF.sub(lambda m: os.environ.get(m.group(1), ""), value)


def load_code_servers() -> list[dict]:
    """Return the developer-defined MCP servers, with env refs in headers expanded."""
    try:
        entries = json.loads(_SERVERS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []
    for e in entries:
        if e.get("headers"):
            e["headers"] = {k: _expand_env(str(v)) for k, v in e["headers"].items()}
    return entries
