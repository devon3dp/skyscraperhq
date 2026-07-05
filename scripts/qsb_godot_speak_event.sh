#!/usr/bin/env bash
# qsb_godot_speak_event.sh — speak the most recent ticker event line.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
LOG="${ROOT}/data/logs/cognitive/thought_trace.jsonl"

LAST=""
if [ -f "${LOG}" ]; then
  LAST="$(tail -1 "${LOG}" 2>/dev/null | python3 -c "import sys, json; d=json.loads(sys.stdin.read()); print(d.get('text',''))" 2>/dev/null || true)"
fi
[ -z "${LAST}" ] && LAST="Cockpit running. No recent events."
exec "${ROOT}/scripts/qsb_godot_audio_test_voice.sh" "Event: ${LAST}"
