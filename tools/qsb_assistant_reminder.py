#!/usr/bin/env python3
"""qsb_assistant_reminder.py — Wren/Claude's assistants ping the operator when work-pattern drifts.

Checks every N seconds (or one-shot):
  · last F47 stamp age — should not exceed 30 min during active session
  · last memory write age — long sessions without a save are suspicious
  · last diary line age — same
  · last backup age — should be < 4h while we have unsaved work

When any threshold breached, push ONE Telegram message via Iris and stamp F47.
Anti-spam: never push the same reminder kind twice within 1h.

Usage:
  python3 tools/qsb_assistant_reminder.py --check          # one-shot, exits
  python3 tools/qsb_assistant_reminder.py --watch --period 600   # 10-min loop
"""
from __future__ import annotations
import argparse, json, os, pathlib, sys, time, urllib.request
from datetime import datetime, timezone

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
VAULT = ROOT / "floors/floor_28_security_department/vault/.env.telegram"
MEMORY_INDEX = pathlib.Path("/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1/memory/MEMORY.md")
DIARY = ROOT / "qsb_session_diary.md"
F47 = REG / "qsb_f47_team_records.jsonl"
BACKUPS_DIR = pathlib.Path("/vaults/ai/backups")
REMINDER_LOG = REG / "qsb_assistant_reminder_log.jsonl"

THRESHOLDS = {
    # kind: (max_age_seconds, message)
    "f47_stamp_stale":    (30*60,    "Heads up: no F47 stamp for 30+ minutes. Wren should stamp at job boundaries."),
    "memory_write_stale": (2*60*60,  "Heads up: no auto-memory write for 2+ hours. If you've learned anything non-obvious, save it before it rots."),
    "diary_line_stale":   (60*60,    "Heads up: no diary line for an hour. Append a one-line summary of where you are."),
    "backup_stale":       (4*60*60,  "Heads up: last backup is over 4h old. Generator could go anytime — checkpoint to /vaults/ai/backups."),
}
DEDUP_WINDOW = 60*60   # don't repeat same reminder kind within 1h


def now_utc() -> float: return time.time()
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00","Z")


def file_age(p: pathlib.Path) -> float | None:
    try: return now_utc() - p.stat().st_mtime
    except FileNotFoundError: return None


def last_jsonl_ts(p: pathlib.Path) -> float | None:
    if not p.exists(): return None
    try:
        with p.open() as f:
            *_, last = f
        row = json.loads(last)
        ts = row.get("ts","")
        if ts: return datetime.fromisoformat(ts.replace("Z","+00:00")).timestamp()
    except Exception: return None
    return p.stat().st_mtime


def latest_backup_age() -> float | None:
    if not BACKUPS_DIR.exists(): return None
    snaps = sorted(BACKUPS_DIR.glob("qsb_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not snaps: return None
    return now_utc() - snaps[0].stat().st_mtime


def recently_sent(kind: str) -> bool:
    if not REMINDER_LOG.exists(): return False
    cutoff = now_utc() - DEDUP_WINDOW
    try:
        with REMINDER_LOG.open() as f:
            for line in f:
                row = json.loads(line)
                if row.get("kind") == kind:
                    ts_s = datetime.fromisoformat(row["ts"].replace("Z","+00:00")).timestamp()
                    if ts_s > cutoff: return True
    except Exception: pass
    return False


def push_telegram(text: str) -> tuple[bool, str]:
    if not VAULT.exists(): return False, "no vault"
    token = ""
    chat_id = 0
    for line in VAULT.read_text().splitlines():
        if line.startswith("QSB_TELEGRAM_BOT_TOKEN="):
            token = line.split("=",1)[1].strip()
    if not token: return False, "no token in vault"
    # find chat_id from telegram audit
    audit = REG / "qsb_telegram_audit.jsonl"
    if audit.exists():
        try:
            for line in audit.read_text().splitlines():
                r = json.loads(line); cid = r.get("chat_id")
                if isinstance(cid, int):
                    chat_id = cid; break
        except Exception: pass
    if not chat_id: return False, "no chat_id in audit"
    body = json.dumps({"chat_id": chat_id, "text": "🔔 " + text}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage",
                                  data=body, method="POST")
    req.add_header("Content-Type","application/json")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            resp = json.loads(r.read())
            if resp.get("ok"): return True, f"msg {resp['result']['message_id']}"
            return False, str(resp)[:120]
    except Exception as e:
        return False, str(e)[:120]


def stamp_event(kind: str, text: str, push_result: tuple[bool, str]):
    row = {"ts": now_iso(), "kind": kind, "text": text,
           "pushed": push_result[0], "push_detail": push_result[1]}
    REMINDER_LOG.parent.mkdir(parents=True, exist_ok=True)
    with REMINDER_LOG.open("a") as f: f.write(json.dumps(row)+"\n")
    with F47.open("a") as f:
        f.write(json.dumps({"ts": row["ts"], "kind": "assistant_reminder",
                            "operator":"reminder_daemon",
                            "summary": f"{kind} → pushed={row['pushed']} ({row['push_detail']})"})+"\n")


def check_once(quiet: bool = False) -> int:
    """Returns count of reminders fired."""
    fired = 0
    checks = {
        "f47_stamp_stale":    last_jsonl_ts(F47),
        "memory_write_stale": file_age(MEMORY_INDEX) and (now_utc() - file_age(MEMORY_INDEX) if False else None) or file_mtime(MEMORY_INDEX),
        "diary_line_stale":   file_mtime(DIARY),
        "backup_stale":       None if latest_backup_age() is None else (now_utc() - latest_backup_age()),
    }
    # cleaner approach using file_mtime helper below
    checks = {
        "f47_stamp_stale":    last_jsonl_ts(F47),
        "memory_write_stale": file_mtime(MEMORY_INDEX),
        "diary_line_stale":   file_mtime(DIARY),
        "backup_stale":       latest_backup_mtime(),
    }
    for kind, last_ts in checks.items():
        max_age, msg = THRESHOLDS[kind]
        if last_ts is None:
            if not quiet: print(f"  {kind}: no data, skipping")
            continue
        age = now_utc() - last_ts
        if not quiet: print(f"  {kind}: age={int(age)}s  threshold={max_age}s  breach={'YES' if age>max_age else 'no'}")
        if age > max_age and not recently_sent(kind):
            res = push_telegram(msg)
            stamp_event(kind, msg, res)
            fired += 1
            if not quiet: print(f"    → PUSHED: {res}")
    return fired


def file_mtime(p: pathlib.Path) -> float | None:
    try: return p.stat().st_mtime
    except FileNotFoundError: return None


def latest_backup_mtime() -> float | None:
    if not BACKUPS_DIR.exists(): return None
    snaps = list(BACKUPS_DIR.glob("qsb_*"))
    if not snaps: return None
    return max(p.stat().st_mtime for p in snaps)


def cmd_watch(period: int):
    print(f"[reminder] watching every {period}s. ctrl-c to stop.")
    while True:
        try:
            fired = check_once(quiet=False)
            print(f"  cycle done, fired={fired}")
        except Exception as e:
            print(f"  cycle err: {e}")
        time.sleep(period)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="one-shot")
    ap.add_argument("--watch", action="store_true", help="loop")
    ap.add_argument("--period", type=int, default=600, help="watch period seconds")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    if a.watch: cmd_watch(a.period)
    elif a.check: sys.exit(0 if check_once(a.quiet) == 0 else 0)
    else: ap.print_help()

if __name__ == "__main__":
    main()
