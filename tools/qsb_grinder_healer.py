#!/usr/bin/env python3
"""
qsb_grinder_healer.py — auto-heals a WEDGED box grinder (TP / Acer).

The box grinders (qsb-grinder-tp / qsb-grinder-acer) drive continuous 24/7 PRODUCE+ANALYZE
work, writing one row per unit to qsb_grind_log.jsonl. Two real failure modes:
  (A) the systemd service dies/fails       -> `systemctl is-active` != active
  (B) the service is "active" but WEDGED   -> no new grind rows for minutes
      (its local Ollama hangs, or the SSH-driven producer hangs mid-call). systemd
      still reports active, so Restart=always never fires. This is the silent one the
      cockpit shows as "STALLED" and nothing recovers today.

Each tick, per box: find the newest grind-log row for that box. If the service is not
active, OR the newest unit is older than STALL_SEC while the service claims active, the
grinder is wedged -> `systemctl restart qsb-grinder-<box>.service`, then verify it starts
producing again. Every action is logged honestly. Safe: only ever restarts a local,
already-authorized grinder service; never touches Ollama-GPU cold-cycle, minds, or vault.
Modeled on the proven qsb_ollama_wedge_healer.py.
"""
import subprocess, json, time, sys, calendar, urllib.request
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
GRIND_LOG = ROOT / "data" / "registries" / "qsb_grind_log.jsonl"
LOG = ROOT / "data" / "registries" / "qsb_grinder_healer.jsonl"
STALL_SEC = 360            # 6 min with no new unit while "active" = wedged
BOXES = {"tp_pip": "qsb-grinder-tp", "acer_cass": "qsb-grinder-acer"}
COCKPITS = {"tp_pip": "http://DESKTOP-9RBVKSM.local:9120/health",
            "acer_cass": "http://DESKTOP-1E2FB5N.local:9120/health"}


def _log(box, action, detail=""):
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "box": box, "action": action, "detail": str(detail)[:200]}
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    print(f"[grinder-healer] {box} {action} {detail}", flush=True)


def _parse_ts(ts):
    # grind-log timestamps are UTC ("...Z"); timegm interprets struct_time AS UTC.
    try:
        return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def _newest_age(box, now):
    """Age in seconds of the newest grind-log row for this box (None if none found)."""
    newest = None
    try:
        with open(GRIND_LOG) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                # count only SUCCESSFUL units — an all-erroring grinder emits a failed row
                # every ~10s, which fooled this into reporting "fresh/healthy" (Acer was
                # fake-green for 5h, 521 consecutive cockpit_unreachable). OK-freshness is truth.
                if d.get("box") == box and d.get("status") == "ok":
                    t = _parse_ts(d.get("ts", ""))
                    if t and (newest is None or t > newest):
                        newest = t
    except FileNotFoundError:
        return None
    return None if newest is None else int(now - newest)


def _svc_active(svc):
    r = subprocess.run(["systemctl", "is-active", svc + ".service"],
                       capture_output=True, text=True)
    return r.stdout.strip() == "active"


def _cockpit_ok(box):
    """Health of the real box work endpoint; a local grinder can be active while this hangs."""
    try:
        with urllib.request.urlopen(COCKPITS[box], timeout=4) as r:
            return 200 <= r.status < 500
    except Exception:
        return False


def heal_box(box, svc, now, force_stall=False):
    active = _svc_active(svc)
    age = _newest_age(box, now)
    cockpit = _cockpit_ok(box)
    # force_stall lets a caller prove the heal path without waiting for a real wedge
    # Do not restart on a momentary network blip; require a stale successful unit too.
    cockpit_wedged = (age is not None and age > 120 and not cockpit)
    wedged = force_stall or (not active) or (age is not None and age > STALL_SEC) or cockpit_wedged
    reason = ("service_inactive" if not active
              else f"log_stale_{age}s" if (age is not None and age > STALL_SEC)
              else f"cockpit_unreachable_log_age_{age}s" if cockpit_wedged
              else "forced" if force_stall else "healthy")
    if not wedged:
        _log(box, "ok", f"active, newest unit {age}s ago, cockpit={'up' if cockpit else 'down'}")
        return False
    _log(box, "wedge_detected", f"reason={reason} active={active} age={age}")
    try:
        r = subprocess.run(["systemctl", "restart", svc + ".service"],
                           capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        _log(box, "restart_TIMEOUT", "systemctl restart exceeded 120s (box unreachable?)")
        return False
    if r.returncode != 0:
        _log(box, "restart_FAILED", r.stderr.strip()[:140])
        return False
    time.sleep(10)
    back = _svc_active(svc)
    _log(box, "restarted_grinder", "service active again" if back else "still not active after restart")
    return back


def main():
    now = time.time()
    force = "--prove-heal" in sys.argv           # induce the heal path for one box (proof)
    only = None
    for a in sys.argv[1:]:
        if a in BOXES:
            only = a
    healed = 0
    for box, svc in BOXES.items():
        if only and box != only:
            continue
        if heal_box(box, svc, now, force_stall=(force and (only is None or box == only))):
            healed += 1
    if not force:
        print(f"[grinder-healer] tick done, {healed} healed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
