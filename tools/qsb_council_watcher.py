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
CHECK_EVERY_S = 5  # Ross 2026-07-05 #183: 5s scan
ALERT_COOLDOWN_S = 300     # don't spam same alert; 5min between repeats
LAST_ALERT = {}            # {ceo: ts_epoch} anti-spam
HUB = "http://127.0.0.1:8852"

# Ross rule #101 → #169 UNIFORM 10-min SLA on ALL tasks.
SLA_BY_PRIORITY = {
    "urgent": 10 * 60,
    "high":   10 * 60,
    "normal": 10 * 60,
    "low":    10 * 60,
}
IDLE_NOTE_GRACE_S = 5 * 60    # #169: 5-min silence = idle
SIGNOFF_SLA_S = 10 * 60       # awaiting_peer_signoff > 10min → return to open

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

def scan_ceo_task_cap():
    """Ross #128/#216 — max 3 in-flight per CEO. Over cap = release oldest.
    Ross 2026-07-06 fix: must NULL the owner + set state=open explicitly,
    else reopen keeps owner in 'in_progress' and task never leaves the CEO."""
    tasks = _get_tasks()
    if not tasks: return
    by_owner = {}
    for t in tasks:
        if t.get("state") in ("claimed","in_progress","ready_to_ship","awaiting_peer_signoff") and t.get("owner"):
            by_owner.setdefault(t["owner"], []).append(t)
    released_total = 0
    for owner, tlist in by_owner.items():
        if len(tlist) <= 3: continue
        tlist.sort(key=lambda t: t.get("claimed_at") or t.get("assigned_at") or t.get("created_at",""))
        for t in tlist[3:]:
            # Must clear owner + reset state — reopen alone keeps owner
            _post("/tasks/update", {"id": t["id"], "actor": "council_watcher",
                                     "owner": None, "state": "open"})
            _post("/tasks/note", {
                "id": t["id"], "actor": "council_watcher",
                "text": f"🎯 3-TASK-CAP #216 — {owner} was at {len(tlist)} > cap 3. Released to open pool."
            })
            released_total += 1
    if released_total:
        try:
            post_to_town_square("council_watcher",
                f"🎯 3-CAP scan · released {released_total} surplus task(s) back to open pool",
                to="council", src="watcher_ceo_cap")
        except Exception: pass


def scan_signoff_cap():
    """Ross 2026-07-05 #141: max 5 tasks in awaiting_peer_signoff system-wide.
    Over cap = urgency signal + auto-release oldest to open with SLA note."""
    tasks = _get_tasks()
    awaiting = [t for t in tasks if t.get("state") == "awaiting_peer_signoff"]
    if len(awaiting) <= 5: return
    over = len(awaiting) - 5
    # Sort by sandbox_passed_at ASC — release the OLDEST first
    awaiting.sort(key=lambda t: _iso_epoch(t.get("sandbox_passed_at") or t.get("started_at") or t.get("created_at","")))
    to_release = awaiting[:over]
    for t in to_release:
        _post("/tasks/reopen", {"id": t["id"], "actor": "council_watcher"})
        _post("/tasks/note", {
            "id": t["id"], "actor": "council_watcher",
            "text": f"🚨 SIGNOFF CAP #141 — {len(awaiting)} tasks awaiting > 5 cap. Released oldest to open for re-take/re-verify. Original owner @{t.get('owner','?')} may re-claim."
        })
    try:
        post_to_town_square("council_watcher",
            f"🚨 SIGNOFF-CAP #141 · queue {len(awaiting)} > 5 · released {len(to_release)} oldest back to open",
            to="council", src="watcher_signoff_cap")
    except Exception: pass


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
        # Ross 2026-07-05 #173: DISPATCH other 3 CEOs to investigate + fix
        try:
            other_ceos = [c for c in CEOS if c != m["ceo"]]
            for helper in other_ceos:
                probe_msg = (f"CEO OFFLINE ALERT: {m['ceo']} silent {m['silent_s']}s. "
                             f"As {helper}, please: (1) probe your view of {m['ceo']}, "
                             f"(2) report reachability, (3) suggest one concrete recovery step. "
                             f"Reply in <100 chars.")
                # Route via brain router for each helper
                try:
                    import urllib.request as _ur
                    body = json.dumps({"prompt":probe_msg,"caller":helper,"task":"chat"}).encode()
                    r = _ur.urlopen(_ur.Request("http://127.0.0.1:8852/brain/route",
                        data=body, headers={"Content-Type":"application/json"}), timeout=15)
                    d = json.loads(r.read())
                    reply = d.get("reply","")[:120]
                    post_to_town_square(helper,
                        f"🔎 {helper} probing {m['ceo']}: {reply}",
                        to="council", src="offline_helper_probe")
                except Exception: pass
        except Exception: pass

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
            # Ross rule #141 — signoff cap enforcement
            scan_signoff_cap()
            # Ross rule #128/#216 — per-CEO 3-task cap enforcement
            scan_ceo_task_cap()
        except Exception as e:
            print(f"  [!] watcher error: {e}")
        time.sleep(CHECK_EVERY_S)

if __name__ == "__main__":
    main()
