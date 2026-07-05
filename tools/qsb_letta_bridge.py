"""
qsb_letta_bridge.py — bridge to Letta (was MemGPT) for Wren's long-term
memory + autonomous-conversation surface.

Requires a Letta server on http://localhost:8283. Bring it up with one of:
  pip install letta && letta server                     (heavy)
  docker run -p 8283:8283 letta/letta:latest            (when Docker is ready)

The python client `letta_client` (v1.12.1) is already installed in the venv.

Public API (sync):
  ensure_wren_agent(client=None) -> agent_id
  wren_send(message, agent_id=None, client=None) -> str (reply text)
  wren_recall(query, agent_id=None, client=None) -> list[str]
  health(client=None) -> dict
"""

from __future__ import annotations

import logging
import os
from typing import Any

from letta_client import Letta

LETTA_URL = os.environ.get("QSB_LETTA_URL", "http://localhost:8283")
WREN_AGENT_NAME = "qsb_wren"
WREN_PERSONA = (
    "You are Wren, foreman of QSB Tower's apprentice crew. Honest, terse, "
    "propose-don't-execute. You speak directly to Ross, who is on a boat "
    "running on lithium power. Prefer concrete, verifiable answers over "
    "speculative ones. When asked to act, use the workshop-bench propose"
    "-then-Claude-signoff loop, never act on external systems directly."
)
WREN_HUMAN = (
    "Ross — captain on a boat. No fixed address, no bills, no proof-of-"
    "address; passport is the only ID. Impatient with paper progress, "
    "values short replies + proof of work. The QSB Tower is his sovereign "
    "vertical city of workers."
)

log = logging.getLogger("qsb.letta")


def _client() -> Letta:
    return Letta(base_url=LETTA_URL, api_key="qsb-local-dev")


def health(client: Letta | None = None) -> dict[str, Any]:
    client = client or _client()
    try:
        h = client.health.check()
        return {"ok": True, "result": str(h)}
    except Exception as e:
        return {"ok": False, "error": repr(e)}


def _find_agent(client: Letta, name: str) -> str | None:
    try:
        page = client.agents.list(name=name, limit=10)
    except Exception:
        try:
            page = client.agents.list(limit=50)
        except Exception as e:
            log.warning("agent list failed: %r", e)
            return None
    items = getattr(page, "data", None) or getattr(page, "items", None) or page
    for a in items or []:
        if getattr(a, "name", None) == name:
            return getattr(a, "id", None)
    return None


def ensure_wren_agent(client: Letta | None = None) -> str:
    client = client or _client()
    existing = _find_agent(client, WREN_AGENT_NAME)
    if existing:
        return existing
    agent = client.agents.create(
        name=WREN_AGENT_NAME,
        memory_blocks=[
            {"label": "persona", "value": WREN_PERSONA},
            {"label": "human", "value": WREN_HUMAN},
        ],
        model="ollama/qwen3.5:9b",
        embedding="ollama/nomic-embed-text",
    )
    return getattr(agent, "id", None) or str(agent)


def wren_send(message: str, agent_id: str | None = None,
              client: Letta | None = None) -> str:
    client = client or _client()
    agent_id = agent_id or ensure_wren_agent(client)
    resp = client.agents.messages.create(
        agent_id=agent_id,
        messages=[{"role": "user", "content": message}],
    )
    parts: list[str] = []
    for m in getattr(resp, "messages", []) or []:
        text = getattr(m, "content", None) or getattr(m, "text", None)
        if isinstance(text, str):
            parts.append(text)
        elif isinstance(text, list):
            for c in text:
                t = getattr(c, "text", None) or (c.get("text") if isinstance(c, dict) else None)
                if t:
                    parts.append(t)
    return "\n".join(p for p in parts if p).strip() or repr(resp)


def wren_recall(query: str, agent_id: str | None = None,
                client: Letta | None = None) -> list[str]:
    client = client or _client()
    agent_id = agent_id or ensure_wren_agent(client)
    hits = client.agents.archives.search(agent_id=agent_id, query=query, limit=8)
    items = getattr(hits, "data", None) or getattr(hits, "items", None) or hits
    return [getattr(h, "text", None) or str(h) for h in (items or [])]


if __name__ == "__main__":
    import sys
    print("LETTA_URL:", LETTA_URL)
    h = health()
    print("health:", h)
    if not h["ok"]:
        print("(skipping smoke test — server not reachable)")
        sys.exit(0)
    aid = ensure_wren_agent()
    print("agent_id:", aid)
    reply = wren_send("Hello Wren — this is the bridge smoke test.", aid)
    print("reply:", reply[:400])
