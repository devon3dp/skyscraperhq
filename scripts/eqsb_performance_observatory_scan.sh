#!/usr/bin/env bash
# EQSB Performance observatory scan (refreshes hardware + advice)
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
python3 -m tower.eqsb_observatory hardware
python3 -c "
import json
adv = json.load(open('data/registries/eqsb_performance_advice.json'))
for a in adv.get('advice') or []:
    print(' -', a)
"
