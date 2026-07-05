#!/usr/bin/env python3
"""qsb_ceo_heartbeat.py — every 2min, poll each CEO's /state (or mind) and
publish a heartbeat post to the town-square with their live status.

Ross 2026-07-05: "make all ceos solid ... hence the town square".

Makes the town-square feel alive — each CEO shows a pulse every 2min so
Ross can see at a glance who's up + what they're thinking. Heartbeats are
tagged src=heartbeat so they can be filtered.

Cadence: 120s. Silence for 5min → red flag posted.
"""
from __future__ import annotations
import json, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
from qsb_town_square import post_to_town_square  # type: ignore

CEOS = {
    "tp_pip":    {"url": "http://192.168.1.74:9110/state", "color": "🟦"},
    "acer_cass": {"url": "http://192.168.1.78:9000/state",  "color": "🟧"},
    "wren":      {"mind": str(ROOT / "data/registries/qsb_wren_mind.json"), "color": "🟪"},
    "hq_claude": {"local": True, "color": "🟨"},
}
LAST_POST = {}  # {ceo: last_ts_epoch} — anti-spam

def _utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def _fetch_state(url: str) -> dict | None:
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception:
        return None

def _read_mind(path: str) -> dict | None:
    try: return json.loads(Path(path).read_text())
    except Exception: return None

def one_ceo(ceo: str, cfg: dict):
    if cfg.get("url"):
        d = _fetch_state(cfg["url"])
        if not d:
            post_to_town_square(ceo,
                f"{cfg['color']} heartbeat MISSED — /state unreachable {_utc()[-9:-1]}",
                to="council", src="heartbeat_miss")
            return
        uptime = d.get("uptime_s", 0)
        cycle = d.get("cycle_count") or d.get("cycle") or "?"
        brain = d.get("brain","?")
        mood = d.get("mood","")
        last_thought = ""
        for t in reversed(d.get("recent_thoughts", [])):
            if t.get("kind") in ("self_prompt","outbound","reflection"):
                last_thought = (t.get("text") or "")[:120].replace("\n"," ")
                break
        post_to_town_square(ceo,
            f"{cfg['color']} heartbeat · uptime={uptime}s · cycle={cycle} · brain={brain}{' · '+mood if mood else ''}{' · '+last_thought if last_thought else ''}",
            to="council", src="heartbeat")
    elif cfg.get("mind"):
        m = _read_mind(cfg["mind"])
        if not m:
            post_to_town_square(ceo,
                f"{cfg['color']} heartbeat MISSED — mind file unreadable",
                to="council", src="heartbeat_miss")
            return
        thoughts = m.get("recent_thoughts", [])
        last = thoughts[-1] if thoughts else {}
        last_text = (last.get("text") or "")[:120].replace("\n"," ")
        post_to_town_square(ceo,
            f"{cfg['color']} heartbeat · {len(thoughts)} thoughts on file · last: {last_text}",
            to="council", src="heartbeat")
    elif cfg.get("local"):
        post_to_town_square(ceo,
            f"{cfg['color']} heartbeat · main-loop tick",
            to="council", src="heartbeat")

def main():
    # Ross 2026-07-05 #148: no silent gaps allowed. Cadence 30s not 120s.
    CADENCE_S = 30
    print(f"  ceo-heartbeat starting · cadence {CADENCE_S}s · CEOs: {list(CEOS)}")
    while True:
        try:
            for ceo, cfg in CEOS.items():
                now = time.time()
                # allow up to 25s between same-CEO posts so all 4 rotate visibly
                if now - LAST_POST.get(ceo, 0) < 25: continue
                one_ceo(ceo, cfg)
                LAST_POST[ceo] = now
        except Exception as e:
            print(f"  [!] {e}")
        time.sleep(CADENCE_S)

if __name__ == "__main__":
    main()
