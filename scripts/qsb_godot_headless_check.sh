#!/usr/bin/env bash
# QSB Godot headless check — confirms Godot parses the project cleanly.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1

GODOT_BIN=native_cockpit/bin/qsb-godot
PROJ=native_cockpit/godot_qsb

if [ ! -x "$GODOT_BIN" ]; then
  echo "godot wrapper missing — run installer"; exit 2
fi
if [ ! -f "$PROJ/project.godot" ]; then
  echo "project.godot missing"; exit 3
fi
cd "$PROJ"
out=$(timeout 25 "../../$GODOT_BIN" --headless --quit 2>&1)
ec=$?
echo "$out" | head -20
echo "exit_code=$ec"
[ $ec -eq 0 ]
