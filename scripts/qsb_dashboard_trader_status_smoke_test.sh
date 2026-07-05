#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
echo "[smoke] sweep script exists"
[[ -x scripts/qsb_dashboard_and_trader_status_sweep.sh ]] || { echo " FAIL"; fails=$((fails+1)); }
echo "[smoke] run sweep + check JSON output"
./scripts/qsb_dashboard_and_trader_status_sweep.sh >/dev/null 2>&1
[[ -f data/registries/qsb_dashboard_and_trader_status_latest.json ]] || { echo " FAIL no JSON"; fails=$((fails+1)); }
jq -e '.fleet.belief_traders_alive >= 0 and .dashboards.qsb_traders_live_serve_8847' \
   data/registries/qsb_dashboard_and_trader_status_latest.json >/dev/null 2>&1 || { echo " FAIL schema"; fails=$((fails+1)); }
echo "result: fails=$fails"
exit $fails
