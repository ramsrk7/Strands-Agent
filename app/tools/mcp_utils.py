from __future__ import annotations
from typing import Any, Iterable, List
from strands.tools.mcp.mcp_client import MCPClient

def gather_tools_from_mcps(clients: Iterable[MCPClient]) -> List[Any]:
    """
    Try to start each MCP client; if any fails, surface a diagnostic tool instead
    of crashing. Always stop successfully-started clients at the end.
    """
    all_tools: List[Any] = []
    started: List[MCPClient] = []

    # Try to start each client independently
    for c in clients:
        if c is None:
            continue
        try:
            c.start()  # open connection (instead of context manager)
            started.append(c)
        except Exception as e:
            all_tools.append(_make_diagnostic_tool(c, e))

    # For clients that started OK, list tools (each independently)
    for c in started:
        try:
            all_tools.extend(c.list_tools_sync())
        except Exception as e:
            all_tools.append(_make_diagnostic_tool(c, e))

    # Stop those clients we actually started
    for c in started:
        try:
            c.stop()
        except Exception:
            pass  # best-effort

    return all_tools

def _make_diagnostic_tool(client: MCPClient, err: Exception):
    class DiagnosticTool:
        name = f"diagnostic:{getattr(client, 'name', 'mcp')}"
        description = (
            "Diagnostics for an MCP client that failed to initialize or list tools. "
            f"Error: {type(err).__name__}: {err}"
        )
        input_schema = {"type": "object", "properties": {}}

        def __call__(self):
            return {"ok": False, "error": str(err)}

    return DiagnosticTool()
