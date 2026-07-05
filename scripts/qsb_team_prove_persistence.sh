#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
fails=0
for f in data/team_memory/shared/shared_project_brief.md \
         data/team_memory/shared/shared_project_state.json \
         data/team_memory/claude/memory.md \
         data/team_memory/wren/memory.md \
         data/team_memory/hermes/memory.md \
         data/team_memory/iquest_coder/memory.md; do
  if [[ ! -f "$f" ]]; then echo "MISSING $f"; fails=$((fails+1)); fi
done
echo "persistence fails=$fails"
exit $fails
