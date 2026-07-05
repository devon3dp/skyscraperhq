#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] city generator python exists"
[[ -f scripts/qsb_unreal_generate_futuristic_city.py ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] city generator shell exists"
[[ -x scripts/qsb_unreal_generate_futuristic_city.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] uses MCP TCP create_actor at 127.0.0.1:55557"
grep -q "55557" scripts/qsb_unreal_generate_futuristic_city.py || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] V9_City_* naming convention used"
grep -q 'V9_City_' scripts/qsb_unreal_generate_futuristic_city.py || { echo " FAIL"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
