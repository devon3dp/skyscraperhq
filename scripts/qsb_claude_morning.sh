#!/usr/bin/env bash
# qsb_claude_morning.sh — the first thing a new session should run.
# Renders identity, mood, inbox, aphorisms, one heavy question, recent
# meta-letters, recent chat, F23 bridge, and the daily synthesis. ONE view.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
python3 - <<'PY'
import sys; sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1")
from src.tower.model_floors.claude_floor.morning_briefing import render
print(render())
PY
