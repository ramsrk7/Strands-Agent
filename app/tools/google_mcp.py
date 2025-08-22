# tools/google_mcp_streamable.py
from __future__ import annotations
from mcp.client.streamable_http import streamablehttp_client
from strands.tools.mcp.mcp_client import MCPClient

def google_mcp_client(base_url: str = "http://127.0.0.1:8080/mcp") -> MCPClient:
    """
    Streamable HTTP MCP client for Google MCP (Gmail/Calendar).
    - Keep base_url pointing to your Google MCP server's /mcp endpoint.
    """
    return MCPClient(lambda: streamablehttp_client(base_url))
