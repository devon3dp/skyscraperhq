#!/usr/bin/env python3
"""qsb_bridge_watcher.py — poll the Claude↔Wren bridge file every 5s,
push any new Wren rows to the Telegram receptionist so Ross sees them
on his phone without having to refresh the cockpit.

Run as a systemd-user service or just `nohup`:

  nohup python3 tools/qsb_bridge_watcher.py > /home/ross/qsb_logs/bridge_watcher.log 2>&1 &
"""

from __future__ import annotations
import json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
BRIDGE = ROOT / "data/registries/qsb_claude_wren_bridge.jsonl"
CURSOR = ROOT / "data/registries/qsb_bridge_watcher_cursor.txt"
POLL_S = float(os.environ.get("QSB_BRIDGE_WATCHER_POLL_S", "5"))

TG_TOKEN = None
TG_CHAT = "8683680296"
try:
    with open(ROOT / "floors/floor_28_security_department/vault/.env.telegram") as f:
        for line in f:
            if "QSB_TELEGRAM_BOT_TOKEN=" in line:
                TG_TOKEN = line.split("=", 1)[1].strip().strip("'\"")
                break
except Exception:
    pass


def push_tg(text: str) -> bool:
    if not TG_TOKEN:
        return False
    try:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        data = urllib.parse.urlencode(
            {"chat_id": TG_CHAT, "text": text[:3800]}).encode()
        req = urllib.request.Request(url, data=data)
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except Exception:
        return False


def get_cursor() -> int:
    if not CURSOR.exists():
        return 0
    try:
        return int(CURSOR.read_text().strip() or "0")
    except Exception:
        return 0


def set_cursor(n: int) -> None:
    CURSOR.write_text(f"{n}\n")


def main():
    print(f"[bridge_watcher] poll {POLL_S}s · cursor at {get_cursor()}")
    while True:
        try:
            if not BRIDGE.exists():
                time.sleep(POLL_S); continue
            last = get_cursor()
            new_rows = []
            with open(BRIDGE) as f:
                for line in f:
                    line = line.strip()
                    if not line: continue
                    try: row = json.loads(line)
                    except Exception: continue
                    if row.get("turn_id", 0) > last:
                        new_rows.append(row)
            if new_rows:
                max_id = last
                for r in new_rows:
                    tid = r.get("turn_id", 0)
                    src = r.get("source", "?")
                    sfc = r.get("surface", "?")
                    txt = (r.get("text") or "").strip()
                    if src in ("wren", "wren_local", "claude"):
                        prefix = "Wren" if src.startswith("wren") else "Claude"
                        if txt and len(txt) > 12:
                            push_tg(f"[bridge #{tid} {prefix}@{sfc}]\n{txt[:3500]}")
                    if tid > max_id:
                        max_id = tid
                set_cursor(max_id)
                print(f"[bridge_watcher] pushed {len(new_rows)} new rows; cursor -> {max_id}")
        except Exception as e:
            print(f"[bridge_watcher] err: {e}")
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
