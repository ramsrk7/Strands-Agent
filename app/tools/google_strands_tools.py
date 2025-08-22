from __future__ import annotations

import os
import time
from typing import Optional, Dict, Any
import requests
from strands import tool

# ---------- Config ----------
GOOGLE_TOKEN_URI = os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REFRESH_TOKEN_DEFAULT = os.getenv("GOOGLE_REFRESH_TOKEN")  # optional fallback
refresh_token = GOOGLE_REFRESH_TOKEN_DEFAULT
GOOGLE_TOOLS_DEBUG = os.getenv("GOOGLE_TOOLS_DEBUG", "0") == "1"

# Simple in-memory access-token cache (per refresh token)
_token_cache: Dict[str, Dict[str, Any]] = {}
def _dbg(msg: str):
    if GOOGLE_TOOLS_DEBUG:
        print(f"[google-tools] {msg}")

def _get_access_token(refresh_token: str) -> str:
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        raise RuntimeError("Set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET env vars.")

    cache = _token_cache.get(refresh_token)
    now = time.time()
    if cache and cache.get("expires_at", 0) > now + 30:
        return cache["access_token"]

    data = {
        "grant_type": "refresh_token",
        "client_id": GOOGLE_CLIENT_ID,
        "client_secret": GOOGLE_CLIENT_SECRET,
        "refresh_token": refresh_token,
    }
    resp = requests.post(GOOGLE_TOKEN_URI, data=data, timeout=30)
    if not resp.ok:
        raise RuntimeError(f"Token refresh failed: {resp.status_code} {resp.text}")

    payload = resp.json()
    access_token = payload["access_token"]
    expires_in = int(payload.get("expires_in", 3600))
    _token_cache[refresh_token] = {
        "access_token": access_token,
        "expires_at": now + expires_in - 60,  # small safety buffer
    }
    return access_token

def _pick_refresh_token(refresh_token: Optional[str]) -> str:
    token = refresh_token or GOOGLE_REFRESH_TOKEN_DEFAULT
    if not token:
        raise RuntimeError("Provide refresh_token or set GOOGLE_REFRESH_TOKEN.")
    return token

def _google_request(
    base_url: str,
    path: str,
    method: str = "GET",
    query: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Generic Google REST request helper.
    - base_url: e.g. 'https://gmail.googleapis.com/gmail/v1' or 'https://www.googleapis.com/calendar/v3'
    - path: path segment like 'users/me/messages' or 'calendars/primary/events'
    - method: 'GET' | 'POST' | 'PATCH' | 'DELETE'
    - query: dict of querystring params
    - body: dict JSON body for POST/PATCH
    """
    token = _pick_refresh_token(refresh_token)
    access_token = _get_access_token(token)

    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    if method.upper() in ("POST", "PATCH"):
        headers["Content-Type"] = "application/json"

    _dbg(f"{method} {url} query={query} body_keys={list((body or {}).keys())}")

    try:
        if method.upper() == "GET":
            r = requests.get(url, headers=headers, params=query, timeout=30)
        elif method.upper() == "POST":
            r = requests.post(url, headers=headers, params=query, json=body, timeout=30)
        elif method.upper() == "PATCH":
            r = requests.patch(url, headers=headers, params=query, json=body, timeout=30)
        elif method.upper() == "DELETE":
            r = requests.delete(url, headers=headers, params=query, timeout=30)
        else:
            return {"ok": False, "error": f"Unsupported method: {method}"}

        content = r.json() if "application/json" in r.headers.get("Content-Type", "") else r.text
        return {"ok": r.ok, "status": r.status_code, "data": content, "headers": dict(r.headers)}
    except Exception as e:
        return {"ok": False, "error": str(e)}

# ---------- Tools ----------
@tool(description="""
Gmail (read-only) generic API call. Ask the LLM to build 'path' and 'query' for Gmail v1.
Examples:
- List messages: path='users/me/messages', query={'q': 'in:inbox newer_than:7d', 'maxResults': 5}
- Get message metadata: path='users/me/messages/{id}', query={'format': 'metadata'}
""")
def gmail_request(
    path: str,
    method: str = "GET",
    query: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return _google_request(
        base_url="https://gmail.googleapis.com/gmail/v1",
        path=path,
        method=method,
        query=query,
        body=body,
    )

@tool(description="""
Calendar (read-only) generic API call. Ask the LLM to build 'path' and 'query' for Calendar v3.
Examples:
- Upcoming events: path='calendars/primary/events',
  query={'timeMin': '2025-08-22T00:00:00Z', 'timeMax': '2025-08-29T00:00:00Z',
         'singleEvents': True, 'orderBy': 'startTime', 'maxResults': 10}
- Get an event: path='calendars/primary/events/{eventId}'
""")
def calendar_request(
    path: str,
    method: str = "GET",
    query: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    return _google_request(
        base_url="https://www.googleapis.com/calendar/v3",
        path=path,
        method=method,
        query=query,
        body=body
    )
