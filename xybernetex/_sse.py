"""
Minimal Server-Sent Events parsers — one sync (requests), one async (httpx).
No external SSE library required.
"""
from __future__ import annotations

import json
from typing import AsyncIterator, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    import httpx
    import requests


# ── Sync ──────────────────────────────────────────────────────────────────────

def iter_sse(response: "requests.Response") -> Iterator[dict]:
    """
    Yield parsed event dicts from a streaming ``requests.Response``.

    Silently skips keepalive comments (lines starting with ``:``) and
    lines that cannot be decoded as JSON.
    """
    buf: list[str] = []
    for raw in response.iter_lines(decode_unicode=True):
        if not isinstance(raw, str):
            raw = raw.decode("utf-8", errors="replace")
        if raw.startswith(":"):
            continue  # SSE keepalive comment
        if raw.startswith("data:"):
            buf.append(raw[5:].strip())
        elif raw == "" and buf:
            payload = "\n".join(buf)
            buf.clear()
            try:
                yield json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                pass


# ── Async ─────────────────────────────────────────────────────────────────────

async def aiter_sse(response: "httpx.Response") -> AsyncIterator[dict]:
    """
    Yield parsed event dicts from a streaming ``httpx.Response``.
    Must be used inside an ``async with client.stream(...)`` block.
    """
    buf: list[str] = []
    async for raw in response.aiter_lines():
        if raw.startswith(":"):
            continue
        if raw.startswith("data:"):
            buf.append(raw[5:].strip())
        elif raw == "" and buf:
            payload = "\n".join(buf)
            buf.clear()
            try:
                yield json.loads(payload)
            except (json.JSONDecodeError, ValueError):
                pass
