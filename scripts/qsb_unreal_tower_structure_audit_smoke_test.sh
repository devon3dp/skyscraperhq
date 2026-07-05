#!/usr/bin/env bash
# Stage 10 smoke — verify Stage 1 canonical floor audit
J="data/registries/qsb_canonical_tower_structure_audit.json"
M="data/logs/qsb_canonical_tower_structure_audit.md"
PASS=0; FAIL=0
[ -f "$J" ] && { PASS=$((PASS+1)); echo "  PASS: $J exists"; } || { FAIL=$((FAIL+1)); echo "  FAIL: $J missing"; }
[ -f "$M" ] && { PASS=$((PASS+1)); echo "  PASS: $M exists"; } || { FAIL=$((FAIL+1)); echo "  FAIL: $M missing"; }
COUNT=$(python3 -c "import json; print(json.load(open('$J'))['canonical_floor_count'])" 2>/dev/null)
[ "$COUNT" = "169" ] && { PASS=$((PASS+1)); echo "  PASS: canonical_floor_count=169"; } || { FAIL=$((FAIL+1)); echo "  FAIL: count=$COUNT (want 169)"; }
echo "tower_structure_audit smoke: $PASS pass / $FAIL fail"
exit $FAIL
