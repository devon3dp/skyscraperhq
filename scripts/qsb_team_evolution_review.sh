#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
OUT=data/logs/qsb_team_evolution_review.md
mkdir -p data/logs
{
  echo "# Team Evolution Review — $TS"
  echo ""
  echo "## Lessons (last 20 shared)"
  tail -20 data/team_memory/shared/shared_team_lessons.jsonl 2>/dev/null || echo "(none)"
  echo ""
  echo "## Latest failure rates"
  cat data/registries/qsb_team_learning_status.json 2>/dev/null
} > "$OUT"
echo "wrote $OUT"
