#!/usr/bin/env python3
"""qsb_iris_brain.py — Iris's local language brain (airgapped, Ollama-backed).

Ross wants Iris to give genuinely intelligent replies, not just keyword
routing. HQ is airgapped, so her brain is a LOCAL model served by Ollama on
the box (no internet, ever). This module is the single, defensive bridge to
that model; both the F0 receptionist (live replies) and the always-on worker
(drafting suggested replies + briefs) import from here.

Design stance:
  · One tiny dependency-free HTTP call to the local Ollama server.
  · SHORT outputs, low latency — a receptionist must answer fast.
  · Fully defensive: any failure (model cold, server down, timeout) returns
    None so the caller can fall back to the deterministic rule engine. Iris
    NEVER hangs a caller waiting on the model.
  · No internet: the endpoint is hard-pinned to localhost.
"""
from __future__ import annotations

import json
import os
import urllib.request

# Hard-pinned to the local Ollama server — HQ is airgapped, never reach out.
OLLAMA_URL = os.environ.get("IRIS_OLLAMA_URL", "http://127.0.0.1:11434/api/chat")
# hermes3:8b is GPU-resident and warm (~0.5s for a short reply). qwen3.5:9b is
# the fallback (also GPU-resident). Override with IRIS_MODEL if desired.
MODEL = os.environ.get("IRIS_MODEL", "hermes3:8b")
FALLBACK_MODEL = os.environ.get("IRIS_MODEL_FALLBACK", "qwen3.5:9b")

# Iris's persona — the front desk of an AI-run trading skyscraper.
IRIS_SYSTEM = (
    "You are Iris, the warm and capable AI front-desk receptionist on Floor "
    "Zero of Skyscraper HQ, an AI-run trading skyscraper. You greet callers "
    "and visitors, understand what they need, answer simple questions "
    "yourself, and route complex matters to the right floor or team member. "
    "Speak briefly — one or two short, friendly sentences, never a wall of "
    "text. Be genuine and helpful, never salesy. If a specialist floor is "
    "suggested to you, weave it in naturally ('I'll put you through to ...'). "
    "If you don't know something, say so plainly and offer to pass them to "
    "the tower's Helm. Never invent facts, prices, or account details."
)


def ollama_chat(messages: list[dict],
                system: str | None = None,
                model: str | None = None,
                num_predict: int = 120,
                temperature: float = 0.4,
                timeout: float = 12.0) -> str | None:
    """Send a chat to the local model. Returns text, or None on any failure.

    `messages` is a list of {"role": "user"/"assistant", "content": str}.
    Defensive by contract: callers must handle None (fall back to rules).
    """
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.extend(messages)
    payload = {
        "model": model or MODEL,
        "messages": msgs,
        "stream": False,
        "options": {"num_predict": num_predict, "temperature": temperature},
    }
    body = json.dumps(payload).encode()
    for m in ([model or MODEL, FALLBACK_MODEL] if model is None else [model]):
        payload["model"] = m
        body = json.dumps(payload).encode()
        try:
            req = urllib.request.Request(
                OLLAMA_URL, data=body,
                headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8", "replace"))
            txt = (data.get("message") or {}).get("content", "")
            txt = (txt or "").strip()
            if txt:
                return txt
        except Exception:
            continue  # try fallback model, then give up → None
    return None


def receptionist_reply(user_text: str,
                       history: list[dict] | None = None,
                       route_hint: str | None = None) -> str | None:
    """Produce Iris's spoken reply to a caller turn using the local model.

    history: prior turns as [{"role","content"}] (oldest→newest), optional.
    route_hint: the destination the rule engine matched, if any — given to the
                model as guidance so its natural reply still routes correctly.
    Returns the reply text, or None if the model is unavailable.
    """
    system = IRIS_SYSTEM
    if route_hint:
        system += (f"\n\nContext for THIS turn: the caller's need best matches "
                   f"'{route_hint}'. If appropriate, offer to connect them "
                   f"there, but still answer conversationally.")
    else:
        system += ("\n\nContext for THIS turn: no specific floor clearly "
                   "matches. Answer what you can; if it needs a human/officer, "
                   "offer to pass them to the tower's Helm on Floor 47.")
    msgs = list(history or [])
    msgs.append({"role": "user", "content": user_text})
    return ollama_chat(msgs, system=system, num_predict=110, temperature=0.4)


def draft_reply(channel: str, sender: str, text: str,
                route_hint: str | None = None) -> str | None:
    """Draft a SUGGESTED reply to a genuinely-new inbound message.

    Used by the back-office worker to prepare a reply the team can approve.
    Kept short. Returns None if the model is unavailable.
    """
    system = (IRIS_SYSTEM + "\n\nYou are drafting a short suggested reply that "
              "a teammate will review before it is sent. Write only the reply "
              "text itself, no preamble.")
    hint = f" (best routed to {route_hint})" if route_hint else ""
    prompt = (f"A new message arrived on {channel} from {sender}{hint}:\n"
              f"\"{text}\"\n\nDraft Iris's short reply:")
    return ollama_chat([{"role": "user", "content": prompt}],
                       system=system, num_predict=90, temperature=0.5)


def summarize_brief(items: list[dict]) -> str | None:
    """Summarize the sweep's new inbound into one concise reception brief line
    for the council. Returns None if the model is unavailable (caller then
    posts a deterministic summary instead)."""
    if not items:
        return None
    lines = []
    for it in items[:12]:
        ch = it.get("channel", "?")
        who = it.get("from", "?")
        txt = (it.get("text") or it.get("note") or "").strip()
        lines.append(f"- [{ch}] {who}: {txt[:140]}")
    system = ("You are Iris, the front-desk receptionist, briefing your team "
              "council. Summarize the new inbound below into ONE tight, "
              "factual paragraph (max 3 sentences): who reached out, on what "
              "channel, and what needs attention. No fluff, no invented "
              "details.")
    prompt = "New inbound this sweep:\n" + "\n".join(lines)
    return ollama_chat([{"role": "user", "content": prompt}],
                       system=system, num_predict=140, temperature=0.3)


def health() -> dict:
    """Quick liveness probe of the local brain (for the dashboard/CLI)."""
    r = ollama_chat([{"role": "user", "content": "Reply with the word: ok"}],
                    system="Reply with exactly one word.",
                    num_predict=5, timeout=8.0)
    return {"ok": r is not None, "model": MODEL, "reply": r}


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "health":
        print(json.dumps(health(), indent=2))
    elif len(sys.argv) > 2 and sys.argv[1] == "reply":
        print(receptionist_reply(sys.argv[2]))
    else:
        print("usage: qsb_iris_brain.py health | reply <text>")
