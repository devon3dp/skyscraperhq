#!/usr/bin/env python3
"""
qsb_underground_selfheal.py — self-healing watchdog for the QSB Underground map pipeline.

Runs as a ROOT systemd oneshot on a short timer. It detects + heals the REAL failure
modes we hit building the map, and logs every action honestly (no silent heals):

  1. transit-map DOWN / UNRESPONSIVE  -> restart qsb-transit-map.service
  2. STALE RENDER after a code edit    -> the exact bug that bit us: the map file was
     edited AFTER the running process started, so :8875 serves old code. Detect by
     comparing the map file mtime to the service's ActiveEnterTimestamp; if the file is
     newer, restart so the live map picks up the new code/feed reader.
  3. STALLED PRODUCER FEED             -> if the shared traffic feed hasn't grown in
     >6min AND a producer timer is dead, restart the dead producer timer(s).

Honest: every check is real (HTTP probe, mtime, systemd state). Every heal writes a row
to data/registries/qsb_underground_selfheal.jsonl. If nothing needs healing it logs "ok".
Runs as root (systemd) so it can `systemctl restart` natively — no sudo password at runtime.
"""
import json, subprocess, urllib.request, time, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
MAP_TOOL = ROOT / "tools" / "qsb_tower_transit_map.py"
FEED = ROOT / "data" / "registries" / "qsb_map_traffic_feed.jsonl"
LOG = ROOT / "data" / "registries" / "qsb_underground_selfheal.jsonl"
API = "http://127.0.0.1:8875/api/data"
MAP_SVC = "qsb-transit-map.service"
PRODUCERS = ["qsb-worker-info-router.timer", "qsb-lift-traffic.timer",
             "qsb-worker-activation.timer", "qsb-floor-activity.timer"]
FEED_STALE_S = 360   # 6 min


def _log(action, reason, detail=""):
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "action": action, "reason": reason, "detail": str(detail)[:200]}
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    print(f"[selfheal] {action} :: {reason} {detail}", flush=True)


def _active(svc):
    return subprocess.run(["systemctl", "is-active", "--quiet", svc]).returncode == 0


def _restart(svc, reason, detail=""):
    r = subprocess.run(["systemctl", "restart", svc], capture_output=True, text=True)
    ok = r.returncode == 0
    _log(("restarted:" if ok else "restart_FAILED:") + svc, reason,
         (detail + " " + r.stderr.strip()).strip()[:160])
    return ok


def _mtime(p):
    try:
        return p.stat().st_mtime
    except Exception:
        return 0


def _svc_start_epoch(svc):
    r = subprocess.run(["systemctl", "show", "-p", "ActiveEnterTimestamp", "--value", svc],
                       capture_output=True, text=True)
    ts = (r.stdout or "").strip()
    if not ts:
        return 0
    d = subprocess.run(["date", "-d", ts, "+%s"], capture_output=True, text=True)
    try:
        return int(d.stdout.strip())
    except Exception:
        return 0


def main():
    healed = []

    # ── Check 1: transit-map responsive on :8875? ──
    alive = False
    try:
        with urllib.request.urlopen(API, timeout=8) as r:
            json.load(r)
        alive = True
    except Exception as e:
        if not _active(MAP_SVC):
            if _restart(MAP_SVC, "map service was INACTIVE"):
                healed.append("map_inactive")
        else:
            if _restart(MAP_SVC, "map UNRESPONSIVE on :8875", str(e)[:50]):
                healed.append("map_unresponsive")

    # ── Check 2: stale render — map file edited after the running process started ──
    if alive:
        start = _svc_start_epoch(MAP_SVC)
        fmt = _mtime(MAP_TOOL)
        if start and fmt > start + 5:
            if _restart(MAP_SVC, "map CODE newer than running process (stale render)",
                        f"file@{int(fmt)} > start@{start}"):
                healed.append("stale_code")

    # ── Check 3: producer feed stalled + a producer timer dead ──
    feed_age = time.time() - _mtime(FEED)
    if feed_age > FEED_STALE_S:
        dead = [t for t in PRODUCERS if not _active(t)]
        for t in dead:
            if _restart(t, "producer timer INACTIVE while feed stale", f"feed_age={int(feed_age)}s"):
                healed.append("producer:" + t)
        if not dead:
            _log("warn", "feed stale but all producer timers active", f"feed_age={int(feed_age)}s")

    if not healed:
        _log("ok", "all healthy", f"map={'up' if alive else 'down'} feed_age={int(feed_age)}s")

    print(json.dumps({"healed": healed, "map_alive": alive}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
