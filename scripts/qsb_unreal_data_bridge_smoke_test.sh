#!/usr/bin/env bash
# Stage 10 smoke — verify Stage 9 data bridge runs + writes snapshot
PY="scripts/qsb_unreal_export_live_snapshot.py"
SH="scripts/qsb_unreal_data_bridge_status.sh"
SNAP="/vaults/nvme0/qsb_unreal_skyscraper/Saved/QSB/qsb_live_snapshot.json"
PASS=0; FAIL=0
[ -f "$PY" ] && { PASS=$((PASS+1)); echo "  PASS: bridge .py exists"; } || { FAIL=$((FAIL+1)); echo "  FAIL: bridge .py missing"; }
[ -f "$SH" ] && { PASS=$((PASS+1)); echo "  PASS: status .sh exists"; } || { FAIL=$((FAIL+1)); echo "  FAIL: status .sh missing"; }
python3 "$PY" >/dev/null 2>&1 && { PASS=$((PASS+1)); echo "  PASS: bridge runs"; } || { FAIL=$((FAIL+1)); echo "  FAIL: bridge crashes"; }
[ -f "$SNAP" ] && { PASS=$((PASS+1)); echo "  PASS: snapshot exists"; } || { FAIL=$((FAIL+1)); echo "  FAIL: snapshot missing"; }
SCHEMA=$(python3 -c "import json; print(json.load(open('$SNAP'))['schema_version'])" 2>/dev/null)
[ "$SCHEMA" = "2" ] && { PASS=$((PASS+1)); echo "  PASS: schema_version=2"; } || { FAIL=$((FAIL+1)); echo "  FAIL: schema=$SCHEMA"; }
FLOORS=$(python3 -c "import json; print(len(json.load(open('$SNAP'))['tower']['floors']))" 2>/dev/null)
[ "$FLOORS" = "169" ] && { PASS=$((PASS+1)); echo "  PASS: 169 floors in snapshot"; } || { FAIL=$((FAIL+1)); echo "  FAIL: floors=$FLOORS"; }
echo "data_bridge smoke: $PASS pass / $FAIL fail"
exit $FAIL
