#!/usr/bin/env bash
# Stage 12 — run ALL smoke tests + collate
cd /vaults/nvme0/qsb_tower_v1
echo "═══════════════ UE5 PROFESSIONAL DASHBOARD SUITE ═══════════════"
TOTAL_PASS=0; TOTAL_FAIL=0
for t in tower_structure_audit hud_design world_design data_bridge professional_roadmap; do
  echo ""
  echo "--- $t ---"
  if bash scripts/qsb_unreal_${t}_smoke_test.sh; then : ; fi
  R=$?
  if [ "$R" = "0" ]; then TOTAL_PASS=$((TOTAL_PASS+1)); else TOTAL_FAIL=$((TOTAL_FAIL+1)); fi
done
echo ""
echo "═══════════════ SUITE TOTAL: $TOTAL_PASS pass / $TOTAL_FAIL fail ═══════════════"
# write latest
python3 -c "
import json, time, pathlib
pathlib.Path('data/registries/qsb_unreal_professional_dashboard_suite_latest.json').write_text(
  json.dumps({'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'total_pass': $TOTAL_PASS, 'total_fail': $TOTAL_FAIL,
              'tests_run': 5}, indent=2))
"
exit $TOTAL_FAIL
