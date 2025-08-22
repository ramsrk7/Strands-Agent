# app/main.py
from __future__ import annotations
import uvicorn
from fastapi import FastAPI, HTTPException, APIRouter
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from contextlib import asynccontextmanager
import logging

# Configure the root strands logger
logging.getLogger("strands").setLevel(logging.DEBUG)

# Add a handler to see the logs
logging.basicConfig(
    format="%(levelname)s | %(name)s | %(message)s", 
    handlers=[logging.StreamHandler()]
)
from config import AWS_REGION, APP_DEBUG
from memory.client import ensure_memory, mem_client
from memory.session import (
    actor_id_for_user,
    session_id_or_default,
    summary_namespace,
    profile_session_id,
)

class InvokeRequest(BaseModel):
    user_id: str
    prompt: str
    session_id: Optional[str] = None
    use_long_term: bool = True     # manual hydration path
    use_hooks: bool = False        # <-- NEW: toggle the hook path
    long_term_top_k: int = 5

class InvokeResponse(BaseModel):
    memory_id: str
    actor_id: str
    session_id: str
    result_text: str
    debug: Dict[str, Any] = {}

class MemorySearchRequest(BaseModel):
    user_id: str
    query: str
    scope: str = Field("profile", pattern="^(profile|session)$")
    session_id: Optional[str] = None

class MemorySearchResponse(BaseModel):
    memory_id: str
    actor_id: str
    namespace: str
    hits: Any

@asynccontextmanager
async def lifespan(app: FastAPI):
    mem = ensure_memory()
    app.state.memory = mem
    app.state.memory_id = mem["id"]
    yield

app = FastAPI(title="Strands + Bedrock AgentCore Memory App", lifespan=lifespan)
router = APIRouter()

def _extract_text_snippets(hits: Any, max_snippets: int = 5) -> str:
    """
    Make a readable snippet block from retrieve_memories(..) results.
    AgentCore returns 'records' (API) / SDK wrappers may return a dict/list.
    We defensively fish for text-ish fields.
    """
    try:
        records = (
            (hits or {}).get("records")
            or (hits or {}).get("items")
            or (hits if isinstance(hits, list) else [])
        )
    except Exception:
        records = hits if isinstance(hits, list) else []
    out: list[str] = []
    for r in records[:max_snippets]:
        text = (
            r.get("text")
            or r.get("content")
            or r.get("value")
            or r.get("summary")
            or str(r)
        )
        out.append(f"- {text}")
    return "\n".join(out)

@router.post("/invoke", response_model=InvokeResponse)
def invoke(req: InvokeRequest):
    memory_id = getattr(app.state, "memory_id", None)
    if not memory_id:
        raise HTTPException(500, "Memory not initialized")

    actor_id = actor_id_for_user(req.user_id)
    session_id = session_id_or_default(req.session_id)
    namespace = summary_namespace(actor_id, session_id)

    long_term_context = ""
    if req.use_long_term and not req.use_hooks:
        # Manual hydration path
        try:
            m = mem_client()
            lt_ns = summary_namespace(actor_id, profile_session_id(actor_id))
            hits = m.retrieve_memories(
                memory_id=memory_id,
                namespace=lt_ns,
                query="summarize user preferences, tone, style, constraints",
                top_k=req.long_term_top_k,
            )
            long_term_context = _extract_text_snippets(hits, req.long_term_top_k)
        except Exception:
            long_term_context = ""

    # Run agent (hooks do hydration + writeback automatically)
    from agents.naming_agent import run_naming_agent
    from agents.personal_assistant_agent import run_personal_assistant
    result_text, meta = run_personal_assistant(
        req.prompt,
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        summary_namespace=namespace,
        long_term_context=long_term_context,
        use_hooks=req.use_hooks,               # <-- pass through
        hooks_top_k=req.long_term_top_k,
    )

    # Persist short-term events always
    m = mem_client()
    errors: Dict[str, str] = {}
    try:
        m.create_event(
            memory_id=memory_id,
            actor_id=actor_id,
            session_id=session_id,
            messages=[(req.prompt, "USER"), (result_text, "ASSISTANT")],
        )
    except Exception as e:
        errors["short_term_write_error"] = repr(e)

    # Only mirror to long-term profile if NOT using hooks (hook does it)
    if not req.use_hooks:
        try:
            lt_session = profile_session_id(actor_id)
            m.create_event(
                memory_id=memory_id,
                actor_id=actor_id,
                session_id=lt_session,
                messages=[(req.prompt, "USER"), (result_text, "ASSISTANT")],
            )
        except Exception as e:
            errors["long_term_write_error"] = repr(e)

    return InvokeResponse(
        memory_id=memory_id,
        actor_id=actor_id,
        session_id=session_id,
        result_text=result_text,
        debug={"region": AWS_REGION, **meta, **errors},
    )


@router.post("/memories/search", response_model=MemorySearchResponse)
def memories_search(req: MemorySearchRequest):
    memory_id = getattr(app.state, "memory_id", None)
    if not memory_id:
        raise HTTPException(500, "Memory not initialized")

    actor_id = actor_id_for_user(req.user_id)
    if req.scope == "profile":
        lt_session = profile_session_id(actor_id)
        ns = summary_namespace(actor_id, lt_session)
    else:
        if not req.session_id:
            raise HTTPException(400, "session_id is required when scope='session'")
        ns = summary_namespace(actor_id, req.session_id)

    try:
        m = mem_client()
        hits = m.retrieve_memories(memory_id=memory_id, namespace=ns, query=req.query)
    except Exception as e:
        raise HTTPException(500, f"retrieve_memories failed: {e!r}")

    return MemorySearchResponse(memory_id=memory_id, actor_id=actor_id, namespace=ns, hits=hits)

app.include_router(router)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8008, reload=APP_DEBUG)
