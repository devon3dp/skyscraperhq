#!/usr/bin/env python3
"""qsb_chat_mirror.py — mirror Claude Code session transcripts into the tower.

Ross 2026-06-13: "please write code so you remember every line of our chats"

Claude Code persists every turn to ~/.claude/projects/<project>/<session_id>.jsonl.
That's not tower-owned and not surfaced anywhere on F47. This tool walks every
session transcript for this project and appends user + assistant turns into
data/registries/qsb_chat_log.jsonl as flat rows: {ts, session_id, role, text}.

State is kept at data/registries/qsb_chat_mirror_state.json so re-runs only
append new turns (high-water-mark per session).

Wire into the heartbeat tick so it runs every 5 min — that way every chat
line is in the tower's own registry within minutes of being said, surviving
PC restarts, context compactions, and Claude Code wipes.
"""
from __future__ import annotations
import json, os, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
TRANSCRIPT_DIR = Path("/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1")
OUT = ROOT / "data/registries/qsb_chat_log.jsonl"
STATE = ROOT / "data/registries/qsb_chat_mirror_state.json"
F47_REC = ROOT / "data/registries/qsb_f47_team_records.jsonl"


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        out = []
        for c in content:
            if isinstance(c, dict):
                t = c.get("type")
                if t == "text":
                    out.append(c.get("text", ""))
                elif t == "tool_use":
                    out.append(f"[tool_use:{c.get('name','?')}]")
                elif t == "tool_result":
                    r = c.get("content", "")
                    if isinstance(r, list):
                        r = " ".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in r)
                    out.append(f"[tool_result:{str(r)[:200]}]")
        return "\n".join(s for s in out if s).strip()
    return ""


def mirror() -> dict:
    state = {}
    if STATE.exists():
        try:
            state = json.loads(STATE.read_text())
        except Exception:
            state = {}

    OUT.parent.mkdir(parents=True, exist_ok=True)
    new_rows = 0
    sessions_seen = 0
    transcripts = sorted(TRANSCRIPT_DIR.glob("*.jsonl")) if TRANSCRIPT_DIR.exists() else []

    with OUT.open("a") as out_fh:
        for tpath in transcripts:
            sessions_seen += 1
            sid = tpath.stem
            offset = state.get(sid, 0)
            try:
                size = tpath.stat().st_size
            except Exception:
                continue
            if size <= offset:
                continue

            with tpath.open("rb") as f:
                f.seek(offset)
                buf = f.read()
            text = buf.decode("utf-8", errors="replace")
            for ln in text.splitlines():
                ln = ln.strip()
                if not ln:
                    continue
                try:
                    rec = json.loads(ln)
                except Exception:
                    continue
                rtype = rec.get("type")
                if rtype not in ("user", "assistant"):
                    continue
                m = rec.get("message", {})
                if not isinstance(m, dict):
                    continue
                txt = extract_text(m.get("content"))
                if not txt:
                    continue
                ts = rec.get("timestamp") or utcnow()
                row = {
                    "ts": ts,
                    "session_id": sid,
                    "role": rtype,
                    "text": txt,
                    "uuid": rec.get("uuid"),
                }
                out_fh.write(json.dumps(row, ensure_ascii=False) + "\n")
                new_rows += 1

            state[sid] = size

    STATE.write_text(json.dumps(state, indent=2))

    summary = {
        "ts": utcnow(),
        "sessions_scanned": sessions_seen,
        "rows_appended": new_rows,
        "log_path": str(OUT.relative_to(ROOT)),
        "state_path": str(STATE.relative_to(ROOT)),
    }

    with F47_REC.open("a") as f:
        f.write(json.dumps({
            "ts": utcnow(),
            "kind": "chat_mirror_tick",
            "floor": "F47",
            "operator": "background",
            "executed_by": "qsb_chat_mirror",
            **summary,
        }) + "\n")
    return summary


def tail(n: int = 20):
    if not OUT.exists():
        return []
    lines = OUT.read_text().splitlines()[-n:]
    return [json.loads(ln) for ln in lines if ln.strip()]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "mirror"
    if cmd == "mirror":
        s = mirror()
        print(json.dumps(s, indent=2))
    elif cmd == "tail":
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 20
        for r in tail(n):
            role = r.get("role", "?")
            txt = (r.get("text") or "").replace("\n", " ")[:120]
            print(f"[{r.get('ts','')[:19]}] {role:>9s}  {txt}")
    else:
        print(f"unknown command: {cmd}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
