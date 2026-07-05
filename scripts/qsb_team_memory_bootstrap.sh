#!/usr/bin/env bash
# Bootstrap the team_memory tree. Idempotent — only creates missing files.
set -u
ROOT="${ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$ROOT" || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
MEM=data/team_memory

mkdir -p $MEM/shared $MEM/claude $MEM/wren $MEM/hermes $MEM/iquest_coder $MEM/openclaw $MEM/smoke_testers $MEM/maintenance

ensure_file() {
  local f="$1"; local default_content="${2:-}"
  if [[ ! -e "$f" ]]; then
    printf '%s' "$default_content" > "$f"
    echo "created $f"
  fi
}

# Shared
ensure_file $MEM/shared/shared_project_brief.md "# QSB Tower — shared project brief
_Not yet built. Run scripts/qsb_team_build_shared_project_brief.sh_
"
ensure_file $MEM/shared/shared_project_state.json '{"ts":"'$TS'","ready":false,"reason":"awaiting brief build"}'
ensure_file $MEM/shared/shared_decisions.jsonl ""
ensure_file $MEM/shared/shared_event_journal.jsonl ""
ensure_file $MEM/shared/shared_task_board.json '{"ts":"'$TS'","tasks":[]}'
ensure_file $MEM/shared/shared_unreal_build_state.json '{"ts":"'$TS'","status":"not_yet_checked"}'
ensure_file $MEM/shared/shared_team_lessons.jsonl ""
ensure_file $MEM/shared/shared_blockers.jsonl ""

# Per-member skeleton
for m in claude wren hermes iquest_coder; do
  ensure_file $MEM/$m/memory.md "# $m memory
_persistent notes_
"
  ensure_file $MEM/$m/memory.json '{"member":"'$m'","ts":"'$TS'","notes":[]}'
  ensure_file $MEM/$m/current_tasks.json '{"member":"'$m'","ts":"'$TS'","tasks":[]}'
  ensure_file $MEM/$m/decisions.jsonl ""
  ensure_file $MEM/$m/lessons.jsonl ""
done

ensure_file $MEM/openclaw/tickets.jsonl ""
ensure_file $MEM/openclaw/inspection_memory.md "# OpenClaw inspection memory\n"
ensure_file $MEM/smoke_testers/test_memory.md "# Smoke tester memory\n"
ensure_file $MEM/smoke_testers/test_results.jsonl ""
ensure_file $MEM/maintenance/system_memory.md "# Maintenance crew system memory\n"
ensure_file $MEM/maintenance/system_checks.jsonl ""

echo "team_memory bootstrap done at $TS"
ls -d $MEM/*
