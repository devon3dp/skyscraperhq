#!/usr/bin/env bash
set -Eeuo pipefail

QSB_ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
PROJECT="/home/ross/qsb_godot_native_cockpit"

GODOT_BIN="$QSB_ROOT/native_cockpit/bin/qsb-godot"
if [ ! -x "$GODOT_BIN" ]; then
  if command -v godot4 >/dev/null 2>&1; then GODOT_BIN="godot4";
  elif command -v godot-4 >/dev/null 2>&1; then GODOT_BIN="godot-4";
  elif [ -x /snap/bin/godot-4 ]; then GODOT_BIN="/snap/bin/godot-4";
  elif command -v godot >/dev/null 2>&1; then GODOT_BIN="godot";
  else echo "ERROR: Godot binary not found"; exit 1; fi
fi

echo "Launching QSB Godot Native Cockpit"
echo "Project: $PROJECT"
echo "Godot: $GODOT_BIN"

test -f "$PROJECT/project.godot" || { echo "ERROR: project.godot missing"; exit 1; }
test -f "$PROJECT/scenes/Main.tscn" || { echo "ERROR: Main.tscn missing"; exit 1; }

cd "$PROJECT"
exec "$GODOT_BIN" --path "$PROJECT"
