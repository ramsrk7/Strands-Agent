# app/memory/session.py
from __future__ import annotations
import uuid

def actor_id_for_user(user_id: str) -> str:
    return user_id

def session_id_or_default(session_id: str | None) -> str:
    return session_id or f"session-{uuid.uuid4().hex[:8]}"

def profile_session_id(actor_id: str) -> str:
    """Stable pseudo-session used to accumulate durable long-term memories."""
    return f"profile-{actor_id}"

def summary_namespace(actor_id: str, session_id: str) -> str:
    return f"/summaries/{actor_id}/{session_id}"
