from fastmcp import FastMCP


def create_mcp() -> FastMCP:
    """Create the MCP gateway without constructing domain services yet."""

    return FastMCP(name="Paper Helper MCP")


mcp = create_mcp()
