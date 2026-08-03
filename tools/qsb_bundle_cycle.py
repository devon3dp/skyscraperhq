#!/usr/bin/env python3
"""qsb_bundle_cycle.py — one full offline-first choreography tick (tower side).

Run on a timer. For each worker box:
  1. If reachable: collect+apply any results the box finished (offline or not),
     then build a fresh bundle from real pending council work and push it, then
     kick a grind on the box (the grind itself runs offline-safe).
  2. If NOT reachable: skip gracefully — the box keeps grinding whatever bundle
     it already holds on local disk, and this tick will collect it next time HQ
     can reach it.

The whole point: HQ being up/down never blocks a box's grind. This tick only
does the SYNC half, which is naturally best-effort.
"""
from __future__ import annotations
import json, sys, datetime
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
import qsb_bundle_sync as sync
import qsb_work_bundle as wb

BOX_SIZE = 5


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def tick():
    report = {"ts": now(), "boxes": {}}
    for box in sync.BOXES:
        entry = {}
        try:
            if not sync.reachable(box):
                entry["reachable"] = False
                report["boxes"][box] = entry
                continue
            entry["reachable"] = True
            # 1. collect+apply anything already done (best-effort)
            try:
                entry["collect"] = sync.collect(box)
            except Exception as e:
                entry["collect_err"] = str(e)[:200]
            # 2. build + push a fresh bundle of real pending work
            built = wb.build(box, BOX_SIZE, "llama3.2")
            entry["built"] = built
            entry["push"] = sync.push(box, built["path"])
            # 3. kick an offline-safe grind on the box (non-blocking best-effort)
            try:
                entry["drive"] = {"rc": sync.drive(box)["rc"]}
            except Exception as e:
                entry["drive_err"] = str(e)[:200]
        except Exception as e:
            entry["error"] = str(e)[:200]
        report["boxes"][box] = entry
    log = ROOT / "data/registries/qsb_bundle_cycle_log.jsonl"
    with open(log, "a") as f:
        f.write(json.dumps(report) + "\n")
    print(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    tick()
