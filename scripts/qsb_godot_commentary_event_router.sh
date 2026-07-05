#!/usr/bin/env bash
# qsb_godot_commentary_event_router.sh — speak event when commentary enabled.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
SETTINGS="${ROOT}/data/registries/qsb_godot_commentary_settings.json"
LOG="${ROOT}/data/logs/qsb_godot_commentary_events.jsonl"

mkdir -p "$(dirname "${LOG}")"
ENABLED="$(python3 -c "
import json, os
p = '${SETTINGS}'
print('true' if os.path.exists(p) and json.load(open(p)).get('commentary_enabled') else 'false')
" 2>/dev/null || echo false)"

if [ "${ENABLED}" != "true" ]; then
  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"skipped\",\"reason\":\"commentary disabled\"}" >> "${LOG}"
  exit 0
fi

MSG="${1:-Cockpit running.}"
if command -v spd-say >/dev/null 2>&1; then
  spd-say --rate 10 "${MSG}" &
  echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"spoke\",\"text\":\"${MSG}\"}" >> "${LOG}"
  exit 0
fi
echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"event\":\"silent\",\"reason\":\"no_tts\"}" >> "${LOG}"
exit 1
