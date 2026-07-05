#!/usr/bin/env bash
# Runs ONE visible UE build pass via the Python scripts.
# Strategy:
#   - If UE editor is RUNNING, push the Python script in via -ExecutePythonScript
#     would require restart. Instead, write each script + invoke via console
#     (Window > Python tab) — we document the recipe here for the user.
#   - If UE editor is DOWN, launch with -ExecutePythonScript=<script>.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y%m%dT%H%M%SZ)
SCRIPT="${1:-scripts/unreal/python/qsb_unreal_build_skyscraper_pass.py}"
[[ -f "$SCRIPT" ]] || { echo "script not found: $SCRIPT"; exit 1; }
LOG=data/logs/unreal_build_pass_${TS}.log
mkdir -p data/logs

if pgrep -f 'UnrealEditor.*QSB_Skyscraper.uproject' >/dev/null; then
  cat <<EOF
editor is RUNNING. To execute Python in the LIVE session:
  1) Window → Output Log → switch to Python tab
  2) Run: exec(open('$SCRIPT').read())
OR restart-with-exec (loses unsaved state):
  ./scripts/qsb_team_daemon_stop.sh   # if daemon was holding things
  pkill -f 'UnrealEditor.*QSB_Skyscraper'
  PYSCRIPT='$SCRIPT' ./scripts/unreal/qsb_unreal_open_editor.sh
EOF
  exit 2
fi

PYSCRIPT="$SCRIPT" ./scripts/unreal/qsb_unreal_open_editor.sh | tee "$LOG"
