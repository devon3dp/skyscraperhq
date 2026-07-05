#!/usr/bin/env bash
# Stage 10 smoke — verify Stage 3 HUD design contract
J="data/registries/qsb_unreal_hud_design_contract.json"
PASS=0; FAIL=0
[ -f "$J" ] && { PASS=$((PASS+1)); echo "  PASS: $J exists"; } || { FAIL=$((FAIL+1)); echo "  FAIL: $J missing"; }
for k in topBar leftRail centerViewport rightPanel bottomDock floatingWindows quickButtons; do
  python3 -c "import json,sys; d=json.load(open('$J')); sys.exit(0 if d.get('$k') else 1)" 2>/dev/null \
    && { PASS=$((PASS+1)); echo "  PASS: HUD has $k"; } \
    || { FAIL=$((FAIL+1)); echo "  FAIL: HUD missing $k"; }
done
echo "hud_design smoke: $PASS pass / $FAIL fail"
exit $FAIL
