#!/usr/bin/env python3
"""qsb_team_liveness_watchdog.py — R108 / GATE 19 team liveness sweep.

Every CEO/runtime/service is probed; each is classified ONLINE/STALE/
UNREACHABLE/OFFLINE/IDENTITY_MISMATCH. Non-ONLINE nodes get a Task Council
recovery task (deduped — only if none open for that node) when --create-recovery
is set. Read-only probes only; NO destructive recovery here (restarts are a
separate, approved step). Designed to be run every ~5 min by a systemd timer.
"""
import argparse, json, socket, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
sys.path.insert(0, str(ROOT / "tools"))
import qsb_council_tasks as qct

WATCHDOG_LOG = REG / "qsb_team_liveness_watchdog.jsonl"

def utc():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

# name, health/identity url, expected id (None = reachability only), id json key
NODES = [
    ("claude_hq",       "http://127.0.0.1:8850/whoami", "claude_hq", "id"),
    ("tp_pip",          "http://127.0.0.1:8861/whoami", "tp_pip",    "id"),
    ("acer_cass",       "http://127.0.0.1:8862/whoami", "acer_cass", "id"),
    ("wren",            "http://127.0.0.1:8851/",       None,        None),
    ("boardroom_hub",   "http://127.0.0.1:8852/",       None,        None),
    ("gene_pool_router","http://127.0.0.1:8860/health", None,        None),
    ("tour_guide",      "http://127.0.0.1:8854/",       None,        None),
    ("receptionist_pi", "ssh://qsb-reception.local:22", None,        None),
]

def probe(url, id_key):
    """Return a probe dict for classify_liveness()."""
    host = url.split("//", 1)[-1].split("/", 1)[0].split(":")[0]
    # ssh:// nodes (e.g. the Pi desktop, which serves no HTTP): reachable = a TCP
    # connect to the ssh port succeeds.
    if url.startswith("ssh://"):
        port = int(url.rsplit(":", 1)[-1]) if url.rsplit(":", 1)[-1].isdigit() else 22
        try:
            socket.gethostbyname(host)
        except Exception:
            return {"host_down": True}
        try:
            with socket.create_connection((host, port), timeout=3):
                return {"reachable": True, "identity": None, "last_heartbeat_ts": None}
        except Exception:
            return {"reachable": False}
    # host_down: DNS/hostname not resolvable AND not an IP we can reach
    try:
        socket.gethostbyname(host)
    except Exception:
        if not host.replace(".", "").isdigit():
            return {"host_down": True}
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "qsb-watchdog"})
        with urllib.request.urlopen(req, timeout=4) as r:
            raw = r.read(4000).decode("utf-8", "ignore")
        ident = None
        if id_key:
            try: ident = json.loads(raw).get(id_key)
            except Exception: ident = None
        return {"reachable": True, "identity": ident, "last_heartbeat_ts": None}
    except Exception:
        return {"reachable": False}

def open_recovery_exists(node_name) -> bool:
    tag = f"node:{node_name}"
    for t in qct.snapshot().get("tasks", []):
        if tag in (t.get("tags") or []) and t.get("state") not in ("done", "denied", "closed"):
            return True
    return False

def sweep(create_recovery=False, detector="hq_claude"):
    results = []
    for name, url, exp, key in NODES:
        p = probe(url, key)
        p["expected_id"] = exp
        state = qct.classify_liveness(p)
        row = {"node": name, "url": url, "state": state,
               "identity": p.get("identity"), "expected_id": exp}
        if state != "ONLINE" and create_recovery:
            if open_recovery_exists(name):
                row["recovery"] = "already_open"
            else:
                r = qct.create_recovery_task(name, last_url=url, last_heartbeat="n/a",
                                             detector=detector, state=state,
                                             evidence=f"watchdog sweep {utc()} -> {state}")
                row["recovery"] = f"created:{r.get('task_id')}"
        results.append(row)
    ev = {"ts": utc(), "kind": "liveness_sweep", "detector": detector, "results": results}
    WATCHDOG_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(WATCHDOG_LOG, "a") as f:
        f.write(json.dumps(ev) + "\n")
    return results

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--create-recovery", action="store_true",
                    help="create deduped recovery tasks for non-ONLINE nodes")
    a = ap.parse_args()
    res = sweep(create_recovery=a.create_recovery)
    for r in res:
        flag = "" if r["state"] == "ONLINE" else "  <== " + r["state"]
        print(f"  {r['node']:18s} {r['state']:16s} {r['url']}{flag}")
    bad = [r["node"] for r in res if r["state"] != "ONLINE"]
    print(f"\nONLINE: {len(res)-len(bad)}/{len(res)}   needs-recovery: {bad or 'none'}")
