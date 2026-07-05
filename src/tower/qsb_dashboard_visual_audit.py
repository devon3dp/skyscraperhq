"""
QSB Tower V3 — Dashboard Visual Audit
Phase: QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2

Documents every frontend visual element with:
  * source (registry / decorative / random)
  * data_driven (true/false)
  * action (kept / gated / removed / rebuilt)

Read-only. Writes:
  data/registries/qsb_dashboard_visual_audit.json
  data/logs/qsb_dashboard_visual_audit.txt
"""

from datetime import datetime, timezone
from pathlib import Path
import json

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"

P_AUDIT = REG / "qsb_dashboard_visual_audit.json"
L_AUDIT = LOGS / "qsb_dashboard_visual_audit.txt"


def _now():
    return datetime.now(timezone.utc).isoformat()


VISUAL_ELEMENTS = [
    {
        "element": "Babylon worker orbit (3D scene)",
        "files": ["src/dashboard/static/qsb_scene.js"],
        "lines": "640-653",
        "data_driven_before_v3": False,
        "source_before": "Math.cos/Math.sin orbit around home floor — visual only",
        "action_in_v3": "REBUILT: workers anchored to deterministic XZ position on assigned floor slab (stable hash of worker_id). No orbiting. Pulse animation only when worker.in_transit=true.",
    },
    {
        "element": "SVG worker pulse (qsb-tower-svg)",
        "files": ["src/dashboard/static/qsb_tower_2d.js"],
        "lines": "777-782",
        "data_driven_before_v3": False,
        "source_before": "Math.sin(now*2.5+phase) cosmetic radius pulse",
        "action_in_v3": "GATED: pulse only fires when worker.in_transit=true or worker.last_event_age_seconds < 30; default radius otherwise.",
    },
    {
        "element": "Babylon lift capsule oscillation",
        "files": ["src/dashboard/static/qsb_scene.js"],
        "lines": "632-638",
        "data_driven_before_v3": False,
        "source_before": "Math.sin(now*speed+phase) up/down across shaft range",
        "action_in_v3": "REBUILT: capsules park at parked_y (default mid-shaft) unless a real lift_movement record is active in qsb_dashboard_live_telemetry.lift_movements; then capsule animates from source floor -> target floor over its dwell_ms.",
    },
    {
        "element": "SVG lift capsule oscillation",
        "files": ["src/dashboard/static/qsb_tower_2d.js"],
        "lines": "761-774",
        "data_driven_before_v3": False,
        "source_before": "Math.sin(now*speed+phase) up/down across shaft range",
        "action_in_v3": "GATED: same as Babylon; capsules render at parked position unless live telemetry reports active movement.",
    },
    {
        "element": "SVG packet arc amplitude jitter",
        "files": ["src/dashboard/static/qsb_tower_2d.js"],
        "lines": "750-751",
        "data_driven_before_v3": False,
        "source_before": "arcAmp = 30 + Math.random()*22 — purely visual",
        "action_in_v3": "KEPT: arc amplitude derives from stable hash of packet.lift_id/title so the same packet draws the same curve every time (deterministic).",
    },
    {
        "element": "Packet body data (state.packets[])",
        "files": ["src/dashboard/static/qsb_tower_2d.js",
                   "src/dashboard/static/qsb_scene.js"],
        "data_driven_before_v3": True,
        "source_before": "/api/unified.packets[] — real packet routes",
        "action_in_v3": "KEPT: packet spawning remains data-driven; only the visual jitter switched to deterministic.",
    },
    {
        "element": "Worker placement on home floor",
        "files": ["src/dashboard/static/qsb_tower_2d.js"],
        "lines": "650-674",
        "data_driven_before_v3": True,
        "source_before": "state.workers[].home_floor",
        "action_in_v3": "KEPT + EXTENDED: workers now placed using qsb_canonical_workers + qsb_dashboard_live_telemetry; absence of an assigned floor renders worker on floor_45 (Recruitment) with a 'unassigned' badge.",
    },
    {
        "element": "Background starfield (SVG)",
        "files": ["src/dashboard/static/qsb_tower_2d.js"],
        "lines": "262-269",
        "data_driven_before_v3": False,
        "source_before": "110 stars from Math.random()",
        "action_in_v3": "KEPT (decorative only): never presented as system activity. Marked DETERMINISTIC_DECOR_ONLY in code comment.",
    },
    {
        "element": "Penthouse halo pulse",
        "files": ["src/dashboard/static/qsb_scene.js"],
        "lines": "668-677",
        "data_driven_before_v3": False,
        "source_before": "Math.sin(now) pulse — purely visual breathing",
        "action_in_v3": "KEPT (decorative breathing only): represents kernel heartbeat — explicitly tied to eqsb_cadence_state.tick_count via period adjustment, but is honestly a decorative breathing animation.",
    },
    {
        "element": "OpenClaw avatar V2 movement",
        "files": ["src/dashboard/static/qsb_skyscraper_v2.js"],
        "lines": "moveOpenClaw()",
        "data_driven_before_v3": True,
        "source_before": "qsb_openclaw_state.supervised_floors — rotates through real list",
        "action_in_v3": "KEPT + EXTENDED: now reads qsb_openclaw_state.current_route_floor (from live telemetry); if no active route, OpenClaw parks at floor_53 instead of rotating.",
    },
    {
        "element": "V2 HUD telemetry (open trades, PnL, workers)",
        "files": ["src/dashboard/static/qsb_skyscraper_v2.js"],
        "data_driven_before_v3": True,
        "source_before": "/api/qsb_v2/penthouse_combined",
        "action_in_v3": "KEPT: extended to read /api/dashboard/live_telemetry which composes the same fields.",
    },
    {
        "element": "Demo mode (?render_test=1)",
        "files": ["src/dashboard/static/qsb_state.js"],
        "lines": "117-170",
        "data_driven_before_v3": False,
        "source_before": "Synthetic state generator labelled render_test_only — only active with URL flag",
        "action_in_v3": "KEPT: synthetic state remains gated to render_test=1; explicit DEMO label added at the top of the cockpit header when active.",
    },
    {
        "element": "Floor interior packet flow (qsb_floor_interior.js)",
        "files": ["src/dashboard/static/qsb_floor_interior.js"],
        "lines": "1162-1258",
        "data_driven_before_v3": False,
        "source_before": "Random worker dots wandering between sections; randomized packet curves",
        "action_in_v3": "GATED: interior animation only runs when the floor has at least one record in qsb_dashboard_live_telemetry.events with floor=N; otherwise interior shows static layout with 'No live data for this floor' badge.",
    },
]


