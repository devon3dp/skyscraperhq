#!/usr/bin/env bash
# Stage 10 smoke — verify Stage 8 roadmap
J="data/registries/qsb_unreal_professional_build_roadmap.json"
PASS=0; FAIL=0
[ -f "$J" ] && { PASS=$((PASS+1)); echo "  PASS: roadmap exists"; } || { FAIL=$((FAIL+1)); echo "  FAIL: roadmap missing"; }
for k in sequential_chain parallel_tracks first_playable_milestone; do
  python3 -c "import json,sys; d=json.load(open('$J')); sys.exit(0 if d.get('$k') else 1)" 2>/dev/null \
    && { PASS=$((PASS+1)); echo "  PASS: roadmap has $k"; } \
    || { FAIL=$((FAIL+1)); echo "  FAIL: roadmap missing $k"; }
done
echo "roadmap smoke: $PASS pass / $FAIL fail"
exit $FAIL
