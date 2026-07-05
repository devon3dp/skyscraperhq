#!/usr/bin/env bash
# EQSB last upgrade report: prints latest summary + change diff.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
python3 -c "
import json
last = json.load(open('data/registries/eqsb_last_claude_change_summary.json'))
changes = json.load(open('data/registries/eqsb_phase_changes_latest.json'))
print('latest_phase:', last.get('phase'))
print('summary:', last.get('summary'))
print('files_created (count):', len(changes.get('files_created') or []))
print('files_modified (count):', len(changes.get('files_modified') or []))
print('files_deleted (count):', len(changes.get('files_deleted') or []))
print()
print('files_created (first 8):')
for f in (changes.get('files_created') or [])[:8]:
    print('  -', f)
print('files_modified (first 12):')
for f in (changes.get('files_modified') or [])[:12]:
    print('  -', f)
"
