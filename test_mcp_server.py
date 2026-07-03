"""Throwaway MCP test server for Phase 5/6 verification. Not part of the app."""

import time

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("test-tools", host="127.0.0.1", port=9100)


@mcp.tool()
def get_magic_number(codename: str) -> int:
    """Look up the magic number registered for a given codename."""
    if codename.strip().lower() == "zephyr-9":
        return 471293
    return -1


@mcp.tool()
def hang_forever() -> str:
    """A tool that never returns in a reasonable time - for timeout testing."""
    time.sleep(120)
    return "should never get here"


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
