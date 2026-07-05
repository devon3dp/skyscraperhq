#!/usr/bin/env python3
"""qsb_f47_rooms_backport.py — STAGE A of the per-floor walkable interiors
workstream. Adds layout/render/interactive blocks to each of F47's existing
25 rooms/<room_id>.json files so the cockpit3d renderer can place them in
the 18×18×3 walkable interior data-driven.

Agreed in qsb_claude_wren_bridge.jsonl turns 32-33 on 2026-06-20:
  Q1: schema covers most; ADD interactive block for live-data hooks
  Q2: STAGE A first (back-port) — baseline before renderer rewrite
  Q3: per-floor qwen call for the OTHER 166 floors (STAGE C)

Run:
  python3 tools/qsb_f47_rooms_backport.py [--dry-run]
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "floors/floor_47_executive_operations_department/rooms"

# Position legend (relative to 18×18×3 floor, origin at center):
#   back_*  = -Z (away from camera entry)
#   front_* = +Z (near entry)
#   left_*  = -X
#   right_* = +X
# Zones place a prop AT a sensible offset within their region. Renderer
# resolves zone → (x, z) using room footprint and the floor's W/D.

PALETTE = "embassy_brass_wren_green"  # references _f47Mats in cockpit3d

# Map every F47 room → render spec. Decisions match the hand-coded F47
# block in src/dashboard/static/cockpit3d/index.html (lines 2095-2233):
#   dais / leader_desk / helix / plinth / audit_board / workshop_bench /
#   signoff_desk / kill_switch / letter_archive — keep those positions.
# Other 16 rooms get fresh, distinct spots so they're visible too.
ROOM_LAYOUT = {
    # ── BACK ROW (centerpiece) ───────────────────────────────────────
    "morning_briefing_podium": {
        "zone": "back_center", "offset_x": 0.0, "offset_z": 3.0,
        "footprint_m": [4.0, 3.0], "height_m": 0.4,
        "primary_prop": "dais", "label_text": "MORNING BRIEFING DAIS",
        "glow": False,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_session_diary.md",
                        "display": "scrolling_list", "refresh_seconds": 60},
    },
    "f47_reception_desk": {
        "zone": "back_center_on_dais", "offset_x": 0.0, "offset_z": 3.0,
        "footprint_m": [2.4, 1.0], "height_m": 0.85,
        "primary_prop": "desk", "label_text": "RECEPTION",
        "glow": False, "interactive": {"type": "none"},
    },

    # ── CENTER ───────────────────────────────────────────────────────
    "blueprint_file": {
        "zone": "center", "offset_x": 0.0, "offset_z": 0.0,
        "footprint_m": [1.1, 1.1], "height_m": 2.8,
        "primary_prop": "display", "label_text": "HELIX",
        "glow": True,
        "interactive": {"type": "live_data",
                        "source_path": "data/registries/qsb_helix_state.json",
                        "display": "status_dot", "refresh_seconds": 120},
    },

    # ── FRONT-LEFT ───────────────────────────────────────────────────
    "architect_drawing_table": {
        "zone": "front_left", "offset_x": 2.5, "offset_z": 3.5,
        "footprint_m": [0.6, 0.6], "height_m": 1.1,
        "primary_prop": "plinth", "label_text": "ARCHITECT",
        "glow": False, "interactive": {"type": "none"},
    },
    "graphic_designer_corner": {
        "zone": "front_left", "offset_x": 4.5, "offset_z": 3.5,
        "footprint_m": [0.8, 0.8], "height_m": 1.1,
        "primary_prop": "plinth", "label_text": "GRAPHIC DESIGNER",
        "glow": False, "interactive": {"type": "none"},
    },

    # ── LEFT WALL ────────────────────────────────────────────────────
    "audit_board": {
        "zone": "left_wall", "offset_x": 0.05, "offset_z": 0.0,
        "footprint_m": [4.0, 0.1], "height_m": 2.0,
        "primary_prop": "wall_panel", "label_text": "AUDIT BOARD · recent verdicts",
        "glow": True,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_f47_audit_checks.jsonl",
                        "display": "scrolling_list", "refresh_seconds": 60},
    },
    "health_pulse_panel": {
        "zone": "left_wall", "offset_x": 0.05, "offset_z": -4.5,
        "footprint_m": [2.4, 0.1], "height_m": 1.4,
        "primary_prop": "wall_panel", "label_text": "HEALTH PULSE",
        "glow": True,
        "interactive": {"type": "live_data",
                        "source_path": "data/registries/qsb_tower_health.json",
                        "display": "status_dot", "refresh_seconds": 30},
    },
    "fleet_roster_wall": {
        "zone": "left_wall", "offset_x": 0.05, "offset_z": 4.5,
        "footprint_m": [3.0, 0.1], "height_m": 1.6,
        "primary_prop": "wall_panel", "label_text": "F47 FLEET · 250 operatives",
        "glow": True,
        "interactive": {"type": "count",
                        "source_path": "data/registries/qsb_f47_fleet_roster.json",
                        "display": "big_number", "refresh_seconds": 300},
    },
    "night_mode_panel": {
        "zone": "left_wall", "offset_x": 0.05, "offset_z": -7.5,
        "footprint_m": [1.4, 0.1], "height_m": 1.0,
        "primary_prop": "wall_panel", "label_text": "NIGHT MODE",
        "glow": False,
        "interactive": {"type": "live_data",
                        "source_path": "data/registries/qsb_night_mode.json",
                        "display": "status_dot", "refresh_seconds": 60},
    },

    # ── BACK-LEFT ────────────────────────────────────────────────────
    "workshop_bench": {
        "zone": "back_left", "offset_x": -3.0, "offset_z": -8.0,
        "footprint_m": [4.0, 1.2], "height_m": 0.9,
        "primary_prop": "bench", "label_text": "WORKSHOP BENCH",
        "glow": False,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_code_proposals.jsonl",
                        "display": "scrolling_list", "refresh_seconds": 120},
    },
    "proposals_desk": {
        "zone": "back_left", "offset_x": -6.5, "offset_z": -5.0,
        "footprint_m": [1.6, 0.8], "height_m": 0.85,
        "primary_prop": "desk", "label_text": "PROPOSALS",
        "glow": False,
        "interactive": {"type": "count",
                        "source_path": "data/registries/qsb_code_proposals.jsonl",
                        "display": "big_number", "refresh_seconds": 120},
    },
    "fitter_bench": {
        "zone": "back_left", "offset_x": -4.5, "offset_z": -3.5,
        "footprint_m": [1.6, 0.8], "height_m": 0.85,
        "primary_prop": "bench", "label_text": "FITTER",
        "glow": False, "interactive": {"type": "none"},
    },

    # ── BACK WALL ────────────────────────────────────────────────────
    "wren_letter_archive": {
        "zone": "back_wall", "offset_x": 0.0, "offset_z": -8.95,
        "footprint_m": [2.4, 0.15], "height_m": 2.5,
        "primary_prop": "archive_shelf", "label_text": "WREN LETTER ARCHIVE",
        "glow": True,
        "interactive": {"type": "count",
                        "source_path": "data/registries/qsb_claude_meta_letters.jsonl",
                        "display": "big_number", "refresh_seconds": 600},
    },

    # ── BACK-RIGHT ───────────────────────────────────────────────────
    "signoff_desk": {
        "zone": "back_right", "offset_x": 3.0, "offset_z": -7.5,
        "footprint_m": [2.6, 1.4], "height_m": 0.85,
        "primary_prop": "desk", "label_text": "SIGN-OFF DESK · 3 seals",
        "glow": False,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_claude_signoff_queue.jsonl",
                        "display": "scrolling_list", "refresh_seconds": 30},
    },
    "applier_room": {
        "zone": "back_right", "offset_x": 5.5, "offset_z": -5.0,
        "footprint_m": [1.6, 0.8], "height_m": 0.85,
        "primary_prop": "desk", "label_text": "APPLIER",
        "glow": False,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_code_apply_audit.jsonl",
                        "display": "scrolling_list", "refresh_seconds": 60},
    },
    "sandbox_lab": {
        "zone": "back_right", "offset_x": 6.5, "offset_z": -3.0,
        "footprint_m": [1.4, 1.0], "height_m": 0.9,
        "primary_prop": "bench", "label_text": "SANDBOX",
        "glow": False,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_proposal_sandbox_runs.jsonl",
                        "display": "scrolling_list", "refresh_seconds": 60},
    },

    # ── RIGHT WALL ───────────────────────────────────────────────────
    "kernel_chat_sidecar": {
        "zone": "right_wall", "offset_x": -0.05, "offset_z": -4.0,
        "footprint_m": [2.0, 0.1], "height_m": 1.4,
        "primary_prop": "wall_panel", "label_text": "KERNEL CHAT",
        "glow": True,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_kernel_chat.jsonl",
                        "display": "scrolling_list", "refresh_seconds": 15},
    },
    "decorator_atelier": {
        "zone": "right_wall", "offset_x": -0.05, "offset_z": 0.0,
        "footprint_m": [2.4, 0.1], "height_m": 1.6,
        "primary_prop": "wall_panel", "label_text": "DECORATOR ATELIER",
        "glow": False, "interactive": {"type": "none"},
    },
    "view_from_window": {
        "zone": "right_wall", "offset_x": -0.05, "offset_z": 5.0,
        "footprint_m": [3.6, 0.1], "height_m": 2.0,
        "primary_prop": "wall_panel", "label_text": "WINDOW",
        "glow": True, "interactive": {"type": "none"},
    },

    # ── FRONT-RIGHT ──────────────────────────────────────────────────
    "kill_switch_chamber": {
        "zone": "front_right", "offset_x": 2.0, "offset_z": 3.0,
        "footprint_m": [0.7, 0.7], "height_m": 1.8,
        "primary_prop": "chamber", "label_text": "KILL SWITCH · Ross-only",
        "glow": True,
        "interactive": {"type": "live_data",
                        "source_path": "data/registries/qsb_proposal_autoapply_gate.json",
                        "display": "status_dot", "refresh_seconds": 30},
    },
    "helm_auger_conferring_room": {
        "zone": "front_right", "offset_x": 4.5, "offset_z": 5.5,
        "footprint_m": [2.2, 1.4], "height_m": 0.85,
        "primary_prop": "chair_set", "label_text": "HELM × AUGER",
        "glow": False,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_helm_briefings.jsonl",
                        "display": "scrolling_list", "refresh_seconds": 120},
    },

    # ── FRONT-CENTER (entry-side small props) ────────────────────────
    "visitor_sign_in_book": {
        "zone": "front_center", "offset_x": -0.6, "offset_z": 7.5,
        "footprint_m": [0.6, 0.4], "height_m": 0.95,
        "primary_prop": "desk", "label_text": "SIGN IN",
        "glow": False, "interactive": {"type": "none"},
    },
    "kettle_break_area": {
        "zone": "front_center", "offset_x": -5.5, "offset_z": 5.0,
        "footprint_m": [1.4, 1.0], "height_m": 1.1,
        "primary_prop": "kitchen_line", "label_text": "BREAK",
        "glow": False, "interactive": {"type": "none"},
    },
    "library_shelf": {
        "zone": "front_left", "offset_x": -7.0, "offset_z": 2.5,
        "footprint_m": [2.4, 0.4], "height_m": 2.2,
        "primary_prop": "library_shelf", "label_text": "LIBRARY",
        "glow": False, "interactive": {"type": "none"},
    },
    "worker_forum_corner": {
        "zone": "front_left", "offset_x": -6.5, "offset_z": 0.5,
        "footprint_m": [1.8, 1.4], "height_m": 0.4,
        "primary_prop": "seating", "label_text": "FORUM",
        "glow": False,
        "interactive": {"type": "tail",
                        "source_path": "data/registries/qsb_worker_forum.jsonl",
                        "display": "scrolling_list", "refresh_seconds": 300},
    },
}


def backport(dry_run: bool) -> dict:
    counts = {"updated": 0, "skipped": 0, "missing": 0}
    changes = []
    for room_id, spec in ROOM_LAYOUT.items():
        path = F47 / f"{room_id}.json"
        if not path.exists():
            counts["missing"] += 1
            changes.append((room_id, "MISSING"))
            continue
        doc = json.loads(path.read_text())
        if "layout" in doc and "render" in doc and "interactive" in doc:
            # Already has all three — skip unless we want a force-rewrite.
            counts["skipped"] += 1
            changes.append((room_id, "already-has-blocks"))
            continue
        # Add three new blocks. Preserve existing keys.
        doc["layout"] = {
            "zone": spec["zone"],
            "offset_x": spec["offset_x"],
            "offset_z": spec["offset_z"],
            "footprint_m": spec["footprint_m"],
            "height_m": spec["height_m"],
        }
        doc["render"] = {
            "primary_prop": spec["primary_prop"],
            "palette": PALETTE,
            "label_text": spec["label_text"],
            "glow": spec["glow"],
        }
        doc["interactive"] = spec["interactive"]
        if not dry_run:
            path.write_text(json.dumps(doc, indent=2) + "\n")
        counts["updated"] += 1
        changes.append((room_id, "updated" if not dry_run else "would-update"))

    # Detect any rooms on disk not in our map
    on_disk = {p.stem for p in F47.glob("*.json")}
    not_mapped = sorted(on_disk - set(ROOM_LAYOUT.keys()))
    return {"counts": counts, "changes": changes, "unmapped_on_disk": not_mapped}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = backport(args.dry_run)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
