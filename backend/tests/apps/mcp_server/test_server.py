from fastmcp import Client

from paper_helper.apps.mcp_server.server import create_mcp


async def test_mcp_server_starts_without_exposing_unimplemented_tools() -> None:
    server = create_mcp()

    async with Client(server) as client:
        tools = await client.list_tools()

    assert tools == []
