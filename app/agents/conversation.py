from __future__ import annotations
try:
    # Some versions don’t accept constructor args
    from strands.agent.conversation_manager import SlidingWindowConversationManager
except ImportError:
    SlidingWindowConversationManager = None  # type: ignore

def conversation_manager():
    if SlidingWindowConversationManager is None:
        return None
    # No kwargs for broad compatibility; tune later via attribute if available
    cm = SlidingWindowConversationManager()
    # Optional: if your version exposes the property, you can cap it:
    if hasattr(cm, "max_turns"):
        setattr(cm, "max_turns", 12)
    return cm
