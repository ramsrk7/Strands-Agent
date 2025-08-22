#!/usr/bin/env python3
"""
client.py — tiny CLI for chatting with your FastAPI agent using a stable session_id.

Usage:
  python client.py --user-id ram
Options:
  --url http://localhost:8080          # API base URL
  --user-id ram                        # required (separates memories per actor)
  --session-id <id>                    # resume a specific session id (optional)
  --hooks / --no-hooks                 # enable Strands hooks (default: on)
  --long-term / --no-long-term         # manual hydration path (default: off when hooks on)
  --top-k 5                            # number of long-term snippets to bring in

Commands inside the chat:
  /new      -> start a new session id
  /id       -> show current session id
  /quit     -> exit
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

DEFAULT_URL = "http://localhost:8080"
SESS_DIR = Path(".agent_sessions")
SESS_DIR.mkdir(exist_ok=True)

def session_path(user_id: str) -> Path:
    return SESS_DIR / f"{user_id}.json"

def load_saved_session(user_id: str) -> Optional[str]:
    p = session_path(user_id)
    if p.exists():
        try:
            data = json.loads(p.read_text())
            return data.get("session_id")
        except Exception:
            return None
    return None

def save_session(user_id: str, session_id: str) -> None:
    p = session_path(user_id)
    p.write_text(json.dumps({"session_id": session_id}, indent=2))

def make_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="CLI client for Strands+AgentCore app")
    ap.add_argument("--url", default=DEFAULT_URL, help="Base URL for the API")
    ap.add_argument("--user-id", required=True, help="User id (actor_id)")
    ap.add_argument("--session-id", default=None, help="Start with an explicit session id")
    ap.add_argument("--hooks", dest="hooks", action="store_true", help="Enable hooks (default)")
    ap.add_argument("--no-hooks", dest="hooks", action="store_false", help="Disable hooks")
    ap.set_defaults(hooks=True)
    ap.add_argument("--long-term", dest="long_term", action="store_true", help="Use manual long-term hydration")
    ap.add_argument("--no-long-term", dest="long_term", action="store_false", help="Disable manual long-term hydration")
    ap.set_defaults(long_term=False)  # default off (hooks handle LT)
    ap.add_argument("--top-k", type=int, default=5, help="Top-k long-term snippets (hydration)")
    return ap

def post_invoke(base_url: str, user_id: str, prompt: str, session_id: Optional[str],
                use_hooks: bool, use_long_term: bool, top_k: int) -> dict:
    payload = {
        "user_id": user_id,
        "prompt": prompt,
        "use_hooks": use_hooks,
        "use_long_term": use_long_term,
        "long_term_top_k": top_k
    }
    if session_id:
        payload["session_id"] = session_id
    r = requests.post(f"{base_url}/invoke", json=payload, timeout=120)
    if r.status_code != 200:
        # Try to show server-provided detail if present
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        raise SystemExit(f"[ERROR] {r.status_code} from /invoke: {detail}")
    return r.json()

def main():
    args = make_parser().parse_args()

    base_url = args.url.rstrip("/")
    user_id = args.user_id
    session_id = args.session_id or load_saved_session(user_id)

    if session_id:
        print(f"[INFO] Resuming session_id={session_id!r} for user_id={user_id!r}")
    else:
        print(f"[INFO] No prior session found for user_id={user_id!r}. A new one will be created on first call.")

    print(f"[INFO] Hooks={'ON' if args.hooks else 'OFF'} | Manual LT Hydration={'ON' if args.long_term else 'OFF'} | top_k={args.top_k}")
    print("Type your message and press Enter. Commands: /new, /id, /quit")

    while True:
        try:
            user_input = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[INFO] Bye!")
            break

        if not user_input:
            continue

        # Commands
        if user_input.lower() in {"/quit", "/exit"}:
            print("[INFO] Bye!")
            break
        if user_input.lower() == "/id":
            print(f"[INFO] session_id={session_id!r}")
            continue
        if user_input.lower() == "/new":
            session_id = None
            print("[INFO] Started a NEW session (will be assigned on next message).")
            continue

        try:
            resp = post_invoke(
                base_url=base_url,
                user_id=user_id,
                prompt=user_input,
                session_id=session_id,
                use_hooks=args.hooks,
                use_long_term=args.long_term,
                top_k=args.top_k,
            )
        except SystemExit as e:
            print(e)
            continue
        except Exception as e:
            print(f"[ERROR] Request failed: {e}")
            continue

        # Update local session id if server generated a new one
        new_session = resp.get("session_id")
        if new_session and new_session != session_id:
            session_id = new_session
            save_session(user_id, session_id)
            print(f"[INFO] Assigned session_id={session_id!r} (saved)")

        # Print the assistant’s reply
        print(f"\nAssistant:\n{resp.get('result_text', '')}")

        # Optional: show quick debug info (comment out if noisy)
        debug = resp.get("debug", {})
        if debug:
            tool_count = debug.get("tool_count")
            hooks_enabled = debug.get("hooks_enabled", None)
            used_lt = debug.get("used_long_term", None)
            extra_bits = []
            if tool_count is not None:
                extra_bits.append(f"tools={tool_count}")
            if hooks_enabled is not None:
                extra_bits.append(f"hooks={hooks_enabled}")
            if used_lt is not None:
                extra_bits.append(f"manualLT={used_lt}")
            if extra_bits:
                print("[debug] " + ", ".join(extra_bits))

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Bye!")
        sys.exit(0)
