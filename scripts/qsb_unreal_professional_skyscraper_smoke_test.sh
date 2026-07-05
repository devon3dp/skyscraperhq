#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] skyscraper generator python exists"
[[ -f scripts/qsb_unreal_generate_professional_skyscraper.py ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] skyscraper generator shell exists"
[[ -x scripts/qsb_unreal_generate_professional_skyscraper.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] does NOT hardcode floor count — reads canonical JSON"
grep -q 'canonical_floor_count' scripts/qsb_unreal_generate_professional_skyscraper.py || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] uses canonical structure registry"
grep -q 'qsb_canonical_tower_structure_latest.json' scripts/qsb_unreal_generate_professional_skyscraper.py || { echo " FAIL"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
