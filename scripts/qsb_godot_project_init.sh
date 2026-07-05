#!/usr/bin/env bash
# QSB Godot project init — sanity-check + re-emit project.godot if missing.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1

PROJ=native_cockpit/godot_qsb
mkdir -p "$PROJ/scenes" "$PROJ/scripts" "$PROJ/assets" "$PROJ/exports" "$PROJ/logs"

if [ ! -f "$PROJ/project.godot" ]; then
  cat > "$PROJ/project.godot" <<'P'
config_version=5
[application]
config/name="QSB Godot Native Cockpit"
run/main_scene="res://scenes/Main.tscn"
[autoload]
Telemetry="*res://scripts/TelemetryBridge.gd"
[rendering]
renderer/rendering_method="forward_plus"
P
  echo "project.godot recreated"
fi
echo "ok: $(ls $PROJ/scenes/*.tscn | wc -l) scenes, $(ls $PROJ/scripts/*.gd | wc -l) scripts"
