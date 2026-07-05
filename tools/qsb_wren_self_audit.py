#!/usr/bin/env python3
"""qsb_wren_self_audit.py — score Wren's last N agent sessions so she
sees her own trajectory.

Reads data/registries/qsb_wren_local_agent_sessions.jsonl. For each
session computes:

  - tool_calls_count
  - had_final_text (bool)
  - final_text_chars
  - looped (bool — same tool name back-to-back >= 3 times)
  - artifact_leak (bool — [cli], [tool_use:X], [tool_result:X] in final_text)

Writes a compact daily score to qsb_wren_self_audit.jsonl. Wren can
list the latest row via read_recent_f47_records or read it via
wren_read_file.
"""

from __future__ import annotations
import datetime, json, re
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SESS = ROOT / "data/registries/qsb_wren_local_agent_sessions.jsonl"
OUT  = ROOT / "data/registries/qsb_wren_self_audit.jsonl"

ARTIFACT_RX = re.compile(r"\[[a-zA-Z_][a-zA-Z0-9_]*(?::[^\]]*?)?\]")


def score_session(d: dict) -> dict:
    tool_calls = d.get("tool_calls", []) or []
    final = (d.get("final_text") or "").strip()
    fn_seq = [tc.get("fn", "") for tc in tool_calls]
    looped = False
    if len(fn_seq) >= 3:
        for i in range(len(fn_seq) - 2):
            if fn_seq[i] == fn_seq[i+1] == fn_seq[i+2]:
                looped = True; break
    artifact_leak = bool(ARTIFACT_RX.search(final))
    return {
        "session_id": d.get("session_id", "?"),
        "ts": d.get("ts_end") or d.get("ts_start") or "",
        "turns": d.get("turns", 0),
        "wall_seconds": d.get("wall_seconds", 0),
        "tool_calls_count": len(tool_calls),
        "had_final_text": bool(final),
        "final_text_chars": len(final),
        "looped_on_one_tool": looped,
        "artifact_leak": artifact_leak,
    }


def audit_last_n(n: int = 10) -> dict:
    if not SESS.exists():
        return {"ok": False, "error": "sessions file missing"}
    rows = []
    for line in SESS.read_text().splitlines()[-int(n):]:
        line = line.strip()
        if not line: continue
        try: d = json.loads(line)
        except Exception: continue
        rows.append(score_session(d))
    if not rows:
        return {"ok": False, "error": "no rows"}
    n = len(rows)
    summary = {
        "n_sessions": n,
        "pct_had_final_text": round(100 * sum(1 for r in rows if r["had_final_text"]) / n, 1),
        "pct_looped_on_one_tool": round(100 * sum(1 for r in rows if r["looped_on_one_tool"]) / n, 1),
        "pct_artifact_leak": round(100 * sum(1 for r in rows if r["artifact_leak"]) / n, 1),
        "avg_tool_calls": round(sum(r["tool_calls_count"] for r in rows) / n, 2),
        "avg_final_chars": round(sum(r["final_text_chars"] for r in rows) / n, 2),
        "rows": rows,
    }
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")
    payload = {"ts": ts, "audit": summary}
    with open(OUT, "a") as f:
        f.write(json.dumps(payload) + "\n")
    return {"ok": True, **summary, "stamped_ts": ts}


if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=10)
    a = p.parse_args()
    out = audit_last_n(a.n)
    print(json.dumps(out, indent=2))
