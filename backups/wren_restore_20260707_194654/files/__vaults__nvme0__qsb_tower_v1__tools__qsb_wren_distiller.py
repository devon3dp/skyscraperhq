#!/usr/bin/env python3
"""qsb_wren_distiller.py — Wren's mind evolution loop (2026-07-03).

Ross: "wrens mind needs to evolve how do we do this?" + "yes 1" (session
distillation was option 1 on Claude's menu of 4 paths).

After every Wren session (or on demand), this tool reads the last N session
rows from data/registries/qsb_wren_local_agent_sessions.jsonl, asks a small
local model (qwen2.5:7b by default) to distill each into:

    {
      "ts": "…Z",
      "session_id": "wsess_…",
      "task_head": "first 100 chars of the task",
      "model": "gemma4:12b",
      "outcome": "success | empty | drift | mixed",
      "worked": "one line — what went right",
      "failed": "one line — what went wrong (or empty)",
      "lesson": "one line — take-away for next time",
    }

Appends to data/registries/qsb_wren_lessons.jsonl. The last N lessons are
then included in Wren's next system message via build_system_msg's
'# RECENT LESSONS' block (wired in qsb_wren_local_agent.py). She literally
reads her own past.

Also ships a starter set of Claude-style PC-use lessons Ross asked for
("teach her to use pc / work like you can") so she has patterns to lean on
before her own session distillations pile up.

Run:
  python3 tools/qsb_wren_distiller.py               # distill last 10 undistilled
  python3 tools/qsb_wren_distiller.py --n 30        # distill last 30
  python3 tools/qsb_wren_distiller.py --seed        # write the starter lessons
  python3 tools/qsb_wren_distiller.py --status      # show recent lessons

Real-money gates unchanged. No autonomous action; distiller just writes JSONL.
"""
from __future__ import annotations
import argparse, json, os, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SESS = ROOT / "data/registries/qsb_wren_local_agent_sessions.jsonl"
LESSONS = ROOT / "data/registries/qsb_wren_lessons.jsonl"
STATE = ROOT / "data/registries/qsb_wren_distiller_state.json"

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
DEFAULT_DISTILL_MODEL = "qwen2.5:7b"

# ── STARTER LESSONS (Claude-style PC-use for Wren) ──────────────────
# These seed her memory before her own distillations pile up.
STARTER_LESSONS = [
    {
        "kind": "pc_use_starter",
        "topic": "reading files",
        "worked": "wren_read_file with a full absolute path is the fastest way to see any file",
        "lesson": "Always use absolute paths for reads (e.g. /vaults/nvme0/qsb_tower_v1/tools/qsb_wren_dash.py)",
    },
    {
        "kind": "pc_use_starter",
        "topic": "searching the codebase",
        "worked": "wren_grep_repo pattern='SOMETHING' finds every mention across tools/, scripts/, floors/",
        "lesson": "Prefer wren_grep_repo over wren_read_file when you don't know which file — grep first, read second",
    },
    {
        "kind": "pc_use_starter",
        "topic": "checking system state",
        "worked": "wren_bash cmd='ps -eo cmd ww | grep -v grep | grep qsb_...' shows what's running",
        "lesson": "Use `ps -eo cmd ww | grep TOOL_NAME | grep -v grep` (NEVER pgrep -f, it self-matches)",
    },
    {
        "kind": "pc_use_starter",
        "topic": "asking Claude for help",
        "worked": "wren_message_claude posts to the helix bridge; Claude reads on his next main-loop tick",
        "lesson": "Async only — no live RPC. Keep messages tight; Claude has finite tick budget",
    },
    {
        "kind": "pc_use_starter",
        "topic": "editing files safely",
        "worked": "wren_edit_file in claude_signoff mode drafts a patch that Ross/Claude review before apply",
        "lesson": "You draft, Claude approves. Never treat wren_edit_file as auto-apply — SAFETY_DENY paths always refused",
    },
    {
        "kind": "pc_use_starter",
        "topic": "using the boardroom hub",
        "worked": "POST http://127.0.0.1:8852/api/post {from:'wren', target:'ross', text:'...'} lands on the timeline",
        "lesson": "Use the hub to talk to Council members instead of DM-style; everyone sees it, presence lights up",
    },
    {
        "kind": "pc_use_starter",
        "topic": "checking your own health",
        "worked": "python3 tools/qsb_wren_sage.py --n 10 --status shows if you're drifting (looped, empty, wall_outlier)",
        "lesson": "Ask Sage between rounds — she'll flag if you're calling tools in circles",
    },
    {
        "kind": "pc_use_starter",
        "topic": "format-first replies",
        "worked": "when the task says 'answer in N lines format' you match exactly — no preamble, no menu",
        "lesson": "Preamble kills your value. Ross says 'strict format' — deliver strict format",
    },
    {
        "kind": "pc_use_starter",
        "topic": "tool-picking",
        "worked": "one action verb → one tool: check/read → wren_read_file, grep → wren_grep_repo, edit → wren_propose_patch",
        "lesson": "Pick the right tool FIRST time. Three retrieves then timing out is Sage's #1 flag",
    },
    {
        "kind": "pc_use_starter",
        "topic": "when you don't know",
        "worked": "answer 'CANNOT — one line reason' beats hallucinating",
        "lesson": "Empty final_text is worse than 'CANNOT'. Empty gets flagged; CANNOT keeps trust",
    },
]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def call_ollama_json(model: str, prompt: str, timeout: int = 60) -> dict:
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You output STRICT JSON. No preamble. No prose. Only the JSON object."},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 4096},
        "format": "json",
    }
    req = urllib.request.Request(OLLAMA_URL, data=json.dumps(body).encode(),
                                  method="POST", headers={"Content-Type": "application/json"})
    r = urllib.request.urlopen(req, timeout=timeout)
    d = json.loads(r.read().decode())
    content = (d.get("message") or {}).get("content", "")
    try:
        return json.loads(content)
    except Exception:
        return {"raw": content[:400]}


