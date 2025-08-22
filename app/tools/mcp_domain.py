from __future__ import annotations
from strands.tools.mcp import MCPClient
from mcp import stdio_client, StdioServerParameters

def domain_mcp_client() -> MCPClient:
    # fastdomaincheck-mcp-server must be available via `uvx`
    return MCPClient(lambda: stdio_client(
        StdioServerParameters(command="uvx", args=["fastdomaincheck-mcp-server"])
    ))

