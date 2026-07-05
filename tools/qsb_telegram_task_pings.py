#!/usr/bin/env python3
"""qsb_telegram_task_pings.py — watches task board for completions and
sends Telegram pings to Ross.

Ross 2026-07-05 #121: "i need notification sent to telegram through the
receptionist to tell me each time a task is completed".

Cadence: poll /tasks/data every 30s. Track seen done task_ids across
restarts via a state file. On new completion, send:
    ✓ [owner] completed: title — verified by [peer] — took Xm
"""
from __future__ import annotations
import json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
STATE = ROOT / "data/runtime/qsb_telegram_seen_dones.json"
VAULT_ENV = ROOT / "floors/floor_28_security_department/vault/.env.telegram"
HUB = "http://127.0.0.1:8852"
CHAT_ID = "8683680296"   # Ross
POLL_S = 30
RATE_LIMIT_S = 3         # max 1 message per 3s so we don't flood

def _load_token() -> str | None:
    if not VAULT_ENV.exists(): return None
    for line in VAULT_ENV.read_text().splitlines():
        if line.startswith("QSB_TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    return None

def _load_seen() -> set:
    if not STATE.exists(): return set()
    try: return set(json.loads(STATE.read_text()))
    except Exception: return set()

def _save_seen(seen: set):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(sorted(seen)))

def _fetch_tasks() -> list:
    try:
        with urllib.request.urlopen(HUB + "/tasks/data", timeout=5) as r:
            return json.loads(r.read()).get("tasks", [])
    except Exception:
        return []

def _iso_epoch(iso: str) -> float:
    try: return datetime.fromisoformat(iso.replace("Z","+00:00")).timestamp()
    except Exception: return 0.0

def _fmt_dur(seconds: float) -> str:
    if seconds < 60: return f"{int(seconds)}s"
    if seconds < 3600: return f"{int(seconds//60)}m"
    return f"{int(seconds//3600)}h{int((seconds%3600)//60)}m"

def _send_telegram(token: str, text: str) -> bool:
    try:
        data = urllib.parse.urlencode({
            "chat_id": CHAT_ID, "text": text[:4000],
            "parse_mode": "HTML", "disable_web_page_preview": "true",
        }).encode()
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data=data,
            headers={"Content-Type":"application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read()).get("ok", False)
    except Exception as e:
        print(f"  [!] telegram send fail: {e}")
        return False

def format_message(t: dict) -> str:
    title = t.get("title","(untitled)")
    owner = t.get("completed_by") or t.get("owner") or "?"
    peer = t.get("peer_signoff_by") or "no signoff"
    # duration
    start = _iso_epoch(t.get("claimed_at") or t.get("started_at") or t.get("created_at",""))
    end = _iso_epoch(t.get("completed_at",""))
    dur = end - start if (start and end) else 0
    dur_lbl = _fmt_dur(dur) if dur > 0 else "?"
    # last note as evidence
    notes = t.get("notes", [])
    evidence = ""
    if notes:
        evidence = "\n<i>" + (notes[-1].get("text","")[:200]).replace("<","&lt;") + "</i>"
    return f"✓ <b>{owner}</b> completed:\n<b>{title[:180]}</b>\n· verified by {peer}\n· took {dur_lbl}{evidence}"

def main():
    token = _load_token()
    if not token:
        print("  no telegram token — abort")
        sys.exit(1)
    print(f"  telegram-task-pings started · poll {POLL_S}s · chat={CHAT_ID}")
    seen = _load_seen()
    # Prime: on first run, mark all currently-done as seen (don't spam Ross with history)
    if not seen:
        tasks = _fetch_tasks()
        seen.update(t["id"] for t in tasks if t.get("state") == "done")
        _save_seen(seen)
        print(f"  primed with {len(seen)} existing completions (silent)")
    while True:
        try:
            tasks = _fetch_tasks()
            done_now = [t for t in tasks if t.get("state") == "done"]
            new = [t for t in done_now if t["id"] not in seen]
            new.sort(key=lambda t: t.get("completed_at",""))
            sent = 0
            for t in new:
                msg = format_message(t)
                ok = _send_telegram(token, msg)
                if ok:
                    seen.add(t["id"])
                    sent += 1
                    print(f"  ✓ pinged: {t['id'][:12]} · {t.get('title','?')[:60]}")
                    time.sleep(RATE_LIMIT_S)
            if sent:
                _save_seen(seen)
        except Exception as e:
            print(f"  [!] loop error: {e}")
        time.sleep(POLL_S)

if __name__ == "__main__":
    main()
