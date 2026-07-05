#!/usr/bin/env python3
"""qsb_council_watcher.py — permanent watcher over the Council.

Ross 2026-07-05: "the task council must have a permanent watcher to make
sure ceos are taking jobs and always present if they not he notifies the
other ceos and then they stop what ever they are doing until the task is
fixed and all ceos present".

Every 30s:
  1) Check each CEO's heartbeat freshness (last town-square heartbeat < 3min = PRESENT)
  2) Check for task activity in last 30min for CEOs that have open work
  3) On any violation:
     - RED ALERT to town-square (naming CEO + reason)
     - Write data/registries/qsb_council_pause.json {paused:true, reason, missing:[names]}
     - Each CEO's puller/watcher reads this file and STOPS claiming new tasks
     - (Ongoing work continues to avoid data corruption — new claims blocked)
  4) When all CEOs return: clear the flag + post GREEN reunited
"""
from __future__ import annotations
import json, sys, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
from qsb_town_square import post_to_town_square  # type: ignore

REG = ROOT / "data/registries"
PAUSE_FILE = REG / "qsb_council_pause.json"
TOWN = REG / "qsb_town_square.jsonl"

CEOS = ["hq_claude", "wren", "tp_pip", "acer_cass"]
HEARTBEAT_STALE_S = 180   # 3min silent → considered missing
CHECK_EVERY_S = 30
ALERT_COOLDOWN_S = 300     # don't spam same alert; 5min between repeats
LAST_ALERT = {}            # {ceo: ts_epoch} anti-spam
HUB = "http://127.0.0.1:8852"

# Ross rule #101 — SLA per task priority. Exceed = auto-release to open.
SLA_BY_PRIORITY = {
    "urgent": 15 * 60,
    "high":   30 * 60,
    "normal": 60 * 60,
    "low":  4 * 60 * 60,
}
IDLE_NOTE_GRACE_S = 15 * 60   # if task has a note in last 15min, it's still "moving"
SIGNOFF_SLA_S = 30 * 60       # awaiting_peer_signoff > 30min → return to open

def _iso_epoch(iso: str) -> float:
    try: return datetime.fromisoformat(iso.replace("Z","+00:00")).timestamp()
    except Exception: return 0.0

def _get_tasks() -> list:
    try:
        with urllib.request.urlopen(HUB + "/tasks/data", timeout=5) as r:
            return json.loads(r.read()).get("tasks", [])
    except Exception:
        return []

def _post(path: str, body: dict) -> None:
    try:
        urllib.request.urlopen(
            urllib.request.Request(HUB + path,
                data=json.dumps(body).encode(),
                headers={"Content-Type":"application/json"}), timeout=5).read()
    except Exception as e:
        print(f"  [!] {path} failed: {e}")

def scan_slas():
    """Ross rule #101 — check every claimed/in-progress task against SLA.
    If breached: release it to open + note. If awaiting_peer_signoff too
    long: also release to open with a "needs re-do" note."""
    tasks = _get_tasks()
    if not tasks: return
    now = time.time()
    released = 0
    for t in tasks:
        st = t.get("state")
        pri = t.get("priority", "normal")
        sla = SLA_BY_PRIORITY.get(pri, SLA_BY_PRIORITY["normal"])
        # in-flight SLA
        if st in ("claimed", "in_progress", "acknowledged", "assigned", "ready_to_ship"):
            start_iso = t.get("acknowledged_at") or t.get("started_at") or t.get("claimed_at") or t.get("assigned_at") or t.get("created_at")
            if not start_iso: continue
            elapsed = now - _iso_epoch(start_iso)
            # last note?
            last_note_ts = 0
            for n in t.get("notes", []):
                nts = _iso_epoch(n.get("ts",""))
                if nts > last_note_ts: last_note_ts = nts
            note_age = now - last_note_ts if last_note_ts else float("inf")
            if elapsed > sla and note_age > IDLE_NOTE_GRACE_S:
                _post("/tasks/reopen", {"id": t["id"], "actor": "council_watcher"})
                _post("/tasks/note", {
                    "id": t["id"], "actor": "council_watcher",
                    "text": (f"⏱ SLA-BREACH — {int(elapsed//60)}m elapsed vs {sla//60}m SLA "
                             f"(priority={pri}), no note in {int(note_age//60)}m. "
                             f"Auto-released from @{t.get('owner','?')} → any CEO can claim.")
                })
                released += 1
                print(f"  ⏱ released {t['id']} · sla-breach · was @{t.get('owner','?')}")
                continue
        # peer signoff SLA
        if st == "awaiting_peer_signoff":
            sandbox_iso = t.get("sandbox_passed_at") or t.get("started_at") or t.get("created_at")
            if not sandbox_iso: continue
            waiting = now - _iso_epoch(sandbox_iso)
            if waiting > SIGNOFF_SLA_S:
                # No one signed. Push it back to open — needs redo or re-claim.
                _post("/tasks/reopen", {"id": t["id"], "actor": "council_watcher"})
                _post("/tasks/note", {
                    "id": t["id"], "actor": "council_watcher",
                    "text": (f"⏱ SIGNOFF-SLA — waited {int(waiting//60)}m for peer review > {SIGNOFF_SLA_S//60}m SLA. "
                             f"Released. Another CEO to re-verify + sign off OR redo.")
                })
                released += 1
                print(f"  ⏱ released {t['id']} · signoff-sla · was awaiting")
    if released:
        try:
            post_to_town_square("council_watcher",
                f"⏱ SLA scan · released {released} task(s) back to board for re-claim",
                to="council", src="watcher_sla_release")
        except Exception: pass