def build():
    summary = {
        "total_elements_audited": len(VISUAL_ELEMENTS),
        "data_driven_before_v3":   sum(1 for e in VISUAL_ELEMENTS if e["data_driven_before_v3"]),
        "random_or_decorative":    sum(1 for e in VISUAL_ELEMENTS if not e["data_driven_before_v3"]),
        "rebuilt_in_v3":           sum(1 for e in VISUAL_ELEMENTS if "REBUILT" in e["action_in_v3"]),
        "gated_in_v3":             sum(1 for e in VISUAL_ELEMENTS if "GATED" in e["action_in_v3"]),
        "kept_decorative":         sum(1 for e in VISUAL_ELEMENTS if "decorative" in e["action_in_v3"].lower() and "KEPT" in e["action_in_v3"]),
    }
    payload = {
        "ok": True,
        "phase": "QSB_DASHBOARD_DATA_DRIVEN_SKYSCRAPER_REBUILD_V2",
        "kind": "qsb_dashboard_visual_audit",
        "generated_ts": _now(),
        "policy": "NO_RANDOM_LIVE_GRAPHICS",
        "dashboard_visual_mode": "LIVE_DATA_ONLY",
        "summary": summary,
        "elements": VISUAL_ELEMENTS,
        "execution_allowed": False,
        "active_local_only": True,
        "real_money_live_trading_enabled": False,
    }
    REG.mkdir(parents=True, exist_ok=True)
    LOGS.mkdir(parents=True, exist_ok=True)
    P_AUDIT.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    with L_AUDIT.open("w", encoding="utf-8") as f:
        f.write("QSB Dashboard Visual Audit\n")
        f.write("==========================\n")
        f.write("ts:                       " + payload["generated_ts"] + "\n")
        f.write("phase:                    " + payload["phase"] + "\n")
        f.write("policy:                   " + payload["policy"] + "\n")
        f.write("dashboard_visual_mode:    " + payload["dashboard_visual_mode"] + "\n\n")
        f.write("Summary:\n")
        for k, v in summary.items():
            f.write("  %-32s %s\n" % (k, v))
        f.write("\nElements:\n")
        for e in VISUAL_ELEMENTS:
            f.write("  - %s\n" % e["element"])
            f.write("      data_driven_before_v3: %s\n" % e["data_driven_before_v3"])
            f.write("      source_before:         %s\n" % e["source_before"])
            f.write("      action_in_v3:          %s\n" % e["action_in_v3"])
    return payload


def main():
    print(json.dumps(build(), indent=2))


if __name__ == "__main__":
    main()
