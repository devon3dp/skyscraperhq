#!/usr/bin/env python3
"""qsb_buffer_snapshot.py — capture volatile state every tick so a crash
doesn't lose 'where we were'.

Ross 2026-06-14: "100% persistence... if it falls, it can get back up."

What's volatile (in-memory or ephemeral) and needs snapshotting:
  · which daemons are alive
  · cloudflared tunnel URL (regenerates each restart)
  · ADB device id (Galaxy plugged in?)
  · last 20 F47 chat exchanges
  · last 20 CLI chat-mirror exchanges
  · unsigned proposals in the bench queue
  · last diary line + last F47 record (current narrative)
  · godot running flag
  · cockpit URL

Write atomically: write to .tmp, fsync, os.replace().
Archive last 12 snapshots so a corrupted current can roll back to LKG.

Read by:
  · tools/qsb_wake_briefing.py
  · the F47 chat panel (planned)
"""
from __future__ import annotations
import json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BUFFER = ROOT / "data/registries/qsb_buffer_state.json"
ARCHIVE_DIR = ROOT / "data/registries/qsb_buffer_state_archive"
F47_CHAT = ROOT / "data/registries/qsb_claude_f47_chat_history.jsonl"
CLI_LOG  = ROOT / "data/registries/qsb_chat_log.jsonl"
DIARY    = ROOT / "data/registries/qsb_session_diary.md"
F47_RECS = ROOT / "data/registries/qsb_f47_team_records.jsonl"
PROPOSALS = ROOT / "data/registries/qsb_code_proposals.jsonl"
CLOUDFLARED_LOG = Path("/tmp/skyscraper/cloudflared.log")

DAEMONS = [
    ("dashboard",   "src/dashboard/server.py"),
    ("lumen",       "qsb_lumen_serve.py"),
    ("vision",      "qsb_vision_floor.py"),
    ("heartbeat",   "qsb_tower_heartbeat.py"),
    ("cloudflared", "cloudflared"),
    ("qualify",     "qsb_qualify_everyone.py"),
    ("godot",       "godot-4"),
]


def utcnow():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _is_alive(pat: str) -> bool:
    try:
        r = subprocess.run(["pgrep","-f",pat], capture_output=True, text=True, timeout=4)
        return r.returncode == 0 and r.stdout.strip() != ""
    except Exception:
        return False


def _adb_device() -> str:
    try:
        r = subprocess.run(["adb","devices"], capture_output=True, text=True, timeout=4)
        for ln in (r.stdout or "").splitlines()[1:]:
            ln = ln.strip()
            if ln and "device" in ln:
                return ln.split()[0]
    except Exception:
        pass
    return ""


def _tunnel_url() -> str:
    if not CLOUDFLARED_LOG.exists():
        return ""
    try:
        import re
        txt = CLOUDFLARED_LOG.read_text()
        # last trycloudflare URL in the log
        urls = re.findall(r"https://[a-z0-9-]+\.trycloudflare\.com", txt)
        return urls[-1] if urls else ""
    except Exception:
        return ""


def _tail_jsonl(path: Path, n: int):
    if not path.exists():
        return []
    try:
        with path.open() as f:
            lines = f.readlines()[-n:]
        rows = []
        for ln in lines:
            ln = ln.strip()
            if not ln: continue
            try: rows.append(json.loads(ln))
            except: continue
        return rows
    except Exception:
        return []


def _unsigned_proposals():
    rows = _tail_jsonl(PROPOSALS, n=500)
    return [
        {"id": r.get("id"), "kind": r.get("kind"), "sigs": len(r.get("sigs",[]))}
        for r in rows if not r.get("applied")
    ]


def _diary_last():
    if not DIARY.exists():
        return ""
    try:
        for ln in reversed(DIARY.read_text().splitlines()):
            ln = ln.strip()
            if ln.startswith("- "):
                return ln
    except Exception:
        pass
    return ""


def _f47_last_decision():
    rows = _tail_jsonl(F47_RECS, n=50)
    skip = {"heartbeat_tick","auto_sigs_tick","applier_tick","chat_mirror_tick",
            "audit_crew_tick","mass_dispatch_run"}
    for r in reversed(rows):
        if r.get("kind") not in skip:
            return {"ts": r.get("ts"), "kind": r.get("kind"), "operator": r.get("operator")}
    return {}


def build_snapshot() -> dict:
    daemons = {name: _is_alive(pat) for name, pat in DAEMONS}
    f47_tail = _tail_jsonl(F47_CHAT, n=20)
    cli_tail = _tail_jsonl(CLI_LOG, n=20)
    return {
        "ts": utcnow(),
        "daemons": daemons,
        "adb_device": _adb_device(),
        "cloudflared_url": _tunnel_url(),
        "highlights": {
            "alive_count": sum(1 for v in daemons.values() if v),
            "down": [k for k,v in daemons.items() if not v],
            "f47_chat_tail_count": len(f47_tail),
            "cli_chat_tail_count": len(cli_tail),
            "unsigned_proposals": len(_unsigned_proposals()),
            "diary_last": _diary_last(),
            "last_decision": _f47_last_decision(),
        },
        "f47_chat_tail": [
            {"ts": r.get("ts",""), "you": (r.get("you") or "")[:200]}
            for r in f47_tail
        ],
        "cli_chat_tail": [
            {"ts": r.get("ts",""), "role": r.get("role",""), "text": (r.get("text") or "")[:200]}
            for r in cli_tail
        ],
    }


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w") as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())
    os.replace(str(tmp), str(path))


def rotate_archive(keep: int = 12) -> None:
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(ARCHIVE_DIR.glob("buffer_*.json"))
    while len(files) > keep:
        try:
            files[0].unlink()
        except Exception:
            pass
        files = files[1:]


def main():
    snap = build_snapshot()
    content = json.dumps(snap, indent=2)

    # Archive current first (if it exists), then overwrite current.
    if BUFFER.exists():
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        stamp = snap["ts"].replace(":","").replace("-","").replace("T","_")[:15]
        archive_path = ARCHIVE_DIR / f"buffer_{stamp}.json"
        try:
            archive_path.write_text(BUFFER.read_text())
        except Exception:
            pass
        rotate_archive(keep=12)

    write_atomic(BUFFER, content)
    # Compact summary to stdout
    print(json.dumps({
        "ok": True,
        "ts": snap["ts"],
        "alive_count": snap["highlights"]["alive_count"],
        "down": snap["highlights"]["down"],
        "tunnel": snap["cloudflared_url"],
        "adb": snap["adb_device"] or "(none)",
        "unsigned_proposals": snap["highlights"]["unsigned_proposals"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
