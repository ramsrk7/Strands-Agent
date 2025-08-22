# app/agents/naming_agent.py
from __future__ import annotations
from typing import Any, Dict, Tuple, List, Optional

from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL_ID,
    OPENAI_MAX_TOKENS,
    OPENAI_TEMPERATURE,
    AWS_REGION,
)
from tools.memory_tools import build_memory_tools
from tools.mcp_domain import domain_mcp_client
from tools.github_http import github_tools
from agents.conversation import conversation_manager
from agents.hooks import LongTermMemoryHook  # <-- NEW

from strands import Agent
from strands.models.openai import OpenAIModel

BASE_SYSTEM_PROMPT = """
You are a helpful assistant that proposes names for open-source projects about building AI agents.
Requirements:
- Provide at least 3 name ideas.
- For each idea, validate one available domain (.io or .dev) and one available GitHub org handle.
- Use the provided tools to check availability before answering.
Be concise and structured.
"""

def _build_model() -> OpenAIModel:
    return OpenAIModel(
        client_args={"api_key": OPENAI_API_KEY},
        model_id=OPENAI_MODEL_ID,
        params={"max_tokens": OPENAI_MAX_TOKENS, "temperature": OPENAI_TEMPERATURE},
    )

def run_naming_agent(
    prompt: str,
    *,
    memory_id: str,
    actor_id: str,
    session_id: str,
    summary_namespace: str,
    long_term_context: str = "",     # still supported if you want manual hydration
    use_hooks: bool = False,         # <-- NEW: enable hooks path
    hooks_top_k: int = 5,            # <-- NEW
) -> Tuple[str, Dict[str, Any]]:
    model = _build_model()

    # Tools including memory tools
    mem_tools = build_memory_tools(
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        region=AWS_REGION,
        namespace=summary_namespace,
    )

    # System prompt; if not using hooks, we can still inject context manually
    system_prompt = BASE_SYSTEM_PROMPT
    if long_term_context and not use_hooks:
        system_prompt += "\n\n# Long-term user context (read-only)\n" + long_term_context.strip()

    mcp = domain_mcp_client()
    with mcp:
        tools: List[Any] = mcp.list_tools_sync() + github_tools() + mem_tools
        cm = conversation_manager()

        agent_kwargs: Dict[str, Any] = {
            "model": model,
            "system_prompt": system_prompt,
            "tools": tools,
        }
        # Register hooks like in the AWS notebook
        if use_hooks:
            agent_kwargs["hooks"] = [LongTermMemoryHook(memory_id=memory_id, actor_id=actor_id, top_k=hooks_top_k)]

        if cm is not None:
            agent_kwargs["conversation_manager"] = cm

        agent = Agent(**agent_kwargs)
        result = agent(prompt)

    result_text = getattr(result, "text", None) or str(result)
    meta = {
        "tool_count": len(tools),
        "tools": [getattr(t, "name", str(t)) for t in tools],
        "hooks_enabled": use_hooks,
    }
    return result_text, meta
