#!/usr/bin/env bash
# qsb_launch_primary_cockpit.sh — launches the PRIMARY cockpit (Godot).
# Does not open browser dashboard. Fails clearly if Godot project missing.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"

echo "============================================================"
echo "  QSB · Launching PRIMARY cockpit (Godot)"
echo "============================================================"

# Pre-flight: project files
if [ ! -f "${PROJECT}/project.godot" ]; then
  echo "ERROR: Godot project missing at ${PROJECT}/project.godot"
  echo "  Restore the project or recreate it before launching."
  exit 2
fi
if [ ! -f "${PROJECT}/scenes/Main.tscn" ]; then
  echo "ERROR: Main.tscn missing at ${PROJECT}/scenes/Main.tscn"
  exit 2
fi
if [ ! -f "${PROJECT}/scripts/Main.gd" ]; then
  echo "ERROR: Main.gd missing at ${PROJECT}/scripts/Main.gd"
  exit 2
fi

# Pre-flight: Godot binary
GODOT_BIN=""
if [ -x "${ROOT}/native_cockpit/bin/qsb-godot" ]; then
  GODOT_BIN="${ROOT}/native_cockpit/bin/qsb-godot"
elif command -v godot4 >/dev/null 2>&1; then
  GODOT_BIN="godot4"
elif [ -x /snap/bin/godot-4 ]; then
  GODOT_BIN="/snap/bin/godot-4"
elif command -v godot >/dev/null 2>&1; then
  GODOT_BIN="godot"
else
  echo "ERROR: Godot binary not found. Install godot-4 via snap or apt."
  exit 3
fi

echo "  project: ${PROJECT}"
echo "  binary:  ${GODOT_BIN}"
echo
echo "  This is the PRIMARY visual cockpit."
echo "  Browser dashboard at :8765 is legacy fallback only."
echo "  PyQt admin shell is admin fallback only."
echo
echo "  Launching..."
echo

exec "${GODOT_BIN}" --path "${PROJECT}"
