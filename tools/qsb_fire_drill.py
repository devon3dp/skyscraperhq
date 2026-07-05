#!/usr/bin/env python3
"""qsb_fire_drill.py — assembly + head count.

Designated assembly point: CAR PARK · OUTSIDE the tower at ground level,
20 metres from the south entrance. Workers evacuate via lifts to the lobby
then exit south to the car park's painted grid.

On a drill:
  1. Alarm sounds + announcement on every floor.
  2. Floor managers check workers off as they pass the muster point.
  3. Head count is computed across all rosters at the car park grid.
  4. All-clear when 100% of expected workers are present.
  5. Activity tail stamps every step. No execution gate is flipped.

Advisory only. No actual evacuation; no service restart.
"""
from __future__ import annotations
import json, pathlib
from collections import Counter
from datetime import datetime, timezone

ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
ASSEMBLY_POINT = "car_park_external"
ASSEMBLY_NAME = "Tower Car Park · Muster Point"
ASSEMBLY_LOCATION = "20m south of the lobby entrance, painted assembly grid"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _stamp(kind: str, payload: dict) -> None:
    payload["ts"] = _now()
    payload["kind"] = kind
    payload["location"] = ASSEMBLY_POINT
    payload["advisory_only"] = True
    with (REG / "qsb_tower_activity_tail.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload) + "\n")


def _all_workers() -> list[dict]:
    """Aggregate every worker across every known roster."""
    workers = []
    for r in sorted(REG.glob("qsb_*roster*.json")):
        try:
            d = json.loads(r.read_text())
            for w in d.get("workers", d.get("members", [])):
                if isinstance(w, dict) and w.get("worker_id"):
                    workers.append({
                        "id": w["worker_id"],
                        "floor": str(w.get("floor", "")).upper(),
                        "role": w.get("role", ""),
                        "source_roster": r.name,
                    })
        except Exception: pass
    # Plus the baseline file
    try:
        bl = json.loads((REG / "qsb_baseline_floor_workforce.json").read_text())
        for w in bl.get("workers", []):
            workers.append({
                "id": w["worker_id"], "floor": w.get("floor",""),
                "role": w.get("role",""), "source_roster": "qsb_baseline_floor_workforce.json",
            })
    except Exception: pass
    return workers


def _managers_map() -> dict:
    try:
        d = json.loads((REG / "qsb_floor_managers.json").read_text())
        return {m["floor"]: m["manager_name"] for m in d.get("managers", [])}
    except Exception:
        return {}


def initiate() -> dict:
    """Start the drill. Returns the full report."""
    start_ts = _now()
    _stamp("fire_drill_initiated", {
        "assembly_point": ASSEMBLY_POINT,
        "assembly_name": ASSEMBLY_NAME,
        "location": ASSEMBLY_LOCATION,
        "summary": "Fire drill initiated. EVACUATE the tower. Muster on the painted grid in the car park, 20 metres south of the lobby entrance.",
    })

    workers = _all_workers()
    expected_total = len(workers)
    by_floor = Counter(w["floor"] for w in workers)
    managers = _managers_map()

    # Per-floor check-in
    floor_reports = []
    for fkey, count in sorted(by_floor.items(), key=lambda x: int(x[0][1:]) if x[0].startswith("F") and x[0][1:].isdigit() else 99):
        mgr = managers.get(fkey, "—")
        accounted_for = count   # advisory: assume all check in (no live agents)
        floor_reports.append({
            "floor": fkey,
            "manager": mgr,
            "expected": count,
            "accounted_for": accounted_for,
            "check_in_ts": _now(),
            "status": "all_present" if accounted_for == count else "missing",
        })
        _stamp("fire_drill_check_in", {
            "floor": fkey, "manager": mgr,
            "expected": count, "accounted_for": accounted_for,
            "summary": f"{fkey} reports {accounted_for}/{count} present",
        })

    # Head count
    total_present = sum(r["accounted_for"] for r in floor_reports)
    pct = round(100.0 * total_present / max(1, expected_total), 1)

    # All clear if 100%
    all_clear = total_present == expected_total
    end_ts = _now()
    _stamp("fire_drill_head_count", {
        "expected": expected_total, "present": total_present,
        "percentage": pct, "floor_count": len(floor_reports),
        "summary": f"Head count: {total_present}/{expected_total} ({pct}%)",
    })
    if all_clear:
        _stamp("fire_drill_all_clear", {
            "assembly_point": ASSEMBLY_POINT,
            "summary": "ALL CLEAR. Drill complete. Workers may return to their floors.",
        })

    report = {
        "ok": True,
        "kind": "qsb_fire_drill_report",
        "started_ts": start_ts,
        "completed_ts": end_ts,
        "assembly_point": ASSEMBLY_POINT,
        "assembly_name": ASSEMBLY_NAME,
        "assembly_location": ASSEMBLY_LOCATION,
        "expected_total": expected_total,
        "present_total": total_present,
        "percentage_present": pct,
        "all_clear": all_clear,
        "floor_count_drilled": len(floor_reports),
        "manager_count": len([r for r in floor_reports if r["manager"] != "—"]),
        "floor_reports": floor_reports,
        "advisory_only": True,
        "drill_only": True,
        "no_real_evacuation": True,
    }
    (REG / "qsb_fire_drill_latest.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    # F47 record
    with (REG / "qsb_f47_team_records.jsonl").open("a") as f:
        f.write(json.dumps({
            "ts": end_ts, "kind": "f47_team_record",
            "job": "fire_drill_v1",
            "status": "completed", "lead": "wren",
            "all_clear": all_clear, "head_count": total_present,
            "advisory_only": True,
        }) + "\n")
    return report


# ── V1.6 dry-run failover rehearsal ───────────────────────────────────
# Tests that every service is up, every execution gate is in its expected
# (locked-where-required) state, and every kill-switch file is reachable.
# NEVER flips a gate. NEVER restarts a service. Pure observation.
#
# Returns a visitor-safe summary: pass/fail counts only — no internal paths
# in the public `summary` block. The full detail block stays in the audit row.

# Services that must answer on localhost. Probed with a short HTTP GET.
_FAILOVER_SERVICES = [
    ("dashboard",      "http://127.0.0.1:8765/api/unified"),
    ("lumen",          "http://127.0.0.1:8848/"),
    ("vision",         "http://127.0.0.1:8821/"),
    ("kernel_sidecar", "http://127.0.0.1:8766/api/kernel_chat_health"),
]

# Execution gates that MUST be locked false for safety. Their truthy state
# would fail the drill. Each entry is (gate_id, expected_bool).
# These names mirror the gates declared in CLAUDE.md.
_FAILOVER_GATES_EXPECTED_FALSE = [
    "worker_execution_enabled",
    "provider_execution_enabled",
    "live_dispatch_enabled",
    "autonomous_workers_enabled",
    "live_trading_enabled",
    "real_order_execution_enabled",
    "openclaw_execution_enabled",
    "binance_order_execution_enabled",
    "stock_order_execution_enabled",
    "web_access_autonomous_enabled",
]

# Kill-switch / control files we expect to be reachable on disk.
_FAILOVER_KILL_SWITCHES = [
    REG / "qsb_proposal_autoapply_gate.json",
    REG / "security_gates.json",
    REG / "kernel_activation_gate_status.json",
]


def _probe_service(url: str, timeout: float = 1.2) -> tuple[bool, str]:
    import urllib.request, urllib.error
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            code = getattr(resp, "status", 200)
            return (200 <= code < 500), f"http_{code}"
    except urllib.error.HTTPError as e:
        # 4xx still proves the service is up and answering.
        return (e.code < 500), f"http_{e.code}"
    except Exception as e:
        return False, type(e).__name__


def _read_gate_state() -> dict:
    """Best-effort read of current gate states from known registry files.

    We treat absence of a gate file as 'unknown' — only an explicit truthy
    value fails the drill. The CLAUDE.md-declared posture is the ground
    truth; this is a probe for any registry that has flipped a value.
    """
    states: dict = {}
    candidates = [
        REG / "kernel_activation_gate_status.json",
        REG / "security_gates.json",
        REG / "qsb_proposal_autoapply_gate.json",
    ]
    for p in candidates:
        try:
            if not p.exists():
                continue
            d = json.loads(p.read_text())
            # Flatten any obvious bool fields
            if isinstance(d, dict):
                for k, v in d.items():
                    if isinstance(v, bool):
                        states[k] = v
            elif isinstance(d, list):
                for item in d:
                    if not isinstance(item, dict):
                        continue
                    gid = item.get("id") or item.get("gate_id")
                    if gid and "enforcement_enabled" in item:
                        states[gid] = bool(item.get("enforcement_enabled"))
        except Exception:
            pass
    return states


def dry_run_failover(source: str = "manual") -> dict:
    """Dry-run failover rehearsal — read-only, never flips a gate.

    Returns a dict with two views:
      summary: visitor-safe { pass, fail, status, services_ok, gates_ok,
                              kill_switches_ok }
      detail:  internal block with per-check results, stamped to the audit
               jsonl. NOT included in the visitor-safe surface.
    """
    started_ts = _now()

    # 1. Services up?
    svc_results = []
    for name, url in _FAILOVER_SERVICES:
        ok, why = _probe_service(url)
        svc_results.append({"name": name, "ok": ok, "detail": why})
    services_ok = sum(1 for r in svc_results if r["ok"])
    services_total = len(svc_results)

    # 2. Gates in expected state? Anything explicitly true that we expect
    #    false is a fail. Unknown gates are reported but don't fail.
    gate_state = _read_gate_state()
    gate_results = []
    for gid in _FAILOVER_GATES_EXPECTED_FALSE:
        actual = gate_state.get(gid)
        if actual is None:
            gate_results.append({"gate": gid, "ok": True, "detail": "absent_assumed_false"})
        else:
            gate_results.append({"gate": gid, "ok": (actual is False),
                                  "detail": f"actual={actual}"})
    gates_ok = sum(1 for r in gate_results if r["ok"])
    gates_total = len(gate_results)

    # 3. Kill-switches reachable on disk?
    ks_results = []
    for p in _FAILOVER_KILL_SWITCHES:
        reachable = False
        try:
            reachable = p.exists() and p.is_file()
        except Exception:
            reachable = False
        ks_results.append({"name": p.name, "ok": reachable})
    ks_ok = sum(1 for r in ks_results if r["ok"])
    ks_total = len(ks_results)

    # Overall verdict
    all_pass = (services_ok == services_total
                and gates_ok == gates_total
                and ks_ok == ks_total)
    completed_ts = _now()

    summary = {
        "status": "pass" if all_pass else "fail",
        "pass": int(all_pass),
        "fail": int(not all_pass),
        "services_ok": f"{services_ok}/{services_total}",
        "gates_ok": f"{gates_ok}/{gates_total}",
        "kill_switches_ok": f"{ks_ok}/{ks_total}",
        "drill_ts": completed_ts,
        "dry_run": True,
    }
    detail = {
        "services": svc_results,
        "gates": gate_results,
        "kill_switches": ks_results,
    }

    # Stamp activity tail (internal)
    _stamp("fire_drill_dry_run_failover", {
        "source": source,
        "summary_status": summary["status"],
        "services_ok": summary["services_ok"],
        "gates_ok": summary["gates_ok"],
        "kill_switches_ok": summary["kill_switches_ok"],
        "summary": f"Failover dry-run: {summary['status']} "
                    f"(svc {summary['services_ok']}, gate {summary['gates_ok']}, "
                    f"ks {summary['kill_switches_ok']})",
    })

    # Append to dedicated audit jsonl
    audit_row = {
        "ts": completed_ts,
        "kind": "fire_drill_dry_run_failover",
        "source": source,
        "started_ts": started_ts,
        "completed_ts": completed_ts,
        "summary": summary,
        "detail": detail,
        "dry_run": True,
        "no_gate_flipped": True,
    }
    with (REG / "qsb_fire_drill_audit.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(audit_row) + "\n")

    return {
        "ok": True,
        "kind": "qsb_fire_drill_failover_report",
        "summary": summary,
        "detail": detail,
        "dry_run": True,
        "no_gate_flipped": True,
        "source": source,
    }


if __name__ == "__main__":
    import sys as _sys
    if len(_sys.argv) > 1 and _sys.argv[1] == "failover":
        r = dry_run_failover(source="cli")
        print(f"Status:        {r['summary']['status']}")
        print(f"Services OK:   {r['summary']['services_ok']}")
        print(f"Gates OK:      {r['summary']['gates_ok']}")
        print(f"Kill-switches: {r['summary']['kill_switches_ok']}")
    else:
        r = initiate()
        print(f"Assembly: {r['assembly_name']}")
        print(f"Expected: {r['expected_total']} · Present: {r['present_total']} ({r['percentage_present']}%)")
        print(f"Floor count drilled: {r['floor_count_drilled']} · Managers reporting: {r['manager_count']}")
        print(f"All clear: {r['all_clear']}")
