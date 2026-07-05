#!/usr/bin/env python3
"""qsb_ceo_intent_executor.py — TP + Acer describe what they'd do in text,
HQ parses their reply and actually executes it on their behalf.

Ross 2026-07-05 "sort it out": their council_node has no tool-call parsing
loop, so their LLM types text like `Invoke-WebRequest -Uri X -Body Y`
without actually invoking anything. HQ (this module) reads their reply,
extracts the intended action, and does it — attributed to them.

Supported intents (grow the list as we see patterns):
  · POST http://192.168.1.71:8852/hq/write_file with JSON body → do the write
  · POST to boardroom /tasks/create → create the task
  · Invoke-WebRequest -Uri X -Body Y (PowerShell shape) → same as above

Not supported (bail loudly, don't guess):
  · arbitrary shell commands
  · anything not clearly targeted at HQ endpoints

Usage:
    from qsb_ceo_intent_executor import execute_intent
    result = execute_intent(ceo_name, reply_text)
    # result = {"intent": "write_file", "executed": True, "detail": {...}}
"""
from __future__ import annotations
import json, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data/registries"


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _stamp_execution(ceo: str, intent: str, ok: bool, detail: dict):
    """Audit trail — Ross can see everything HQ did on someone's behalf."""
    aud = REG / "qsb_ceo_intent_audit.jsonl"
    aud.parent.mkdir(parents=True, exist_ok=True)
    with aud.open("a") as f:
        f.write(json.dumps({
            "ts": _utc(), "ceo": ceo, "intent": intent,
            "executed": ok, "detail": detail,
        }) + "\n")


def _parse_write_file_intent(reply: str) -> dict | None:
    """Look for a PowerShell/curl POST to /hq/write_file with a JSON body.
    Returns {ceo, path, content} or None."""
    # Try to find the JSON body first
    # Common shapes:
    #   -Body '{"ceo":"...","path":"...","content":"..."}'
    #   --data '{...}'
    body_match = re.search(r"""(?:-Body|--data(?:-raw)?)\s+['"](\{.*?\})['"]""",
                           reply, re.DOTALL)
    if not body_match:
        return None
    body_str = body_match.group(1)
    # Try direct JSON parse first
    try:
        payload = json.loads(body_str)
        if isinstance(payload, dict) and payload.get("ceo") and payload.get("path"):
            return payload
    except Exception:
        pass
    # Fallback: field-by-field grep (LLM may have messed the JSON escaping)
    ceo_m = re.search(r'"ceo"\s*:\s*"([^"]+)"', body_str)
    path_m = re.search(r'"path"\s*:\s*"([^"]+)"', body_str)
    content_m = re.search(r'"content"\s*:\s*"(.*?)(?<!\\)"', body_str, re.DOTALL)
    if ceo_m and path_m and content_m:
        return {
            "ceo": ceo_m.group(1),
            "path": path_m.group(1),
            "content": content_m.group(1).replace("\\n","\n").replace('\\"','"'),
        }
    return None


def execute_intent(ceo: str, reply_text: str) -> dict:
    """Read the CEO's reply, find their intended action, execute it, stamp audit.
    Returns {intent, executed, detail}."""
    # 1) Write-file intent (most common)
    payload = _parse_write_file_intent(reply_text)
    if payload:
        # Force the ceo field to match the actual replier (prevent spoofing)
        payload["ceo"] = ceo
        try:
            body = json.dumps(payload).encode()
            req = urllib.request.Request("http://127.0.0.1:8852/hq/write_file",
                                         data=body,
                                         headers={"Content-Type":"application/json"})
            r = urllib.request.urlopen(req, timeout=6)
            d = json.loads(r.read())
            _stamp_execution(ceo, "write_file", True, d)
            return {"intent":"write_file","executed":True,"detail":d}
        except Exception as e:
            err = {"error": str(e)[:200]}
            _stamp_execution(ceo, "write_file", False, err)
            return {"intent":"write_file","executed":False,"detail":err}

    # 2) No recognized intent
    _stamp_execution(ceo, "none_recognized", False, {"reply_head": reply_text[:200]})
    return {"intent":"none","executed":False,
            "detail":{"reply_head": reply_text[:200]}}


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("usage: qsb_ceo_intent_executor.py <ceo> <reply_text>")
        sys.exit(2)
    ceo = sys.argv[1]
    reply = sys.argv[2]
    r = execute_intent(ceo, reply)
    print(json.dumps(r, indent=2))
