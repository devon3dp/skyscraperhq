#!/usr/bin/env bash
# Append a manual note to Wren's private memory.md (also stamps F47).
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
NOTE="${1:-}"
[[ -z "$NOTE" ]] && { echo "usage: $0 'note text'"; exit 1; }
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo -e "\n## $TS\n$NOTE" >> data/team_memory/wren/memory.md
echo "{\"ts\":\"$TS\",\"kind\":\"wren_memory_note\",\"role\":\"wren_keeper\",\"summary\":\"${NOTE//\"/\\\"}\"}" >> data/registries/qsb_f47_team_records.jsonl
echo "appended to data/team_memory/wren/memory.md"
