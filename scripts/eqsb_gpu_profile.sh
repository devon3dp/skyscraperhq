#!/usr/bin/env bash
# EQSB gpu profile — runs the full hardware observatory and prints
# the relevant profile slice.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
python3 -m tower.eqsb_observatory hardware >/dev/null
python3 -c "import json; print(json.dumps(json.load(open('data/registries/eqsb_gpu_profile.json')), indent=2))" 2>/dev/null || cat data/registries/eqsb_gpu_profile.json
