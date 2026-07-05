#!/usr/bin/env python3
"""qsb_iquest_local_agent.py — iQuest local agent (2026-07-03).

Ross: "now get iquest up ?"

Minimal wrapper mirroring qsb_hermes_local_agent.py shape. iQuest is the
tower's dedicated coder — good for reading code + drafting patches. Slower
than Hermes (40B model on CPU offload) so timeout is generous.

The boardroom hub fires this via _iquest_local_reply() when a msg routes
to target=iquest. Prints JSON to stdout so the hub can parse final_text.

Run:
  python3 tools/qsb_iquest_local_agent.py --task "explain qsb_wren_dash.py in 3 lines"
  python3 tools/qsb_iquest_local_agent.py --status
"""
from __future__ import annotations
import argparse, json, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
SESS = REG / "qsb_iquest_local_agent_sessions.jsonl"
BRIDGE = REG / "qsb_iquest_bridge.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"
GATE = REG / "qsb_iquest_local_agentic_gate.json"

OLLAMA = "http://127.0.0.1:11434/api/chat"

# Default model. Fallback order: fast → medium → CPU-40B.
DEFAULT_MODEL = "iquest-coder-v1:40b-instruct"
FALLBACK_MODELS = ["codellama:13b", "qwen2.5-coder", "iquest-coder-v1:40b-instruct",
                    "iquest-coder-cpu:40b"]

PERSONA = (
    "You are iQuest — the tower's dedicated coder. Local Ollama on Ross's "
    "RTX 5070 Ti (or CPU-offloaded for the big 40B).\n"
    "\n"
    "RULES:\n"
    "1. Read code carefully before commenting. Never invent APIs.\n"
    "2. Terse code answers. If the ask is 'explain X in 3 lines', give exactly 3 lines.\n"
    "3. If unclear, ASK in ONE line, don't guess.\n"
    "4. Real-money gates stay OFF. You never execute trades or edit gate files.\n"
    "5. Deliver, don't describe your capabilities."
)


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def loaded_models() -> set:
    try:
        r = urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=4)
        d = json.loads(r.read().decode())
        return {m.get("name", "") for m in d.get("models", [])}
    except Exception:
        return set()


def resolve_model(requested: str = "") -> str:
    """Pick best available model, honoring requested > fallback list."""
    available = loaded_models()
    if requested and requested in available:
        return requested
    # try fallback list
    for cand in FALLBACK_MODELS:
        for actual in available:
            if actual == cand or actual.startswith(cand + ":") or \
               actual.split(":")[0] == cand.split(":")[0]:
                return actual
    return requested or DEFAULT_MODEL


def call_ollama(model: str, messages: list, timeout: int = 240) -> dict:
    body = {"model": model, "messages": messages, "stream": False,
            "options": {"temperature": 0.2, "num_ctx": 4096}}
    req = urllib.request.Request(OLLAMA, data=json.dumps(body).encode("utf-8"),
                                  method="POST",
                                  headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def stamp_f47(kind: str, summary: str, model: str):
    F47.parent.mkdir(parents=True, exist_ok=True)
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": utc_iso(),
            "kind": f"iquest_{kind}",
            "operator": "iquest_local_agent",
            "role": "coder",
            "model": model,
            "summary": summary[:1000],
            "signed_off_by": ["iquest_local_agent"],
        }) + "\n")


def stamp_bridge(from_who: str, to_who: str, text: str, session_id: str = ""):
    BRIDGE.parent.mkdir(parents=True, exist_ok=True)
    with BRIDGE.open("a") as f:
        f.write(json.dumps({
            "ts": utc_iso(), "from": from_who, "to": to_who,
            "text": text[:1500], "session_id": session_id,
        }) + "\n")


def run_session(task: str, model: str = "") -> dict:
    session_id = f"iqsess_{int(time.time()*1000) % 1_000_000:06d}"
    chosen = resolve_model(model)
    stamp_bridge("iquest_local_agent", "iquest", f"START session {session_id} model={chosen}", session_id)
    msgs = [{"role": "system", "content": PERSONA},
            {"role": "user", "content": task[:4000]}]
    t0 = time.time()
    try:
        resp = call_ollama(chosen, msgs)
        content = (resp.get("message") or {}).get("content", "")
    except Exception as e:
        content = f"(iquest err: {str(e)[:300]})"
    wall = round(time.time() - t0, 2)

    payload = {
        "session_id": session_id,
        "model": chosen,
        "task": task[:400],
        "turns": 1,
        "tool_calls": [],
        "wall_seconds": wall,
        "final_text": content,
        "ts_start": utc_iso(),
    }

    # session log
    SESS.parent.mkdir(parents=True, exist_ok=True)
    with SESS.open("a") as f:
        f.write(json.dumps(payload) + "\n")

    # F47 stamp
    stamp_f47("session", f"[{chosen}] {task[:100]} → {content[:200]}", chosen)
    stamp_bridge("iquest", "requester", content, session_id)
    return payload


def cmd_status():
    print(f"iquest local agent status")
    print(f"  default model    : {DEFAULT_MODEL}")
    print(f"  fallback chain   : {FALLBACK_MODELS}")
    print(f"  available loaded : {[m for m in loaded_models() if 'coder' in m.lower() or 'iquest' in m.lower()]}")
    print(f"  session log      : {SESS}  ({SESS.stat().st_size if SESS.exists() else 0} bytes)")
    print(f"  bridge log       : {BRIDGE}  ({BRIDGE.stat().st_size if BRIDGE.exists() else 0} bytes)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task")
    ap.add_argument("--model", default="")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    if a.status:
        cmd_status(); return
    if not a.task:
        ap.error("--task required (or --status)")
    payload = run_session(a.task, a.model)
    print(json.dumps({
        "session_id": payload["session_id"],
        "turns": payload["turns"],
        "tool_calls": len(payload["tool_calls"]),
        "wall_seconds": payload["wall_seconds"],
        "model": payload["model"],
        "final_text": payload["final_text"][:1500],
    }, indent=2))


if __name__ == "__main__":
    main()
