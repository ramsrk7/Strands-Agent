# tools/web_search.py
from __future__ import annotations
from typing import Any, Dict, List, Optional

"""
A lightweight web search tool for your agent.

It tries Tavily (if TAVILY_API_KEY is set) and falls back to DuckDuckGo via
the `duckduckgo_search` package (pip install duckduckgo-search).
Returns a compact list of {title, url, snippet}.
"""

import os
import time

def web_search_tools():
    return [WebSearchTool()]

class WebSearchTool:
    name = "web_search"
    description = (
        "Search the web for recent information. "
        "Args: { query: string, max_results?: number (default 5) }"
    )
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
        },
        "required": ["query"],
        "additionalProperties": False,
    }

    def __call__(self, query: str, max_results: int = 5) -> Dict[str, Any]:
        # Prefer Tavily if available
        tavily_key = os.getenv("TAVILY_API_KEY")
        if tavily_key:
            try:
                return {"engine": "tavily", "results": _tavily_search(tavily_key, query, max_results)}
            except Exception as e:
                return {"engine": "tavily", "error": str(e), "results": []}
        # Fallback: DuckDuckGo
        try:
            return {"engine": "duckduckgo", "results": _ddg_search(query, max_results)}
        except Exception as e:
            return {"engine": "duckduckgo", "error": str(e), "results": []}

def _tavily_search(api_key: str, query: str, max_results: int) -> List[Dict[str, str]]:
    import requests
    resp = requests.post(
        "https://api.tavily.com/search",
        json={"api_key": api_key, "query": query, "max_results": max_results, "include_answer": False},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    out = []
    for r in data.get("results", [])[:max_results]:
        out.append({
            "title": r.get("title") or r.get("url", ""),
            "url": r.get("url", ""),
            "snippet": r.get("content", "")[:300],
        })
    return out

def _ddg_search(query: str, max_results: int) -> List[Dict[str, str]]:
    from duckduckgo_search import DDGS  # pip install duckduckgo-search
    out: List[Dict[str, str]] = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results, region="wt-wt", safesearch="moderate"):
            out.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": r.get("body", "")[:300],
            })
            time.sleep(0.15)  # be gentle
    return out
