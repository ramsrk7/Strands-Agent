# test_google_mcp_connect.py
import os
from strands.tools.mcp.mcp_client import MCPClient
from mcp.client.streamable_http import streamablehttp_client

URL = os.getenv("GOOGLE_MCP_URL", "http://127.0.0.1:8080/mcp")
print("Testing", URL)

client = MCPClient(lambda: streamablehttp_client(URL))
try:
    client.start()
    print("Connected.")
    tools = client.list_tools_sync()
    print("Tools:", [getattr(t, "name", str(t)) for t in tools])
finally:
    try:
        client.stop()
    except Exception:
        pass
