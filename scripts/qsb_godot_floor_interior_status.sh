#!/usr/bin/env bash
# qsb_godot_floor_interior_status.sh — concise status printer.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
REG="${ROOT}/data/registries/qsb_floor_interior_master_registry.json"
SCORE="${ROOT}/data/registries/qsb_floor_interior_visual_score.json"
COV="${ROOT}/data/registries/qsb_floor_interior_coverage_audit_latest.json"
SMK="${ROOT}/data/registries/qsb_godot_floor_interior_smoke_test_latest.json"
INT="${ROOT}/data/registries/qsb_floor_interior_interaction_check.json"

echo "============================================================"
echo "  QSB Godot · Every-floor living interior engine · status"
echo "============================================================"
if [ -f "${REG}" ]; then
  python3 -c "
import json
d = json.load(open('${REG}'))
print('  floors registered     :', len(d['floors']))
print('  templates used        :', d.get('templates_used'))
print('  openclaw present count:', d.get('openclaw_present_count'))
print('  inferred (generic)    :', d.get('inferred_count'))
"
fi
for f in COV SMK INT SCORE; do
  v="$(eval echo \$$f)"
  if [ -f "${v}" ]; then
    python3 -c "
import json
d=json.load(open('${v}'))
print(f'  {\"${f}\":21}:', 'ok=' + str(d.get('ok')),
       'score=' + str(d.get('total_score', '-')) if '${f}'=='SCORE' else '')
"
  fi
done
echo
echo "  Run:"
echo "    ./scripts/qsb_floor_interior_coverage_audit.sh"
echo "    ./scripts/qsb_godot_floor_interior_smoke_test.sh"
echo "    ./scripts/qsb_godot_floor_interior_interaction_check.sh"
echo "    ./scripts/qsb_launch_primary_cockpit.sh"
