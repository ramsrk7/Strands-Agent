import os, time, json
from datetime import datetime, timedelta
from botocore.exceptions import ClientError
import boto3
from bedrock_agentcore.memory import MemoryClient
from dotenv import load_dotenv
load_dotenv()

AWS_REGION = os.getenv("AWS_REGION", "us-west-2")

# Control plane (CRUD on the memory resource itself)
ctrl = boto3.client("bedrock-agentcore-control", region_name=AWS_REGION)
# Data plane (SDK helper for create_memory + events)
mem_client = MemoryClient(region_name=AWS_REGION)

def _ctrl_get_memory(memory_id: str) -> dict:
    print(f"[DEBUG] ctrl.get_memory({memory_id}) ...")
    return ctrl.get_memory(memoryId=memory_id)

def _ctrl_list_memories() -> list[dict]:
    print("[DEBUG] ctrl.list_memories() (paginated) ...")
    out = []
    next_token = None
    while True:
        resp = ctrl.list_memories(**({"nextToken": next_token} if next_token else {}))
        # API returns 'memories' (MemorySummary[])
        out.extend(resp.get("memories", []))
        next_token = resp.get("nextToken")
        if not next_token:
            break
    print(f"[DEBUG] ctrl.list_memories -> {len(out)} items")
    return out

def _poll_memory_status(memory_id: str, timeout_sec: int = 90) -> dict:
    print(f"[DEBUG] Polling memory status for {memory_id} up to {timeout_sec}s...")
    deadline = datetime.utcnow() + timedelta(seconds=timeout_sec)
    last = None
    while datetime.utcnow() < deadline:
        try:
            meta = _ctrl_get_memory(memory_id)["memory"]
            status = meta.get("status")
            if status != last:
                print(f"[DEBUG] Memory status = {status} (id={memory_id})")
                last = status
            if status in ("ACTIVE", "FAILED", "DELETING", "DELETED"):
                return meta
        except Exception as e:
            print(f"[DEBUG] get_memory error: {e!r}")
        time.sleep(3)
    raise TimeoutError(f"Memory {memory_id} did not become ACTIVE within {timeout_sec}s")

def _find_memory(target_name: str) -> dict | None:
    """Find by exact name, or by id that startswith the target_name."""
    found = []
    for m in _ctrl_list_memories():
        # control-plane summary includes id, status, createdAt, name (per docs)
        m_id = m.get("id")
        m_name = m.get("name")
        if m_name == target_name or (m_id and m_id.startswith(target_name)):
            print(f"[DEBUG] Matched memory summary: id={m_id} name={m_name}")
            try:
                full = _ctrl_get_memory(m_id)["memory"]
                print(f"[DEBUG] Resolved full memory: {full}")
                return full
            except Exception as e:
                print(f"[DEBUG] get_memory({m_id}) failed: {e!r}; returning summary")
                return {"id": m_id, "name": m_name, "status": m.get("status")}
        found.append(m)
    print("[DEBUG] No matching memory by name or id-prefix.")
    return None

def ensure_memory():
    # Fast path
    override_id = os.getenv("BEDROCK_MEMORY_ID")
    if override_id:
        print(f"[DEBUG] Using BEDROCK_MEMORY_ID override: {override_id}")
        return _poll_memory_status(override_id, timeout_sec=60)

    target_name = os.getenv("BEDROCK_MEMORY_NAME", "ProjectNamerMemory")
    print(f"[DEBUG] Searching for memory named '{target_name}' ...")
    existing = _find_memory(target_name)
    if existing:
        print("[DEBUG] Found existing memory; polling to confirm ACTIVE...")
        return _poll_memory_status(existing["id"], timeout_sec=60)

    # Not found -> create via data plane helper
    strategies = [{
        "summaryMemoryStrategy": {
            "name": "SessionSummarizer",
            "namespaces": ["/summaries/{actorId}/{sessionId}"]
        }
    }]
    try:
        print(f"[DEBUG] Creating memory '{target_name}' with strategies via MemoryClient ...")
        created = mem_client.create_memory(name=target_name, strategies=strategies)
        mem_id = created["id"]
        print(f"[DEBUG] create_memory -> id={mem_id} (now polling control plane)")
        return _poll_memory_status(mem_id, timeout_sec=90)
    except ClientError as e:
        msg = str(e)
        print(f"[DEBUG] create_memory failed: {msg}")
        if "already exists" in msg.lower():
            print("[DEBUG] Detected 'already exists' — re-finding and polling the existing memory...")
            existing = _find_memory(target_name)
            if not existing:
                raise RuntimeError("Create reported 'already exists' but finder couldn’t locate it.") from e
            return _poll_memory_status(existing["id"], timeout_sec=90)
        raise

# --- usage ---
memory_meta = ensure_memory()
MEMORY_ID = memory_meta["id"]
print(f"[DEBUG] USING MEMORY: id={MEMORY_ID} name={memory_meta.get('name')} status={memory_meta.get('status')}")
