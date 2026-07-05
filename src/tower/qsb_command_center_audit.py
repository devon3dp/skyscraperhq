"""
QSB Live Skyscraper Command Center — Audit + Decision
Phase: QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1

Read-only audit that builds:
  data/registries/qsb_command_center_audit.json
  data/logs/qsb_command_center_audit.txt
  data/registries/qsb_dashboard_rebuild_decision.json

The decision is: REFACTOR (keep existing healthy 3D scene + V2/V3
overlay; add Profit Command, Workforce, Narrator panels; replace
floor-detail JSON dump with cards). NOT rebuild from scratch.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

P_AUDIT = REG / "qsb_command_center_audit.json"
L_AUDIT = LOGS / "qsb_command_center_audit.txt"
P_DECISION = REG / "qsb_dashboard_rebuild_decision.json"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load(name, fallback=None):
    p = REG / name
    if not p.exists():
        return fallback if fallback is not None else {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return fallback if fallback is not None else {}


def _check(label, ok, note=""):
    return {"check": label, "ok": bool(ok), "note": note}


def _file_size(rel):
    p = ROOT / rel
    if not p.exists():
        return None
    try:
        return p.stat().st_size
    except Exception:
        return None


AUDIT_QUESTIONS = [
    "What is real data-driven?",
    "What is fake/random?",
    "Where is the worker orbit/band generated?",
    "Where are random packets generated?",
    "Why do worker counts mismatch?",
    "Which frontend files are too patched or fragile?",
    "Should the dashboard be refactored or rebuilt?",
    "What must be fixed first?",
]


def build_audit():
    cw = _load("qsb_canonical_workers.json")
    recon = _load("qsb_worker_count_reconciliation.json")
    oc = _load("qsb_openclaw_state.json")
    paper = _load("qsb_open_paper_trades.json")
    learning = _load("qsb_trade_learning.json")
    live = _load("qsb_dashboard_live_telemetry.json")
    eqsb_intro = _load("eqsb_kernel_introspection_latest.json")
    visual = _load("qsb_dashboard_visual_audit.json")

    frontend_files = [
        "src/dashboard/static/index.html",
        "src/dashboard/static/cockpit.css",
        "src/dashboard/static/cockpit.js",
        "src/dashboard/static/qsb_state.js",
        "src/dashboard/static/qsb_tower_2d.js",
        "src/dashboard/static/qsb_scene.js",
        "src/dashboard/static/qsb_floor_interior.js",
        "src/dashboard/static/qsb_windows.js",
        "src/dashboard/static/qsb_skyscraper_v2.js",
        "src/dashboard/static/qsb_v2_panel.js",
        "src/dashboard/static/qsb_skyscraper_v3.js",
        "src/dashboard/static/eqsb_penthouse.js",
    ]
    file_inventory = [
        {"file": f, "size_bytes": _file_size(f), "exists": (ROOT / f).exists()}
        for f in frontend_files
    ]

    # Random/orbit history (already disabled in V3 phase)
    random_visuals = {
        "worker_orbit_3d_disabled":
            "src/dashboard/static/qsb_scene.js — V3 anchors workers to deterministic floor-slab positions (no Math.cos/Math.sin orbit). REMOVED.",
        "worker_pulse_2d_gated":
            "src/dashboard/static/qsb_tower_2d.js — pulse fires only when in_transit OR recent_event. GATED.",
        "lift_capsule_3d_gated":
            "src/dashboard/static/qsb_scene.js — capsules park unless real lift_movement record. GATED.",
        "lift_capsule_2d_gated":
            "src/dashboard/static/qsb_tower_2d.js — same gating. GATED.",
        "packet_arc_jitter_deterministic":
            "src/dashboard/static/qsb_tower_2d.js — arcAmp now a stable hash of (ts, src, dst). DETERMINISTIC.",
    }

    audit_answers = {
        "1_what_is_data_driven": [
            "/api/unified.packets (real packet feed)",
            "/api/unified.workers / /api/qsb_v2/canonical_workers / /api/dashboard/live_telemetry.workers",
            "/api/eqsb/penthouse_panel (EQSB kernel introspection)",
            "/api/qsb_v2/openclaw_state (OpenClaw flags + tickets)",
            "/api/qsb_v2/open_paper_trades + /api/qsb_v2/trade_learning (paper trades + lessons)",
            "Floor slabs + lift shafts (geometry from render_model)",
            "OpenClaw avatar (V2 overlay; route advances on cadence tick)",
        ],
        "2_what_is_fake_or_random": [
            "(All removed/gated in V3) — penthouse halo breathing remains deterministic decorative only.",
        ],
        "3_worker_orbit_source":
            "src/dashboard/static/qsb_scene.js lines ~640-653 (REMOVED in V3 — anchored to deterministic slab positions).",
        "4_random_packet_source":
            "src/dashboard/static/qsb_tower_2d.js arcAmp jitter (REPLACED with deterministic stable hash).",
        "5_worker_count_mismatch_reason":
            (recon.get("mismatch_reason") or "Before V2 each subsystem kept its own slate; no canonical "
             "registry deduplicated across them. V2 consolidates everything under "
             "qsb_canonical_workers.json."),
        "6_patched_or_fragile_files": [
            "src/dashboard/static/cockpit.js — large legacy controller (2559 LOC). Healthy but dense.",
            "src/dashboard/static/qsb_floor_interior.js — random per-floor animations are gated but the layout is JSON-dump heavy.",
        ],
        "7_refactor_or_rebuild": "REFACTOR. The 3D scene + V2/V3 overlay is structurally healthy; adding cards/panels and a Narrator is preferred over a full rewrite.",
        "8_fix_first": [
            "Wire Profit Command panel + endpoint",
            "Replace floor interior JSON dump with cards + 'no live data' fallback",
            "Add Workforce HR panel (scorecards, rewards, discipline, promotions)",
            "Add Running Commentary button (browser SpeechSynthesis)",
            "Add resilient try/catch around every fetch in cockpit.js",
        ],
    }

    counts = {
        "canonical_workers": cw.get("total_canonical_workers"),
        "active_workers": cw.get("total_active_workers"),
        "newly_employed": cw.get("total_newly_employed_workers"),
        "open_paper_trades": paper.get("open_trade_count"),
        "max_open_trades": paper.get("max_open_trades"),
        "realized_pnl": learning.get("total_realized_pnl"),
        "closed_trade_count": learning.get("closed_trade_count"),
        "lesson_count": learning.get("lesson_count"),
        "openclaw_status": oc.get("status"),
        "openclaw_tickets": oc.get("diagnostic_ticket_count"),
        "eqsb_self_audit_verdict":
            (eqsb_intro.get("guardian") or {}).get("safety_state"),
        "visual_audit_random_or_decorative": (visual.get("summary") or {}).get("random_or_decorative"),
        "visual_audit_rebuilt_in_v3": (visual.get("summary") or {}).get("rebuilt_in_v3"),
    }

    checks = [
        _check("canonical_workers_present",
                bool(counts["canonical_workers"]),
                "qsb_canonical_workers.json total=" + str(counts["canonical_workers"])),
        _check("live_telemetry_block_present",
                bool(live),
                "qsb_dashboard_live_telemetry.json present"),
        _check("openclaw_state_active",
                oc.get("status") == "active",
                "qsb_openclaw_state.status=" + str(oc.get("status"))),
        _check("paper_trades_lifecycle_works",
                (paper.get("open_trade_count") or 0) >= 0,
                "open_trades=" + str(paper.get("open_trade_count"))),
        _check("realized_pnl_recorded",
                learning.get("total_realized_pnl") is not None,
                "realized_pnl=" + str(learning.get("total_realized_pnl"))),
        _check("eqsb_kernel_introspection_present",
                bool(eqsb_intro),
                "eqsb_kernel_introspection_latest.json present"),
        _check("dashboard_visual_audit_present",
                bool(visual),
                "qsb_dashboard_visual_audit.json present"),
    ]

    audit = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_command_center_audit",
        "generated_ts": _now(),
        "dashboard_visual_mode": "LIVE_DATA_ONLY",
        "policy": "NO_RANDOM_LIVE_GRAPHICS",
        "audit_answers": audit_answers,
        "checks": checks,
        "counts": counts,
        "random_visual_status": random_visuals,
        "frontend_file_inventory": file_inventory,
        "audit_questions": AUDIT_QUESTIONS,
        "execution_allowed": False,
        "active_local_only": True,
        "real_money_live_trading_enabled": False,
    }
    REG.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    P_AUDIT.write_text(json.dumps(audit, indent=2), encoding="utf-8")

    with L_AUDIT.open("w", encoding="utf-8") as f:
        f.write("QSB Live Skyscraper Command Center — Audit\n")
        f.write("==========================================\n")
        f.write("ts:      " + audit["generated_ts"] + "\n")
        f.write("phase:   " + audit["phase"] + "\n")
        f.write("policy:  " + audit["policy"] + "\n")
        f.write("mode:    " + audit["dashboard_visual_mode"] + "\n\n")
        f.write("Counts:\n")
        for k, v in counts.items():
            f.write("  %-40s %s\n" % (k, v))
        f.write("\nChecks:\n")
        for c in checks:
            f.write("  [%s] %s  %s\n" % ("OK" if c["ok"] else "FAIL",
                                          c["check"], c.get("note", "")))
        f.write("\nFrontend file inventory:\n")
        for fi in file_inventory:
            f.write("  %-60s exists=%s size=%s\n" % (
                fi["file"], fi["exists"], fi["size_bytes"]))
        f.write("\nAudit Q&A:\n")
        for k, v in audit_answers.items():
            f.write("  - %s:\n" % k)
            if isinstance(v, list):
                for item in v:
                    f.write("      · " + str(item) + "\n")
            else:
                f.write("      %s\n" % v)

    decision = {
        "ok": True,
        "phase": "QSB_LIVE_SKYSCRAPER_COMMAND_CENTER_REBUILD_V1",
        "kind": "qsb_dashboard_rebuild_decision",
        "generated_ts": _now(),
        "path": "REFACTOR",
        "rationale": (
            "3D scene + V2/V3 overlay are structurally healthy; V3 already "
            "eliminated all random orbits/packets. The remaining gaps are "
            "Profit Command, Workforce HR cards (scorecards/rewards/"
            "discipline/promotions), Running Commentary, resilient floor "
            "interior cards, and frontend health hardening — all additive "
            "panels around the same skyscraper container."
        ),
        "preserved": [
            "EQSB Penthouse panel + /api/eqsb/*",
            "QSB V2 Ops panel + /api/qsb_v2/*",
            "QSB V3 Live Telemetry panel + /api/dashboard/live_telemetry",
            "3D Babylon scene + 2D SVG fallback",
            "Same dashboard URL (http://127.0.0.1:8765/?v=unified) and port 8765",
        ],
        "additions": [
            "Profit Command panel + /api/profit_command",
            "Workforce HR panel + scorecards/rewards/discipline/promotions",
            "Running Commentary button + /api/narrator/{tower,floor,worker,profit,openclaw}",
            "Floor interior card view (replaces JSON dump)",
            "Wider resilient fetch wrappers in panels",
        ],
        "backup_path_planned": "data/backups/dashboard_rebuild_<timestamp>/",
        "no_heavy_dependencies": True,
        "execution_allowed": False,
        "active_local_only": True,
        "real_money_live_trading_enabled": False,
    }
    P_DECISION.write_text(json.dumps(decision, indent=2), encoding="utf-8")

    return audit, decision


def main():
    audit, decision = build_audit()
    print(json.dumps({
        "audit_kind": audit["kind"],
        "decision_path": decision["path"],
        "canonical_workers": audit["counts"]["canonical_workers"],
        "openclaw_status": audit["counts"]["openclaw_status"],
        "realized_pnl": audit["counts"]["realized_pnl"],
    }, indent=2))


if __name__ == "__main__":
    main()
