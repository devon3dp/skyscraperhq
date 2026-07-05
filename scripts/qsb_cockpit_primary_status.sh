#!/usr/bin/env bash
# qsb_cockpit_primary_status.sh — one-liner: what is the primary cockpit?
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
echo "============================================================"
echo "  QSB Cockpit · Primary Status"
echo "  Phase: QSB_GODOT_NATIVE_COCKPIT_PRIMARY_GRAPHICS_ENGINE_SWITCH_V1"
echo "============================================================"
echo
echo "PRIMARY (professional graphics engine):"
echo "  engine:          godot"
echo "  version:         4.6.1 stable mono"
echo "  role:            primary_professional_graphics_engine"
echo "  project_path:    /home/ross/qsb_godot_native_cockpit"
echo "  qsb_path:        native_cockpit/godot_qsb (symlink)"
echo "  launch_command:  ./scripts/qsb_godot_run.sh"
echo
echo "LEGACY FALLBACK (browser dashboard):"
echo "  url:             http://127.0.0.1:8765/?v=unified"
echo "  role:            legacy_fallback_dashboard"
echo "  do_not_use_as_visual_success: true"
echo
echo "ADMIN FALLBACK (PyQt):"
echo "  run_script:      scripts/qsb_native_cockpit_run.sh"
echo "  role:            fallback_admin_only"
echo "  do_not_use_as_visual_success: true"
echo
echo "To open the primary cockpit:"
echo "  cd $ROOT && ./scripts/qsb_launch_primary_cockpit.sh"
echo
