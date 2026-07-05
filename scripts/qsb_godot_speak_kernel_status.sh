#!/usr/bin/env bash
# qsb_godot_speak_kernel_status.sh — speak the cognitive headline.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
BRIEF="${ROOT}/data/registries/cognitive/cognitive_morning_briefing.json"

HEADLINE="Kernel local only. Advisory only. All execution gates closed."
if [ -f "${BRIEF}" ]; then
  CAND="$(python3 -c "import json; d=json.load(open('${BRIEF}')); print(d.get('headline',''))" 2>/dev/null || true)"
  [ -n "${CAND}" ] && HEADLINE="${CAND}"
fi
exec "${ROOT}/scripts/qsb_godot_audio_test_voice.sh" "${HEADLINE}"
