#!/usr/bin/env bash
# qsb_godot_professional_upgrade_status.sh — reports the 25-gate score.
# Reads qsb_godot_primary_professional_gates.json + _score.json
# Must NOT use browser dashboard as proof of cockpit success.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
GATES="${ROOT}/data/registries/qsb_godot_primary_professional_gates.json"
SCORE="${ROOT}/data/registries/qsb_godot_primary_professional_score.json"

echo "============================================================"
echo "  QSB Godot · Professional Upgrade Status"
echo "  Source of truth: ${GATES}"
echo "============================================================"
echo

if [ ! -f "${GATES}" ]; then
  echo "ERROR: gates registry missing — run the upgrade phase first."
  exit 2
fi

python3 -c "
import json, sys
gates = json.load(open('${GATES}'))
score = json.load(open('${SCORE}')) if '${SCORE}' and __import__('os').path.exists('${SCORE}') else {}
passed = [g for g in gates.get('gates', []) if g.get('passed')]
total  = gates.get('gates', [])
print(f'  Gates passed: {len(passed)} / {len(total)}')
print(f'  Score:        {score.get(\"score\", \"(unknown)\")}/100')
print(f'  Verdict:      {score.get(\"verdict\", \"(unknown)\")}')
print()
print('  Individual gates:')
for g in total:
    mark = '✓' if g.get('passed') else '✗'
    print(f'    [{mark}] {g.get(\"id\"):3} · {g.get(\"name\")}')
    if not g.get('passed') and g.get('notes'):
        print(f'         → {g.get(\"notes\")}')
print()
print('NOTE: This score is ONLY about the Godot cockpit.')
print('      Browser dashboard improvements do not raise this score.')
"
