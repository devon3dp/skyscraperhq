#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TASK="${1:-status check}"
# Default to 8B (fast) — 70B is too slow on CPU. Caller can override via HERMES_MODEL.
MODEL="${HERMES_MODEL:-hermes3:8b}"
exec .venv/bin/python3 scripts/team_adapters/qsb_ollama_ask.py --member hermes --model "$MODEL" --task "$TASK" --timeout 120
