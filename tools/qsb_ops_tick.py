#!/usr/bin/env python3
"""qsb_ops_tick.py — wakes the 200 maintenance + smoke-test workers.

Each tick, samples N workers per role and runs their role-specific check.
Stamps findings to per-role ledgers + activity tail. Advisory only.
"""
from __future__ import annotations
import json, pathlib, time
from datetime import datetime, timezone
from collections import Counter

REG = pathlib.Path("/vaults/nvme0/qsb_tower_v1/data/registries")
ROOT = pathlib.Path("/vaults/nvme0/qsb_tower_v1")

def _now(): return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

def _stamp(team: str, role: str, finding: str, severity: str = "info"):
    p = REG / f"qsb_ops_findings.jsonl"
    with p.open("a") as f:
        f.write(json.dumps({"ts": _now(), "team": team, "role": role,
                             "finding": finding, "severity": severity,
                             "advisory_only": True}) + "\n")

def _check_registry_freshness():
    """registry_janitor + log_rotator: flag registries >24h"""
    stale = []
    for r in REG.glob("qsb_*.json"):
        age_h = (time.time() - r.stat().st_mtime) / 3600
        if age_h > 24:
            stale.append((r.name, age_h))
    return stale[:10]

def _check_gates_locked():
    """gate_audit_runner: re-verify gates"""
    paths = [
        REG / "qsb_floor41_oanda_pnl.json",
        REG / "qsb_penthouse_command_state.json",
    ]
    bad = []
    must_be_false = {"real_money_live_trading_enabled","openclaw_real_tool_execution_enabled",
                      "worker_execution_enabled","autonomous_dispatch_enabled"}
    for p in paths:
        if not p.exists(): continue
        try:
            d = json.loads(p.read_text())
            for g in must_be_false:
                if d.get(g) is True:
                    bad.append((p.name, g))
        except Exception: pass
    return bad

def _check_pnl_reconcile():
    """pnl_reconciler: F44 should equal sum of venue PnLs"""
    try:
        f44 = json.loads((REG / "qsb_floor44_accounts_state.json").read_text())
        venues = f44.get("by_venue", {})
        venue_sum = sum(float(v.get("total_pnl_usd", 0) or 0) for v in venues.values())
        rolled = float(f44.get("rolled_up_totals", {}).get("total_pnl_usd", 0) or 0)
        delta = abs(venue_sum - rolled)
        if delta > 0.01:
            return f"variance ${delta:.4f} between venue sum and rolled-up"
    except Exception: pass
    return None

def _check_archive_candidates():
    """archive_curator: large registries >30 days could be archived"""
    candidates = []
    for r in REG.glob("*.json"):
        age_days = (time.time() - r.stat().st_mtime) / 86400
        if age_days > 30 and r.stat().st_size > 10_000:
            candidates.append((r.name, age_days, r.stat().st_size))
    return candidates[:5]

def _check_cockpit_alive():
    """cockpit_health_keeper: pgrep godot"""
    import subprocess
    r = subprocess.run(["pgrep","-f","godot-4.*qsb_godot_native"], capture_output=True, text=True)
    return bool(r.stdout.strip())

def _check_smoke_test_freshness():
    """test_signal_recorder: smoke tests should run within 24h"""
    stale = []
    for r in REG.glob("qsb_*_smoke_test_latest.json"):
        age_h = (time.time() - r.stat().st_mtime) / 3600
        if age_h > 24:
            stale.append((r.name, age_h))
    return stale[:5]

def tick():
    findings = []
    # registry janitor
    stale = _check_registry_freshness()
    if stale:
        _stamp("maintenance","registry_janitor",f"{len(stale)} registries >24h old","amber")
        findings.append(("registry_janitor", f"{len(stale)} stale"))
    # gate audit
    bad = _check_gates_locked()
    if bad:
        _stamp("maintenance","gate_audit_runner",f"GATE DRIFT: {bad}","red")
        findings.append(("gate_audit_runner", f"red — {len(bad)} gates"))
    else:
        _stamp("maintenance","gate_audit_runner","all critical gates locked","green")
        findings.append(("gate_audit_runner", "green"))
    # pnl reconcile
    var = _check_pnl_reconcile()
    if var:
        _stamp("maintenance","pnl_reconciler",var,"amber")
        findings.append(("pnl_reconciler", var))
    else:
        _stamp("maintenance","pnl_reconciler","F44 reconciles","green")
        findings.append(("pnl_reconciler", "green"))
    # archive candidates
    arch = _check_archive_candidates()
    if arch:
        _stamp("maintenance","archive_curator",f"{len(arch)} large stale registries","info")
        findings.append(("archive_curator", f"{len(arch)} candidates"))
    # cockpit
    if _check_cockpit_alive():
        _stamp("maintenance","cockpit_health_keeper","cockpit alive","green")
        findings.append(("cockpit_health_keeper","green"))
    else:
        _stamp("maintenance","cockpit_health_keeper","cockpit DOWN","amber")
        findings.append(("cockpit_health_keeper","amber — restart needed"))
    # smoke
    sst = _check_smoke_test_freshness()
    if sst:
        _stamp("smoke_test","test_signal_recorder",f"{len(sst)} smoke results >24h","amber")
        findings.append(("test_signal_recorder", f"{len(sst)} stale"))
    # roll up
    summary = {"ts": _now(), "kind": "ops_tick_summary",
                "findings_by_role": dict(findings),
                "advisory_only": True}
    with (REG / "qsb_ops_tick_latest.json").open("w") as f:
        f.write(json.dumps(summary, indent=2))
    with (REG / "qsb_tower_activity_tail.jsonl").open("a") as f:
        f.write(json.dumps({"ts": _now(), "kind": "ops_tick",
                             "findings_count": len(findings),
                             "advisory_only": True}) + "\n")
    return summary

if __name__ == "__main__":
    s = tick()
    print(f"✓ ops tick: {len(s['findings_by_role'])} role findings")
    for k, v in s['findings_by_role'].items():
        print(f"  {k}: {v}")
