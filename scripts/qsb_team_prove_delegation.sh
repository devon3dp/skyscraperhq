#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
F=data/registries/qsb_team_consensus_latest.json
[[ -f $F ]] || { echo "NO roundtable run yet"; exit 1; }
C=$(jq -r .consensus "$F")
echo "consensus=$C"
[[ "$C" != "null" && -n "$C" ]] && exit 0 || exit 1
