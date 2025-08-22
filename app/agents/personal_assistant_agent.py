# app/agents/personal_assistant_agent.py
from __future__ import annotations
from typing import Any, Dict, Tuple, List
from contextlib import ExitStack

from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL_ID,
    OPENAI_MAX_TOKENS,
    OPENAI_TEMPERATURE,
    AWS_REGION,
)

from strands import Agent
from strands.models.openai import OpenAIModel

from agents.conversation import conversation_manager
from agents.hooks import LongTermMemoryHook

from tools.memory_tools import build_memory_tools
from tools.web_search import web_search_tools
from tools.mcp_utils import gather_tools_from_mcps

# Other MCPs
from tools.mcp_domain import domain_mcp_client
from tools.google_mcp import google_mcp_client  # Streamable HTTP Google MCP
from tools.google_strands_tools import calendar_request, gmail_request
from datetime import datetime
from zoneinfo import ZoneInfo  # stdlib

def now_in_tz(tz: str = "UTC") -> datetime:
    """Timezone-aware current datetime."""
    return datetime.now(ZoneInfo(tz))

def now_in_tz_iso(tz: str = "UTC") -> str:
    """ISO 8601 string with offset, e.g. 2025-08-22T10:05:23-07:00"""
    return now_in_tz(tz).isoformat()

# examples
print(now_in_tz("America/Los_Angeles"))
print(now_in_tz_iso("America/Los_Angeles"))


BASE_SYSTEM_PROMPT = f"""
You are a helpful, security-conscious personal assistant. Always retrieve memories first to get some context. Always address the user with their name. 
You can browse the web to find recent information and use MCP tools (Google, domain, etc.).
- Prefer least-privilege tools (read-only unless write is needed).
- When using web search, return citations (titles + URLs) along with concise summaries.
- If using Google tools, clearly state which Gmail/Calendar operation you're performing.
Be concise and structured in your final response.

Here's your current time: {now_in_tz("America/Los_Angeles")}
""".strip()

def _build_model():
    return OpenAIModel(
        client_args={"api_key": OPENAI_API_KEY},
        model_id=OPENAI_MODEL_ID,
        params={"max_tokens": OPENAI_MAX_TOKENS, "temperature": OPENAI_TEMPERATURE},
    )

def run_personal_assistant(
    prompt: str,
    *,
    memory_id: str,
    actor_id: str,
    session_id: str,
    summary_namespace: str,
    long_term_context: str = "",   # ← NEW: supports manual LT hydration
    use_hooks: bool = True,
    hooks_top_k: int = 5,
) -> Tuple[str, Dict[str, Any]]:
    """
    Single-turn invocation of the personal assistant.
    - If use_hooks=True: LongTermMemoryHook handles LT retrieval + writeback.
    - If use_hooks=False: any provided long_term_context is appended to system prompt.
    """
    model = _build_model()

    # Non-MCP tools
    mem_tools = build_memory_tools(
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        region=AWS_REGION,
        namespace=summary_namespace,
    )
    search_tools = web_search_tools()

    # Build system prompt (manual LT hydration only when hooks are off)
    system_prompt = BASE_SYSTEM_PROMPT
    if long_term_context and not use_hooks:
        system_prompt += "\n\n# Long-term user context (read-only)\n" + long_term_context.strip()

    # Prepare MCP clients; ensure they are active while calling the agent
    mcp_clients = [                # stdio MCP (uvx fastdomaincheck-mcp-server)
        google_mcp_client(base_url="http://localhost:8080/mcp"),  # HTTP MCP (example)
    ]

    with ExitStack() as stack:
        # Enter all MCP client contexts so tool calls don't fail
        for c in mcp_clients:
            stack.enter_context(c)

        #mcp_tools = gather_tools_from_mcps(mcp_clients)
        google_tools = [calendar_request, gmail_request]
        print("MCP Tools: ", google_tools)
        tools: List[Any] = search_tools + mem_tools + google_tools

        cm = conversation_manager()
        agent_kwargs: Dict[str, Any] = {
            "model": model,
            "system_prompt": system_prompt,
            "tools": tools,
        }
        if use_hooks:
            agent_kwargs["hooks"] = [LongTermMemoryHook(memory_id=memory_id, actor_id=actor_id, top_k=hooks_top_k)]
        if cm is not None:
            agent_kwargs["conversation_manager"] = cm

        agent = Agent(**agent_kwargs)
        result = agent(prompt)

    result_text = getattr(result, "text", None) or str(result)
    return result_text, {
        "tool_count": len(tools),
        "tools": [getattr(t, "name", str(t)) for t in tools],
        "hooks_enabled": use_hooks,
        "manual_lt_injected": bool(long_term_context and not use_hooks),
    }
