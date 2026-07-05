#!/usr/bin/env bash
# Stage 10 smoke — verify Stage 4 world design + Stage 5 interiors
W="data/registries/qsb_unreal_skyscraper_world_design.json"
I="data/registries/qsb_unreal_floor_interior_design_rules.json"
M="data/registries/qsb_unreal_model_floor_design.json"
V="data/registries/qsb_unreal_voice_command_design.json"
PASS=0; FAIL=0
for f in "$W" "$I" "$M" "$V"; do
  [ -f "$f" ] && { PASS=$((PASS+1)); echo "  PASS: $(basename $f) exists"; } || { FAIL=$((FAIL+1)); echo "  FAIL: $(basename $f) missing"; }
done
# Verify lighting choice
L=$(python3 -c "import json; print(json.load(open('$W')).get('lighting',''))" 2>/dev/null)
echo "$L" | grep -q "Lumen" && { PASS=$((PASS+1)); echo "  PASS: lighting=$L"; } || { FAIL=$((FAIL+1)); echo "  FAIL: lighting expected Lumen"; }
echo "world_design smoke: $PASS pass / $FAIL fail"
exit $FAIL
