"""FastMCP composition root.

The gateway owns protocol translation only. Domain capabilities are reached
through generated service clients once their contracts are implemented.
"""

from fastmcp import FastMCP


def create_mcp() -> FastMCP:
    """Create the MCP gateway without exposing unimplemented tools."""

    return FastMCP(name="Paper Helper MCP")


mcp = create_mcp()
