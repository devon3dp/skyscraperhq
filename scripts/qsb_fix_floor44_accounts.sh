#!/usr/bin/env bash
# Stand up Floor 44 Accounts/PnL with real manifest + reassign PnL Accountant
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
python3 -m tower.qsb_hardware_floor
python3 -m tower.qsb_workers_reconciliation
python3 -m tower.qsb_workforce
python3 -c "
import json
acc = json.load(open('data/registries/qsb_accounts_floor_state.json'))
print('Floor 44 state:', acc.get('current_state'))
print('Floor 44 workers:', acc.get('worker_count'))
"
