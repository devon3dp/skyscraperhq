#!/usr/bin/env python3
"""qsb_wake_briefing.py — what Wren should know the moment she wakes.

Ross 2026-06-14: "We need to design the skyscraper to be 100% persistent.
If it falls, it can get back up. We need more fail-safe designs that stops
the system from breaking."

Pattern Ross caught: PC crashes → Wren forgets → next session re-pitches
dead ideas (Twilio after Termux was already chosen, US Toll-Free after we
proved UK can't reach it, etc).

This tool synthesises a 200-word wake briefing from:
  · last buffer snapshot           (data/registries/qsb_buffer_state.json)
  · last 3 F47 letters             (qsb_claude_meta_letters.jsonl)
  · last 8 diary lines             (qsb_session_diary.md)
  · forget-prevention catalogue    (qsb_abandoned_paths.jsonl)
  · last 5 F47 records             (qsb_f47_team_records.jsonl)
  · running daemons                (pgrep)

Outputs to stdout AND writes to data/registries/qsb_wake_briefing.md.
Read by Wren on every wake — terminal session start, F47 chat first turn.
"""
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BUFFER     = ROOT / "data/registries/qsb_buffer_state.json"
LETTERS    = ROOT / "data/registries/qsb_claude_meta_letters.jsonl"
DIARY      = ROOT / "data/registries/qsb_session_diary.md"
ABANDONED  = ROOT / "data/registries/qsb_abandoned_paths.jsonl"
F47_RECS   = ROOT / "data/registries/qsb_f47_team_records.jsonl"
OUT_MD     = ROOT / "data/registries/qsb_wake_briefing.md"
CLAUDE_SESSIONS_DIR = Path.home() / ".claude/projects/-vaults-nvme0-qsb-tower-v1"

DAEMONS_TO_CHECK = [
    ("dashboard",       "src/dashboard/server.py"),
    ("lumen",           "qsb_lumen_serve.py"),
    ("vision",          "qsb_vision_floor.py"),
    ("heartbeat",       "qsb_tower_heartbeat.py"),
    ("cloudflared",     "cloudflared"),
    ("qualify_loop",    "qsb_qualify_everyone.py"),
]


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _read_jsonl(path: Path, tail: int):
    if not path.exists():
        return []
    rows = []
    try:
        with path.open() as f:
            lines = f.readlines()[-tail:]
        for ln in lines:
            ln = ln.strip()
            if not ln: continue
            try: rows.append(json.loads(ln))
            except: continue
    except Exception:
        pass
    return rows


def _daemon_status():
    out = []
    for name, pat in DAEMONS_TO_CHECK:
        try:
            r = subprocess.run(["pgrep","-f",pat], capture_output=True, text=True, timeout=4)
            alive = r.returncode == 0 and r.stdout.strip() != ""
            out.append((name, alive))
        except Exception:
            out.append((name, False))
    return out


def _buffer_snapshot():
    if not BUFFER.exists():
        return None
    try:
        return json.loads(BUFFER.read_text())
    except Exception:
        return None


def _diary_tail(n: int = 8):
    if not DIARY.exists():
        return []
    try:
        lines = [l.rstrip() for l in DIARY.read_text().splitlines() if l.strip().startswith("- ")]
        return lines[-n:]
    except Exception:
        return []


def _f47_recs_tail(n: int = 5):
    rows = _read_jsonl(F47_RECS, tail=n * 4)  # filter below
    # Skip pure heartbeat_tick rows so the briefing isn't all heartbeats
    interesting = [r for r in rows if r.get("kind") not in ("heartbeat_tick","auto_sigs_tick","applier_tick","chat_mirror_tick")]
    return interesting[-n:]


def _letters_tail(n: int = 3):
    return _read_jsonl(LETTERS, tail=n)


def _abandoned_list():
    rows = _read_jsonl(ABANDONED, tail=200)
    return [r for r in rows if r.get("never_pitch_again")]


def _latest_claude_session_uuid():
    """Return the basename (minus .jsonl) of the newest claude-code session file."""
    try:
        if not CLAUDE_SESSIONS_DIR.exists():
            return None
        candidates = list(CLAUDE_SESSIONS_DIR.glob("*.jsonl"))
        if not candidates:
            return None
        newest = max(candidates, key=lambda p: p.stat().st_mtime)
        return newest.stem
    except Exception:
        return None


def render() -> str:
    parts = []
    parts.append(f"# WREN WAKE BRIEFING — {utcnow()}")
    parts.append("")

    # Resume hint — top of the briefing, per gap audit
    sess = _latest_claude_session_uuid()
    parts.append("## To resume your last conversation")
    parts.append("```")
    parts.append("cd /vaults/nvme0/qsb_tower_v1")
    if sess:
        parts.append(f"claude --resume {sess}")
    else:
        parts.append("claude --resume <session-uuid>   # no prior session found")
    parts.append("```")
    parts.append("")

    parts.append("_Read this every time you wake. It exists because Ross caught me re-pitching dead ideas across crashes._")
    parts.append("")

    # Daemons
    parts.append("## Tower vitals")
    for name, alive in _daemon_status():
        mark = "✓" if alive else "✗"
        parts.append(f"- {mark} {name}")
    parts.append("")

    # Buffer
    buf = _buffer_snapshot()
    if buf:
        parts.append("## Last snapshot")
        parts.append(f"- ts: `{buf.get('ts','?')}`")
        for k, v in (buf.get("highlights") or {}).items():
            parts.append(f"- {k}: {v}")
        parts.append("")
    else:
        parts.append("## Last snapshot")
        parts.append("- (no buffer snapshot yet — run `tools/qsb_buffer_snapshot.py`)")
        parts.append("")

    # Diary tail
    diary = _diary_tail()
    if diary:
        parts.append("## Diary tail")
        for ln in diary:
            parts.append(ln)
        parts.append("")

    # Recent F47 records (decisions, not heartbeats)
    recs = _f47_recs_tail()
    if recs:
        parts.append("## Recent decisions (not heartbeat noise)")
        for r in recs:
            parts.append(f"- `{r.get('ts','?')[:19]}` {r.get('kind','?')}")
        parts.append("")

    # Last letters
    letters = _letters_tail()
    if letters:
        parts.append("## Last letters (read in full before high-stakes action)")
        for l in letters:
            parts.append(f"- `{l.get('ts','?')[:19]}` gen={l.get('generation','?')} · {l.get('subject','(no subject)')}")
        parts.append("")

    # The do-not-pitch list — load-bearing
    abandoned = _abandoned_list()
    if abandoned:
        parts.append("## ❌ DEAD IDEAS — DO NOT PITCH THESE TO ROSS")
        parts.append("")
        parts.append("_If you find yourself proposing any of these, STOP. Ross has killed them. The reason is real._")
        parts.append("")
        for a in abandoned:
            parts.append(f"- **{a.get('idea','?')}** — {a.get('reason','?')[:200]}")
        parts.append("")

    parts.append("---")
    parts.append("_Generated by `tools/qsb_wake_briefing.py`. Re-run any time. Sources: qsb_buffer_state.json, qsb_session_diary.md, qsb_f47_team_records.jsonl, qsb_claude_meta_letters.jsonl, qsb_abandoned_paths.jsonl._")

    return "\n".join(parts) + "\n"


def main():
    md = render()
    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    OUT_MD.write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
