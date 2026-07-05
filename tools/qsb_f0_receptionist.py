#!/usr/bin/env python3
"""qsb_f0_receptionist.py — F0 Ground / Reception Lobby AI greeter.

Ross 2026-06-13: "I have a SIM card and a modem ... I can ring up the
skyscraper and talk to an AI. So it needs to say, like, welcome to skyscraper
HQ run by AI. How can I help you?"

This is v1 — conversational core, no telephony yet. Provides:
  · greet(): the welcome line for a new caller / visitor
  · converse(caller_id, text): routes the caller's question to the right
    downstream destination (Helm, Lumen, the trading desk, a specific floor)
    and returns the AI receptionist's reply
  · close_call(caller_id, summary): closes the session, stamps F47 record

Session memory keyed on caller_id so a caller can have a multi-turn
conversation. State at data/registries/qsb_f0_calls.jsonl.

Telephony comes later via a Twilio Media Stream webhook — that wrapper just
passes through to converse() with the caller's phone number as caller_id and
streams the reply audio back. Same conversational core works for browser
chat, Godot interior, and phone calls.
"""
from __future__ import annotations
import json, sys, argparse, os, urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CALLS = ROOT / "data/registries/qsb_f0_calls.jsonl"

# Iris's local language brain (Ollama on the airgapped box). Optional: if the
# model is unavailable the receptionist falls back to the deterministic rule
# engine below, so import failure must never break the front desk.
sys.path.insert(0, str(ROOT / "tools"))
try:
    from qsb_iris_brain import receptionist_reply as _brain_reply  # type: ignore
except Exception:  # pragma: no cover - defensive
    def _brain_reply(user_text, history=None, route_hint=None):
        return None
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"

GREETING_DEFAULT = (
    "Welcome to Skyscraper HQ run by AI. "
    "My name's Iris, the front-desk receptionist on Floor Zero. "
    "How can I help you today?"
)

# Topic → downstream-destination routing. v1 is keyword-based; LLM-based
# topic-trigger expansion can come later via the bounded consult tool.
ROUTES = [
    (["trade", "trading", "oanda", "binance", "stock", "stocks", "forex"],
        "F41 OANDA Practice Trading Floor",
        "/api/floor/41"),
    (["wren", "f47", "helm", "auger", "embassy"],
        "F47 Claude Embassy (Wren)",
        "/api/officers/Helm/talk"),
    (["seed", "cannabis", "greenline", "horticulture"],
        "F149 Greenline Seed Centre",
        "/api/floor/149"),
    (["music", "tower sound", "f58"],
        "F58 Tower Sound music studio",
        "/api/floor/58"),
    (["lumen", "ai chat", "chat bot"],
        "F48 Lumen AI chat",
        "http://127.0.0.1:8848/"),
    (["bank", "ledger", "account", "f44", "accounts"],
        "F44 Accounts",
        "/api/floor/44"),
    (["worker", "employee", "stamp in", "stamp out", "timeclock"],
        "F47 worker time clock",
        "/api/timeclock/status"),
    (["shop", "store", "buy", "catalog", "catalogue"],
        "F59 Shopping Centre",
        "/api/floor/59"),
]

FALLBACK_REPLY = (
    "I'm not sure who handles that yet — let me pass you up to Helm, "
    "who runs the tower bearing. One moment."
)


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def append_call(rec: dict) -> None:
    CALLS.parent.mkdir(parents=True, exist_ok=True)
    with CALLS.open("a") as f:
        f.write(json.dumps(rec) + "\n")


def session_history(caller_id: str, last: int = 6) -> list[dict]:
    if not CALLS.exists():
        return []
    out = []
    for ln in CALLS.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("caller_id") == caller_id:
            out.append(r)
    return out[-last:]


def route_for(text: str) -> tuple[str | None, str | None]:
    t = (text or "").lower()
    for keywords, destination, endpoint in ROUTES:
        if any(k in t for k in keywords):
            return destination, endpoint
    return None, None


