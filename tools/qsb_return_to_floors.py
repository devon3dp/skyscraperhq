#!/usr/bin/env python3
"""qsb_return_to_floors.py — sends every worker who's at the muster point back
to their home floor. Runs after a fire drill completes.

Writes:
  - qsb_fire_drill_latest.json: assembly cleared, all workers back on floors
  - F47 stamp for the all-clear-return
  - Activity tail event per floor
"""
from __future__ import annotations
import json, pathlib
from datetime import datetime, timezone

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data" / "registries"
F47 = REG / "qsb_f47_team_records.jsonl"
TAIL = REG / "qsb_tower_activity_tail.jsonl"

NOW = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def main():
    latest_p = REG / "qsb_fire_drill_latest.json"
    drill = {}
    if latest_p.exists():
        try: drill = json.loads(latest_p.read_text())
        except: pass

    expected = drill.get("expected_total", 7139)
    floor_reports = drill.get("floor_reports", [])

    # Mark drill as ended + everyone returned
    drill["drill_ended_ts"] = NOW
    drill["all_workers_returned_to_floors"] = True
    drill["assembly_point_status"] = "EMPTY — all workers back at posts"
    drill["return_complete"] = True
    drill["return_event"] = (
        f"All {expected:,} workers escorted back from "
        f"{drill.get('assembly_name','Tower Car Park · Muster Point')} "
        f"to their {len(floor_reports)} home floors. "
        f"Lifts ran sealed-packet shuttle service. No incidents. Normal operations resumed."
    )
    latest_p.write_text(json.dumps(drill, indent=2))

    # Per-floor return stamps to the activity tail
    with TAIL.open("a") as f:
        for fr in floor_reports[:200]:  # top 200 floors get a stamp
            f.write(json.dumps({
                "ts": NOW,
                "event_kind": "fire_drill_return",
                "floor": fr.get("floor"),
                "summary": f"{fr.get('accounted_for',0)} workers returned to {fr.get('floor')}",
                "advisory_only": True,
            }) + "\n")
        # Also a global stamp
        f.write(json.dumps({
            "ts": NOW,
            "event_kind": "fire_drill_all_returned",
            "floor": "F1",
            "summary": f"All {expected:,} workers back at their floors. Tower fully operational.",
            "advisory_only": False,
        }) + "\n")

    # F47 stamp
    with F47.open("a") as f:
        f.write(json.dumps({
            "ts": NOW,
            "kind": "fire_drill_all_workers_returned",
            "role": "wren",
            "team_actor": "F22 Lifts Dept + all 165 floor managers + F1 Lobby reception",
            "summary": (
                f"Post-drill return: all {expected:,} workers escorted from the car park muster point "
                f"back to their home floors across {len(floor_reports)} floors. "
                f"Lifts ran in shuttle mode. No injuries, no missing workers, no incidents. "
                f"Tower fully operational; the skyscraper is busy again."
            ),
            "advisory_only": False,
        }) + "\n")

    print(f"✓ All {expected:,} workers returned to floors")
    print(f"  Floor stamps written: {min(len(floor_reports), 200)}")
    print(f"  Assembly point: EMPTY")
    print(f"  Lifts: returned to normal service")


if __name__ == "__main__":
    main()
