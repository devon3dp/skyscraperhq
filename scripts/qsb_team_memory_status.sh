#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
echo "=== team_memory layout ==="
find data/team_memory -maxdepth 2 -type f 2>/dev/null | sort | head -50
echo ""
echo "=== member roster ==="
for m in claude wren hermes iquest_coder openclaw smoke_testers maintenance; do
  if [[ -d data/team_memory/$m ]]; then
    files=$(ls data/team_memory/$m 2>/dev/null | wc -l)
    echo "  $m: $files files"
  else
    echo "  $m: MISSING"
  fi
done
