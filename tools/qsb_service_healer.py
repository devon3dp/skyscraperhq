#!/usr/bin/env python3
"""
qsb_service_healer.py — consolidated self-healer for the tower's load-bearing,
PORT-BOUND network services.

The tower's critical HTTP servers (gene-pool router, brain router, leadership relay,
boardroom, node bridge, lumen, work-mode dash) all run under systemd with
Restart=always / on-failure. That covers ONE failure mode: the process dies. It does
NOT cover the silent one — the process stays "active" but its accept loop / handler is
WEDGED, so the port stops answering. systemd sees "active" and Restart never fires; the
dashboards and comms mesh go dark with nothing recovering them.

This is the exact gap qsb_ollama_wedge_healer.py (active-but-empty-inference) and
qsb_grinder_healer.py (active-but-log-stale) close for their services. This healer closes
it for the port-bound servers, driven by a table of {service, health_url, port}.

Each tick, per service:
  * HTTP liveness probe (any HTTP status — even 404 — means the server is answering).
    Two attempts before declaring down, so a momentary blip is not a fault.
  * If the port answers            -> log "ok", no action.
  * If the port is dead/hung       -> `systemctl restart <svc>`, then re-probe to confirm
    it came back live. Whether the process was inactive OR active-but-wedged, a restart is
    the correct, already-authorized local recovery.

SAFETY (mirrors the proven healers):
  - Only ever `systemctl restart`s a LOCAL, already-authorized service from the fixed
    table below. It flips no gate, touches no vault/.env/CLAUDE.md, cold-cycles no GPU,
    and never restarts the Codex autorunner.
  - Restart-STORM guard: never restarts the same service more than MAX_RESTARTS times in
    STORM_WINDOW_S; beyond that it logs "giving_up_alert" and leaves it for a human. An
    infinite restart loop is worse than a clean, visible failure.
  - Every restart subprocess has a hard timeout so a hung box can't wedge the healer.
  - Every action is logged honestly (incl. "ok" no-ops) to its OWN new append-only log
    data/registries/qsb_service_healer.jsonl. It writes no other registry.

Runs as a ROOT systemd oneshot on a short timer (like the other healers), so it can
`systemctl restart` natively with no runtime sudo.
"""
import json, subprocess, urllib.request, urllib.error, time, sys, calendar
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
LOG = ROOT / "data" / "registries" / "qsb_service_healer.jsonl"

# The load-bearing, port-bound services this healer guards.
# (systemd_unit, health_url, human_note)
SERVICES = [
    ("qsb-gene-pool-router",  "http://127.0.0.1:8890/", "gene-pool / brain router (MSI-local)"),
    ("qsb-brain-router-v4",   "http://127.0.0.1:8860/", "Brain Router V4 Mission Control"),
    ("qsb-leadership-relay",  "http://127.0.0.1:8855/", "leadership comms relay (Wren/TP/Asa/Bill mesh)"),
    ("qsb-boardroom",         "http://127.0.0.1:8852/", "boardroom hub / task council / town square"),
    ("qsb-node",              "http://127.0.0.1:9100/", "HQ comms bridge / node listener"),
    ("qsb-lumen",             "http://127.0.0.1:8848/", "Lumen F48 chat"),
    ("qsb-work-mode-dash",    "http://127.0.0.1:8882/", "work-mode dashboard (box cockpit feed)"),
]

PROBE_TIMEOUT = 6          # seconds per HTTP attempt
PROBE_ATTEMPTS = 2         # blips tolerated before declaring down
RESTART_TIMEOUT = 90       # hard cap on `systemctl restart`
RECOVER_SETTLE = 8         # let the service bind its port before re-probe
MAX_RESTARTS = 3           # per service ...
STORM_WINDOW_S = 900       # ... within 15 min -> give up + alert


def _now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _log(svc, action, detail=""):
    row = {"ts": _now_iso(), "service": svc, "action": action, "detail": str(detail)[:200]}
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    print(f"[service-healer] {svc} {action} {detail}", flush=True)


def _parse_ts(ts):
    # log timestamps are UTC ("...Z"); timegm interprets struct_time AS UTC (no local skew).
    try:
        return calendar.timegm(time.strptime(ts, "%Y-%m-%dT%H:%M:%SZ"))
    except Exception:
        return None


def _port_alive(url):
    """True if the server answers HTTP at all. ANY HTTP status (200/404/500) => alive;
    only a connection-level failure (refused / timeout / reset) on every attempt => down."""
    for i in range(PROBE_ATTEMPTS):
        try:
            with urllib.request.urlopen(url, timeout=PROBE_TIMEOUT) as r:
                r.read(1)
                return True
        except urllib.error.HTTPError:
            return True  # server responded (with an error status) — it is alive
        except Exception:
            if i + 1 < PROBE_ATTEMPTS:
                time.sleep(1)
                continue
            return False
    return False


def _svc_active(svc):
    try:
        r = subprocess.run(["systemctl", "is-active", svc + ".service"],
                           capture_output=True, text=True, timeout=10)
        return r.stdout.strip() == "active"
    except Exception:
        return False


def _recent_restarts(svc, now):
    """Count this healer's OWN successful restarts of svc inside the storm window."""
    n = 0
    try:
        with open(LOG) as f:
            for line in f:
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                if d.get("service") == svc and d.get("action") == "restarted_service":
                    t = _parse_ts(d.get("ts", ""))
                    if t is not None and (now - t) <= STORM_WINDOW_S:
                        n += 1
    except FileNotFoundError:
        pass
    return n


def heal_service(svc, url, note, now, force=False):
    alive = False if force else _port_alive(url)
    if alive:
        _log(svc, "ok", f"port answering ({note})")
        return False

    active = _svc_active(svc)
    _log(svc, "down_detected", f"reason={'forced' if force else 'port_unresponsive'} active={active} url={url}")

    # restart-storm guard
    recent = _recent_restarts(svc, now)
    if recent >= MAX_RESTARTS:
        _log(svc, "giving_up_alert",
             f"{recent} restarts in <{STORM_WINDOW_S}s — not restarting again; needs a human")
        return False

    try:
        r = subprocess.run(["systemctl", "restart", svc + ".service"],
                           capture_output=True, text=True, timeout=RESTART_TIMEOUT)
    except subprocess.TimeoutExpired:
        _log(svc, "restart_TIMEOUT", f"systemctl restart exceeded {RESTART_TIMEOUT}s")
        return False
    if r.returncode != 0:
        _log(svc, "restart_FAILED", r.stderr.strip()[:140])
        return False

    _log(svc, "restarted_service", f"restart #{recent + 1} in window; settling {RECOVER_SETTLE}s")
    time.sleep(RECOVER_SETTLE)
    back = _port_alive(url)
    _log(svc, "recovered" if back else "still_down_after_restart",
         "port answering again" if back else "port still unresponsive after restart")
    return back


def main():
    now = time.time()
    force = "--prove-heal" in sys.argv          # induce the down path for proof
    only = None
    for a in sys.argv[1:]:
        if a.startswith("qsb-"):
            only = a
    healed = 0
    for svc, url, note in SERVICES:
        if only and svc != only:
            continue
        if heal_service(svc, url, note, now, force=(force and (only is None or svc == only))):
            healed += 1
    print(f"[service-healer] tick done, {healed} healed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