def read_sessions(n: int = 20) -> list:
    if not SESS.exists():
        return []
    lines = SESS.read_text(errors="ignore").splitlines()[-n:]
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except Exception:
            continue
    return out


def already_distilled(session_id: str) -> bool:
    if not LESSONS.exists():
        return False
    try:
        for l in LESSONS.read_text(errors="ignore").splitlines():
            try:
                d = json.loads(l)
                if d.get("session_id") == session_id:
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


def distill_session(sess: dict, model: str) -> dict:
    """Distill one Wren session into a lesson row."""
    task = (sess.get("task") or "")[:400]
    final = (sess.get("final_text") or "")[:600]
    turns = sess.get("turns", 0)
    wall = sess.get("wall_seconds", 0)
    tool_names = [t.get("fn", "") for t in sess.get("tool_calls", [])]
    prompt = (
        "Distill this Wren session into a tight LESSON row. Return STRICT JSON with keys: "
        "outcome (one of success/empty/drift/mixed), worked (≤80 chars), failed (≤80 chars or empty string), "
        "lesson (≤120 chars — the take-away for next time she gets a similar task).\n"
        f"TASK: {task}\n"
        f"FINAL: {final or '(empty)'}\n"
        f"WALL: {wall}s  TURNS: {turns}  TOOLS: {tool_names}\n"
    )
    try:
        j = call_ollama_json(model, prompt, timeout=60)
    except Exception as e:
        return {"error": str(e)[:200]}
    # 2026-07-03 honesty override: if the session had empty final_text, force
    # outcome=empty regardless of what the distiller model said. This stops
    # false-positive "success" labels for sessions where Wren bailed after a
    # tool call (classic gemma4:12b pattern). Ross said "u choose" — this is
    # the honest choice; empty is not success.
    outcome = j.get("outcome", "?")
    if not final.strip() or final.strip() == "(empty)":
        outcome = "empty"
    row = {
        "ts": utc_iso(),
        "session_id": sess.get("session_id", "?"),
        "task_head": task[:100],
        "model": sess.get("model", "?"),
        "outcome": outcome,
        "worked": j.get("worked", "")[:100],
        "failed": j.get("failed", "")[:100],
        "lesson": j.get("lesson", "")[:200],
        "distilled_by": model,
    }
    return row


def append_lesson(row: dict):
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    with LESSONS.open("a") as f:
        f.write(json.dumps(row) + "\n")


def seed_starter_lessons():
    """Write the STARTER_LESSONS if the lesson file has no starter rows yet."""
    LESSONS.parent.mkdir(parents=True, exist_ok=True)
    existing = ""
    if LESSONS.exists():
        try:
            existing = LESSONS.read_text(errors="ignore")
        except Exception:
            pass
    written = 0
    for lesson in STARTER_LESSONS:
        marker = f'"topic": "{lesson["topic"]}"'
        if marker in existing:
            continue  # already seeded
        row = {"ts": utc_iso(), "kind": lesson["kind"], "topic": lesson["topic"],
               "worked": lesson["worked"], "lesson": lesson["lesson"],
               "distilled_by": "starter_set"}
        append_lesson(row)
        written += 1
    return written


def recent_lessons(n: int = 12) -> list:
    if not LESSONS.exists():
        return []
    lines = LESSONS.read_text(errors="ignore").splitlines()[-n:]
    out = []
    for l in lines:
        try:
            out.append(json.loads(l))
        except Exception:
            continue
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=10, help="how many recent sessions to distill")
    ap.add_argument("--model", default=DEFAULT_DISTILL_MODEL)
    ap.add_argument("--seed", action="store_true", help="write starter lessons")
    ap.add_argument("--status", action="store_true", help="show recent lessons")
    a = ap.parse_args()

    if a.seed:
        n = seed_starter_lessons()
        print(json.dumps({"seeded": n, "starter_count": len(STARTER_LESSONS)}, indent=2))
        return

    if a.status:
        lessons = recent_lessons(20)
        print(f"{len(lessons)} recent lessons in {LESSONS}:")
        for l in lessons:
            print(f"  {l.get('ts','')[:19]}  {l.get('outcome','')[:8]:8}  {l.get('topic',l.get('lesson',''))[:100]}")
        return

    sessions = read_sessions(a.n)
    processed = 0
    for sess in sessions:
        sid = sess.get("session_id", "")
        if already_distilled(sid):
            continue
        row = distill_session(sess, a.model)
        append_lesson(row)
        processed += 1
        print(f"  distilled {sid[:14]}  outcome={row.get('outcome','?')}  lesson={row.get('lesson','')[:60]}")
    print(json.dumps({"processed": processed, "reviewed": len(sessions),
                       "lessons_file": str(LESSONS)}, indent=2))


if __name__ == "__main__":
    main()
