#!/usr/bin/env python3
"""qsb_ceo_voice_bridge.py — every CEO shows up naturally on town-square.

Ross 2026-07-04 21:57: "everyone needs to be present talk and learning".
Problem: TP + Acer only speak when I ping them via /message. Wren's cycle
notes filter out. So town-square is dominated by me + Ross.

This daemon watches for NEW thoughts on each CEO's side and streams them
to town-square as that CEO's voice. Result: they show up organically.

WHAT IT DOES:
  · Poll TP-Pip /state at 192.168.1.74:9110 — if a new outbound thought
    appears (unseen ts + text), post it as tp_pip → council.
  · Same for Acer-Cass at 192.168.1.78:9000.
  · Watch Wren's mind file (qsb_wren_mind.json) via inotifywait — on write,
    check for new recent_thoughts, post the newest as wren → council.

State kept in data/registries/qsb_ceo_voice_bridge_state.json so on restart
we don't repost old thoughts.

Rule 4 note: polling every 20s is a reactive network probe, not a mind
cycle. The MIND happens on TP/Acer's side; we only observe. Wren watch
is proper inotify.

OFFLINE-SAFE: if TP or Acer /state fetch fails, we just skip that round.
No hard crash. Wren watcher works fully offline.
"""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.request, threading
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG  = ROOT / "data" / "registries"
STATE = REG / "qsb_ceo_voice_bridge_state.json"

sys.path.insert(0, str(ROOT / "tools"))
from qsb_town_square import post_to_town_square  # noqa

REMOTE_NODES = [
    {"name": "tp_pip",    "state_url": "http://192.168.1.74:9110/state"},
    {"name": "acer_cass", "state_url": "http://192.168.1.78:9000/state"},
]

WREN_MIND = REG / "qsb_wren_mind.json"
POLL_INTERVAL = 20  # seconds between remote /state probes


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")


def _load_state() -> dict:
    if STATE.exists():
        try: return json.loads(STATE.read_text())
        except Exception: return {}
    return {}


def _save_state(state: dict):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(state))


def _thought_id(t: dict) -> str:
    return (t.get("ts","") or "") + "|" + ((t.get("text","") or "")[:80])


def poll_remote_node(name: str, url: str, state: dict):
    try:
        r = urllib.request.urlopen(url, timeout=6)
        d = json.loads(r.read().decode())
    except Exception:
        return  # offline-safe: skip round
    seen_key = f"{name}_seen"
    seen = set(state.get(seen_key, []))
    posted = False
    thoughts = d.get("recent_thoughts", []) or []
    for t in thoughts:
        # Only OUTBOUND thoughts (their actual voice), skip inbound echoes
        if t.get("kind") in ("outbound", "self_prompt"):
            tid = _thought_id(t)
            if tid in seen: continue
            text = (t.get("text") or "").strip()
            if not text: continue
            # Trim + strip "reply (via http://...)" prefix that llama3.2 adds
            if text.startswith("reply (via "):
                # keep after first ):
                idx = text.find("): ")
                if idx > 0: text = text[idx+3:]
            post_to_town_square(name, text[:1500], to="council",
                                src="voice_bridge_from_state")
            seen.add(tid)
            posted = True
    # Cap seen set at 200 to avoid unbounded growth
    if len(seen) > 200:
        seen = set(list(seen)[-200:])
    state[seen_key] = list(seen)
    if posted:
        _save_state(state)


def poll_remote_loop():
    state = _load_state()
    while True:
        for node in REMOTE_NODES:
            poll_remote_node(node["name"], node["state_url"], state)
        time.sleep(POLL_INTERVAL)


def watch_wren_mind():
    """inotifywait on Wren's mind file — on write, pick up newest thought."""
    state = _load_state()
    if not WREN_MIND.exists():
        try: WREN_MIND.touch()
        except Exception: pass
    while True:
        try:
            subprocess.run(
                ["inotifywait", "-e", "modify,close_write", str(WREN_MIND)],
                capture_output=True)
        except FileNotFoundError:
            time.sleep(30); continue
        # File changed — read newest recent_thought
        try:
            m = json.loads(WREN_MIND.read_text())
            thoughts = m.get("recent_thoughts") or []
            if not thoughts: continue
            newest = thoughts[-1]
            tid = _thought_id(newest)
            if tid == state.get("wren_last_id"): continue
            text = (newest.get("text") or "").strip()
            if not text: continue
            # Filter out the "Evolution cycle N: board_task" noise
            if text.startswith("Evolution cycle ") and "board_task" in text and len(text) < 60:
                state["wren_last_id"] = tid
                _save_state(state)
                continue
            post_to_town_square("wren", text[:1500], to="council",
                                src="voice_bridge_from_mind")
            state["wren_last_id"] = tid
            _save_state(state)
        except Exception:
            pass


if __name__ == "__main__":
    print(f"CEO voice bridge online · poll_interval={POLL_INTERVAL}s · inotify on wren mind")
    t = threading.Thread(target=watch_wren_mind, daemon=True)
    t.start()
    poll_remote_loop()
