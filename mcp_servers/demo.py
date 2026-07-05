"""Demo MCP server for Anvil — proves the MCP pipeline with zero external deps.

Registered in ~/.anvil/mcp.json. Real servers (GitHub, Postgres, browsers...)
plug in exactly the same way.
"""
from __future__ import annotations

import datetime

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("anvil-demo")


@mcp.tool()
def current_time() -> str:
    """Get the current local date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


@mcp.tool()
def calculate(expression: str) -> str:
    """Safely evaluate an arithmetic expression like '2*(3+4)'."""
    allowed = set("0123456789+-*/(). %")
    if not set(expression) <= allowed:
        return "ERROR: only arithmetic characters allowed"
    try:
        return str(eval(expression, {"__builtins__": {}}, {}))
    except Exception as e:
        return f"ERROR: {e}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