def greet(caller_id: str | None = None) -> dict:
    history = session_history(caller_id, last=1) if caller_id else []
    line = GREETING_DEFAULT
    if history:
        # Returning caller — warmer line
        line = (f"Welcome back. This is Iris on Floor Zero. "
                f"How can I help you today?")
    rec = {"ts": utcnow(), "caller_id": caller_id, "turn": "iris_greet",
            "text": line}
    append_call(rec)
    return {"ok": True, "from": "Iris (F0 receptionist)", "text": line}


def _history_for_model(caller_id: str, last: int = 6) -> list[dict]:
    """Turn recent call log rows into {role,content} pairs for the model."""
    out: list[dict] = []
    for r in session_history(caller_id, last=last):
        turn, text = r.get("turn"), (r.get("text") or "").strip()
        if not text:
            continue
        if turn == "caller":
            out.append({"role": "user", "content": text})
        elif turn in ("iris_reply", "iris_greet"):
            out.append({"role": "assistant", "content": text})
    return out


def converse(caller_id: str, user_text: str) -> dict:
    # Build prior-turn context BEFORE logging this new user turn.
    history = _history_for_model(caller_id, last=6)

    # log the user turn
    append_call({"ts": utcnow(), "caller_id": caller_id, "turn": "caller",
                  "text": user_text})

    # Deterministic routing decision is ALWAYS computed — it is the source of
    # truth for where the call goes, and the fallback if the model is down.
    destination, endpoint = route_for(user_text)
    if destination:
        meta = {"routed_to": destination, "endpoint": endpoint}
    else:
        meta = {"routed_to": "F47 Helm (fallback)",
                "endpoint": "/api/officers/Helm/talk"}

    # Smarter reply: let Iris's local brain phrase the response, guided by the
    # route hint so her natural language still lands the caller in the right
    # place. If the model is unavailable, fall back to the rule-based lines.
    reply = _brain_reply(user_text, history=history, route_hint=destination)
    if reply:
        meta["reply_source"] = "iris_brain"
    else:
        reply = (f"That sounds like one for {destination}. I'm putting you "
                 f"through — can you hold for a moment?") if destination \
            else FALLBACK_REPLY
        meta["reply_source"] = "rule_fallback"

    rec = {"ts": utcnow(), "caller_id": caller_id, "turn": "iris_reply",
            "text": reply, **meta}
    append_call(rec)
    return {"ok": True, "from": "Iris (F0 receptionist)", "text": reply,
             **meta}


def close_call(caller_id: str, summary: str = "") -> dict:
    history = session_history(caller_id, last=20)
    rec = {"ts": utcnow(), "caller_id": caller_id, "turn": "iris_close",
            "summary": summary or "caller hung up",
            "turn_count": len(history)}
    append_call(rec)
    # stamp F47 record so the call is visible to Wren on next briefing
    f47 = {
        "ts": utcnow(),
        "kind": "f0_call_closed",
        "floor": "F47",
        "operator": "F0 Iris",
        "executed_by": "f0_receptionist",
        "caller_id": caller_id,
        "turns": len(history),
        "summary": summary[:200] if summary else "",
    }
    with F47_REC.open("a") as f:
        f.write(json.dumps(f47) + "\n")
    return {"ok": True, "closed": True, "turn_count": len(history)}


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_g = sub.add_parser("greet")
    p_g.add_argument("--caller", default=None)
    p_c = sub.add_parser("converse")
    p_c.add_argument("--caller", required=True)
    p_c.add_argument("--text", required=True)
    p_x = sub.add_parser("close")
    p_x.add_argument("--caller", required=True)
    p_x.add_argument("--summary", default="")
    args = ap.parse_args()
    if args.cmd == "greet":
        print(json.dumps(greet(args.caller), indent=2))
    elif args.cmd == "converse":
        print(json.dumps(converse(args.caller, args.text), indent=2))
    elif args.cmd == "close":
        print(json.dumps(close_call(args.caller, args.summary), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