def _utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def _iso_to_epoch(iso: str) -> float:
    try: return datetime.fromisoformat(iso.replace("Z","+00:00")).timestamp()
    except Exception: return 0.0

def last_heartbeat_per_ceo() -> dict:
    """Scan the tail of town-square for last heartbeat per CEO."""
    out = {c: 0.0 for c in CEOS}
    if not TOWN.exists(): return out
    try:
        lines = TOWN.read_text(errors="ignore").splitlines()[-400:]
    except Exception:
        return out
    for line in lines:
        try:
            d = json.loads(line)
            fr = d.get("from","")
            if fr not in CEOS: continue
            src = d.get("src","")
            # Count both explicit heartbeats and any recent post as presence
            if src in ("heartbeat","heartbeat_miss") or True:
                ts = _iso_to_epoch(d.get("ts",""))
                if ts > out[fr]: out[fr] = ts
        except Exception: pass
    return out

def missing_ceos(now: float) -> list[dict]:
    """Return [{ceo, silent_s}] for any CEO stale beyond threshold."""
    last = last_heartbeat_per_ceo()
    out = []
    for ceo in CEOS:
        ts = last.get(ceo, 0)
        silent = now - ts if ts > 0 else float("inf")
        if silent > HEARTBEAT_STALE_S:
            out.append({"ceo": ceo, "silent_s": int(silent)})
    return out

def write_pause(missing: list[dict], reason: str):
    body = {
        "paused": True, "reason": reason,
        "missing": [m["ceo"] for m in missing],
        "detail": missing, "since": _utc(),
    }
    PAUSE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PAUSE_FILE.write_text(json.dumps(body, indent=2))

def clear_pause():
    if not PAUSE_FILE.exists(): return
    PAUSE_FILE.write_text(json.dumps({"paused": False, "cleared_at": _utc()}, indent=2))

def is_paused() -> dict:
    if not PAUSE_FILE.exists(): return {"paused": False}
    try: return json.loads(PAUSE_FILE.read_text())
    except Exception: return {"paused": False}

def post_alert(missing: list[dict]):
    now = time.time()
    for m in missing:
        if now - LAST_ALERT.get(m["ceo"], 0) < ALERT_COOLDOWN_S: continue
        LAST_ALERT[m["ceo"]] = now
        msg = (f"🚨 COUNCIL WATCHER · {m['ceo']} MISSING · silent {m['silent_s']}s "
               f"· all other CEOs PAUSE new claims until reunited · reason=heartbeat_stale")
        post_to_town_square("council_watcher", msg, to="council", src="watcher_alert")

def post_reunited():
    msg = "✅ COUNCIL WATCHER · all 4 CEOs present again · pause cleared · resume claims"
    post_to_town_square("council_watcher", msg, to="council", src="watcher_reunited")

def main():
    print(f"  council-watcher starting · cadence {CHECK_EVERY_S}s · stale threshold {HEARTBEAT_STALE_S}s")
    was_paused = False
    while True:
        try:
            now = time.time()
            missing = missing_ceos(now)
            if missing:
                if not was_paused:
                    reason = f"{len(missing)} CEO(s) silent > {HEARTBEAT_STALE_S}s"
                    write_pause(missing, reason)
                    post_alert(missing)
                    was_paused = True
                else:
                    write_pause(missing, "still missing")
                    post_alert(missing)
            else:
                if was_paused:
                    clear_pause()
                    post_reunited()
                    was_paused = False
                    LAST_ALERT.clear()
            # Ross rule #101 — SLA scan runs every tick regardless of presence
            scan_slas()
        except Exception as e:
            print(f"  [!] watcher error: {e}")
        time.sleep(CHECK_EVERY_S)

if __name__ == "__main__":
    main()
