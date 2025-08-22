# app/agents/hooks.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Iterable

from memory.session import profile_session_id, summary_namespace
from memory.client import mem_client

# Strands hooks (names are stable in recent versions)
from strands.hooks import HookProvider
from strands.hooks.events import BeforeInvocationEvent, AfterInvocationEvent

@dataclass
class LongTermMemoryHook(HookProvider):
    """Hydrates long-term context before each turn and writes back after."""
    memory_id: str
    actor_id: str
    top_k: int = 5
    query: str = "summarize user preferences, tone, style, constraints"

    def before_invocation(self, event: BeforeInvocationEvent):
        agent = event.agent
        m = mem_client()
        ns = summary_namespace(self.actor_id, profile_session_id(self.actor_id))
        try:
            hits = m.retrieve_memories(
                memory_id=self.memory_id,
                namespace=ns,
                query=self.query,
                top_k=self.top_k,
            )
            snippets: list[str] = []
            # AgentCore returns different shapes depending on SDK; be defensive:
            recs: Iterable = (
                (hits or {}).get("records")
                or (hits or {}).get("items")
                or (hits if isinstance(hits, list) else [])
            )
            for r in recs:
                text = (
                    getattr(r, "text", None)
                    or r.get("text")  # type: ignore[attr-defined]
                    or r.get("summary")  # type: ignore[attr-defined]
                    or r.get("content")  # type: ignore[attr-defined]
                )
                if text:
                    snippets.append(f"- {text}")
            if snippets:
                agent.system_prompt += "\n\n# Long-term user context (read-only)\n" + "\n".join(
                    snippets[: self.top_k]
                )
        except Exception:
            # Non-fatal: if retrieval fails we proceed without augmentation
            pass

    def after_invocation(self, event: AfterInvocationEvent):
        """Mirror turn into the per-user profile stream for durable recall."""
        try:
            request = event.request
            response = event.response
            m = mem_client()
            lt_session = profile_session_id(self.actor_id)
            m.create_event(
                memory_id=self.memory_id,
                actor_id=self.actor_id,
                session_id=lt_session,
                messages=[
                    (str(getattr(request, "input", "")), "USER"),
                    (str(response), "ASSISTANT"),
                ],
            )
        except Exception:
            pass
