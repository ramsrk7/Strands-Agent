from __future__ import annotations
from typing import List, Any
from strands_tools.agent_core_memory import AgentCoreMemoryToolProvider

def build_memory_tools(memory_id: str, actor_id: str, session_id: str, region: str, namespace: str) -> List[Any]:
    """Expose AgentCore Memory as Strands tools for store/recall."""
    return AgentCoreMemoryToolProvider(
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        namespace=namespace,
        region=region,
    ).tools
