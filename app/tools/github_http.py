from __future__ import annotations
from strands_tools import http_request

def github_tools():
    # Simple wrapper in case you want to swap this for a dedicated GitHub tool later
    return [http_request]
