#!/usr/bin/env bash
# Exit 0 only if the latest consensus is approved/approved_with_concerns.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
S=data/registries/qsb_team_consensus_latest.json
[[ -f $S ]] || { echo "no consensus file"; exit 2; }
C=$(jq -r .consensus "$S")
echo "consensus: $C"
case "$C" in
  approved|approved_with_concerns) exit 0 ;;
  *) exit 1 ;;
esac
