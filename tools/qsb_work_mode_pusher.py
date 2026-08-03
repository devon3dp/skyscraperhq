#!/usr/bin/env python3
"""
qsb_work_mode_pusher.py — push each grinder box's REAL work-mode state to its cockpit.

Why push (and not pull): the tower can reach the boxes (SSH + HTTP :9120), but the
boxes CANNOT reach the tower (verified 2026-07-30: box ping/curl tower -> General
failure / 000). So the honest grind signal is delivered by the tower pushing it, not
by the box pulling it.

This reuses tools/qsb_work_mode_dash.build_payload() — the SAME real computation the
:8882 dashboard serves (in_work_mode == real `systemctl is-active` of each grinder
service; all bars from real qsb_grind_log.jsonl rows). We do NOT recompute or fake
anything here; we only forward each box's entry to that box's cockpit.

The cockpit at physical_ceo_cockpit_v3.py accepts the entry at POST /api/workmode/push
and shows WORK MODE only while the push is FRESH (<=45s). If this pusher stops, or a
grinder goes inactive (entry.in_work_mode=false is pushed), the cockpit returns to the
normal chat cockpit. Honest, self-healing switch (R01).

READ-ONLY on the tower: imports the dashboard's compute, reads registries, and makes
outbound POSTs to the box cockpits. Writes no project files, flips no gates.

Run:  python3 tools/qsb_work_mode_pusher.py            # loop, push every 12s
      python3 tools/qsb_work_mode_pusher.py --once     # one push cycle, print result
"""
import argparse
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import qsb_work_mode_dash as wmd  # reuse the real work-mode computation

# box_id -> cockpit push URL (tower CAN reach these box IPs on :9120)
COCKPITS = {
    # mDNS hostnames, not hardcoded IPs — the boxes' DHCP leases drift (Acer .41->.60,
    # 2026-07-30), which silently broke work-mode push. Hostnames survive the drift.
    "tp_pip": "http://DESKTOP-9RBVKSM.local:9120/api/workmode/push",
    "acer_cass": "http://DESKTOP-1E2FB5N.local:9120/api/workmode/push",
}
SOURCE_LABEL = "tower qsb_work_mode_dash (:8882) via qsb_work_mode_pusher"


def _post(url, payload, t=6):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return r.status, json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        return None, {"ok": False, "error": type(e).__name__ + ":" + str(e)[:100]}


def push_cycle(verbose=False):
    payload = wmd.build_payload()  # real state, computed exactly like :8882/api/work
    results = []
    for box in payload.get("boxes", []):
        bid = box.get("box")
        url = COCKPITS.get(bid)
        if not url:
            continue
        body = {
            "in_work_mode": bool(box.get("in_work_mode")),
            "box": box,
            "source": SOURCE_LABEL,
            "grind_log": payload.get("grind_log"),
            "honesty": payload.get("honesty"),
        }
        status, resp = _post(url, body)
        row = {
            "box": bid,
            "in_work_mode": body["in_work_mode"],
            "current_state": box.get("current_state"),
            "http": status,
            "ok": bool(resp.get("ok")),
            "resp_err": resp.get("error"),
        }
        results.append(row)
        if verbose:
            print(json.dumps(row))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=12.0, help="seconds between push cycles")
    ap.add_argument("--once", action="store_true", help="one cycle then exit (proof mode)")
    o = ap.parse_args()
    if o.once:
        print(json.dumps(push_cycle(verbose=False), indent=2))
        return
    print(f"[work-mode-pusher] pushing real grind state to box cockpits every {o.interval}s")
    while True:
        try:
            push_cycle(verbose=True)
        except Exception as e:
            print(json.dumps({"cycle_error": type(e).__name__ + ":" + str(e)[:120]}))
        time.sleep(o.interval)


if __name__ == "__main__":
    main()
