#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
# Brief age vs project state age — sync if both fresh (<24h)
brief=data/team_memory/shared/shared_project_brief.md
state=data/team_memory/shared/shared_project_state.json
fails=0
for f in $brief $state; do
  [[ -f $f ]] || { echo "missing $f"; fails=$((fails+1)); continue; }
  age=$(( $(date -u +%s) - $(stat -c %Y "$f") ))
  if [[ $age -gt 86400 ]]; then
    echo "stale: $f (${age}s old)"; fails=$((fails+1))
  else
    echo "fresh: $f (${age}s old)"
  fi
done
exit $fails
