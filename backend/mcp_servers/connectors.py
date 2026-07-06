"""Catalog of well-known remote MCP servers offered as one-click connectors.

Data lives in connectors.json (content, not config). Most use OAuth — the user
clicks Connect and authorizes in a popup. Set `"auth": "token"` when the provider
needs a pasted personal access token (e.g. GitHub), or `"auth": "open"` when no
credentials are required.
"""

import json
from pathlib import Path

_CONNECTORS_FILE = Path(__file__).with_name("connectors.json")


def _load() -> list[dict]:
    try:
        return json.loads(_CONNECTORS_FILE.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return []


CONNECTORS: list[dict] = _load()
CONNECTORS_BY_KEY: dict[str, dict] = {c["key"]: c for c in CONNECTORS}
