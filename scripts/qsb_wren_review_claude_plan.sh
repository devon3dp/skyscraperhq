#!/usr/bin/env bash
# Wren reads Claude's pending plan + answers: approve / concerns / block.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
PLAN_FILE="${1:-}"
[[ -z "$PLAN_FILE" || ! -f "$PLAN_FILE" ]] && { echo "usage: $0 path/to/plan.md"; exit 1; }
PLAN=$(head -c 4000 "$PLAN_FILE")
TASK="Review this plan from Claude. Verdict: APPROVE / CONCERNS / BLOCK. Explain in 3 sentences max. Cite one concrete thing in the plan you accept and one you'd add/change.

PLAN:
$PLAN"
.venv/bin/python3 scripts/team_adapters/qsb_ollama_ask.py --member wren --model "${WREN_MODEL:-qwen3.5:9b}" --task "$TASK" --timeout 180
