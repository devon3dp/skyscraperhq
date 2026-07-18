#!/usr/bin/env python3
"""qsb_wren_keep_working.py — daemon that keeps Wren firing.

Ross 2026-07-05 #118: "some one always remind wren to keep working".

Watches nvidia-smi + Wren's evolution loop + puller. If GPU utilization
drops below 30% for > 60s AND there are pending open tasks she could
work, auto-dispatch a fresh chain step. Cap: max 8 nudges/hour.

Also posts a "Wren nudged" line to town-square so Ross HEARS her working.
"""
from __future__ import annotations
import json, subprocess, sys, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
from qsb_town_square import post_to_town_square  # type: ignore

CHECK_EVERY_S = 30
IDLE_THRESHOLD_S = 60          # GPU idle > this = nudge her
GPU_UTIL_THRESHOLD = 30        # below 30% = idle
NUDGE_CAP_PER_HOUR = 8
NUDGES = []  # timestamps

def _utc(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def gpu_util() -> int | None:
    try:
        r = subprocess.run(["nvidia-smi","--query-gpu=utilization.gpu","--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5)
        return int(r.stdout.strip().split()[0])
    except Exception:
        return None

def open_tasks_exist() -> bool:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8852/tasks/data", timeout=5) as r:
            d = json.loads(r.read())
        return (d.get("open",0) + d.get("in_progress",0)) > 0
    except Exception:
        return False

def dispatch_chain():
    prompt = ("Wren keep-working nudge · Ross wants your fans on. Task: design 1 "
              "polished dashboard component: 25 lines CSS, 3 keyframes, palette 6 hex, "
              "1 hover state. Reply with the complete answer, no preamble.")
    subprocess.Popen(
        ["timeout", "150", "python3",
         str(ROOT / "tools/qsb_wren_local_agent.py"), "--task", prompt],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)

def main():
    print(f"  wren-keep-working daemon · check every {CHECK_EVERY_S}s · nudge cap {NUDGE_CAP_PER_HOUR}/hr")
    idle_since = None
    while True:
        try:
            now = time.time()
            # prune nudge stamps
            global NUDGES
            NUDGES = [t for t in NUDGES if now - t < 3600]
            u = gpu_util()
            if u is None:
                time.sleep(CHECK_EVERY_S); continue
            if u < GPU_UTIL_THRESHOLD:
                if idle_since is None: idle_since = now
                idle_dur = now - idle_since
                if idle_dur >= IDLE_THRESHOLD_S and len(NUDGES) < NUDGE_CAP_PER_HOUR and open_tasks_exist():
                    dispatch_chain()
                    NUDGES.append(now)
                    idle_since = None
                    try:
                        post_to_town_square("wren",
                            f"🎨 nudged awake — GPU was {u}% for {int(idle_dur)}s, chain dispatched · nudge {len(NUDGES)}/{NUDGE_CAP_PER_HOUR}/hr",
                            to="council", src="wren_nudge")
                    except Exception: pass
                    print(f"  ⚡ nudged Wren @ {u}% util after {int(idle_dur)}s idle")
            else:
                idle_since = None
        except Exception as e:
            print(f"  [!] loop error: {e}")
        time.sleep(CHECK_EVERY_S)

if __name__ == "__main__":
    main()
