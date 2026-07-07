"""Build MCP tool / slash-command sections appended to the system prompt."""

import json

from database.models import McpServer
from mcp_servers.connectors import CONNECTORS_BY_KEY


def server_usable_in_chat(server: McpServer) -> bool:
    """Include in the agent only servers that can actually load tools."""
    if server.headers_json:
        return True
    if server.tools_snapshot_json:
        return True
    connector = CONNECTORS_BY_KEY.get(server.connector_key or "") or {}
    return connector.get("auth") == "open"


def _server_ready(server: McpServer) -> bool:
    return server_usable_in_chat(server)


def build_mcp_commands_section(servers: list[McpServer]) -> str:
    """Describe connected MCP tools and /prompt commands for the model."""
    blocks: list[str] = []
    for server in servers:
        if not _server_ready(server):
            continue
        tools = json.loads(server.tools_snapshot_json) if server.tools_snapshot_json else []
        prompts = json.loads(server.prompts_snapshot_json) if server.prompts_snapshot_json else []
        if not tools and not prompts:
            continue
        lines = [f"\n### {server.name}"]
        if tools:
            lines.append("Tools (call by exact name):")
            for t in tools:
                desc = (t.get("description") or "").strip()
                lines.append(f"- `{t['name']}`" + (f" — {desc}" if desc else ""))
        if prompts:
            lines.append("Slash-commands (MCP prompts — user may type /name <args>):")
            for p in prompts:
                desc = (p.get("description") or "").strip()
                args = p.get("arguments") or []
                req = [a["name"] for a in args if a.get("required")]
                suffix = f" <{req[0]}>" if len(req) == 1 else ""
                if len(req) > 1:
                    suffix = " " + " ".join(f"{n}=..." for n in req)
                lines.append(f"- `/{p['name']}{suffix}`" + (f" — {desc}" if desc else ""))
        blocks.append("\n".join(lines))

    if not blocks:
        return ""
    header = (
        "\n\n## Connected MCP servers\n"
        "Use the tools below when they help answer the user. "
        "MCP prompts are available as slash-commands (/prompt-name). When the user types one,\n"
        "the server resolves it via MCP get_prompt before you respond.\n"
    )
    return header + "\n".join(blocks)
