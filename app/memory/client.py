from __future__ import annotations
import os
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import boto3
from botocore.exceptions import ClientError
from bedrock_agentcore.memory import MemoryClient

from config import AWS_REGION, BEDROCK_MEMORY_ID, BEDROCK_MEMORY_NAME

# Control plane (describe/list memory resources)
_ctrl = boto3.client("bedrock-agentcore-control", region_name=AWS_REGION)
# Data plane (create memory + write/read events)
_mem = MemoryClient(region_name=AWS_REGION)

def ctrl_list_memories() -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    token = None
    while True:
        resp = _ctrl.list_memories(**({"nextToken": token} if token else {}))
        out.extend(resp.get("memories", []))
        token = resp.get("nextToken")
        if not token:
            break
    return out

def ctrl_get_memory(memory_id: str) -> Dict[str, Any]:
    return _ctrl.get_memory(memoryId=memory_id)["memory"]

def poll_memory_status(memory_id: str, timeout_sec: int = 90) -> Dict[str, Any]:
    deadline = datetime.utcnow() + timedelta(seconds=timeout_sec)
    last = None
    while datetime.utcnow() < deadline:
        try:
            mem = ctrl_get_memory(memory_id)
            status = mem.get("status")
            if status != last:
                print(f"[DEBUG] Memory {memory_id} status = {status}")
                last = status
            if status in ("ACTIVE", "FAILED", "DELETING", "DELETED"):
                return mem
        except Exception as e:
            print(f"[DEBUG] get_memory error: {e!r}")
        time.sleep(3)
    raise TimeoutError(f"Memory {memory_id} did not become ACTIVE within {timeout_sec}s")

def find_memory_by_name_or_prefix(target_name: str) -> Optional[Dict[str, Any]]:
    for m in ctrl_list_memories():
        m_id = m.get("id")
        m_name = m.get("name")
        if m_name == target_name or (m_id and m_id.startswith(target_name)):
            try:
                return ctrl_get_memory(m_id)
            except Exception as e:
                print(f"[DEBUG] ctrl_get_memory({m_id}) failed: {e!r}; returning summary")
                return {"id": m_id, "name": m_name, "status": m.get("status")}
    return None

def ensure_memory(name: Optional[str] = None) -> Dict[str, Any]:
    """Ensure a Memory resource exists and is ACTIVE. Returns full memory dict."""
    target_name = name or BEDROCK_MEMORY_NAME

    # Fast path via explicit ID
    if BEDROCK_MEMORY_ID:
        print(f"[DEBUG] Using BEDROCK_MEMORY_ID override: {BEDROCK_MEMORY_ID}")
        return poll_memory_status(BEDROCK_MEMORY_ID, timeout_sec=60)

    # Try find existing by name/id-prefix
    print(f"[DEBUG] Searching for memory named '{target_name}' ...")
    existing = find_memory_by_name_or_prefix(target_name)
    if existing:
        print("[DEBUG] Found existing memory; polling to confirm ACTIVE...")
        return poll_memory_status(existing["id"], timeout_sec=60)

    # Not found -> create via data plane helper
    strategies = [{
        "summaryMemoryStrategy": {
            "name": "SessionSummarizer",
            "namespaces": ["/summaries/{actorId}/{sessionId}"]
        }
    }]
    try:
        print(f"[DEBUG] Creating memory '{target_name}' with strategies via MemoryClient ...")
        created = _mem.create_memory(name=target_name, strategies=strategies)
        mem_id = created["id"]
        print(f"[DEBUG] create_memory -> id={mem_id} (polling)")
        return poll_memory_status(mem_id, timeout_sec=90)
    except ClientError as e:
        msg = str(e)
        print(f"[DEBUG] create_memory failed: {msg}")
        if "already exists" in msg.lower():
            print("[DEBUG] Detected 'already exists' — re-finding and polling the existing memory...")
            existing = find_memory_by_name_or_prefix(target_name)
            if not existing:
                raise RuntimeError("Create reported 'already exists' but finder couldn’t locate it.") from e
            return poll_memory_status(existing["id"], timeout_sec=90)
        raise

def mem_client() -> MemoryClient:
    """Expose the initialized data-plane client."""
    return _mem
