#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TASK="${1:-status check}"
# iquest-coder-v1:40b is the lighter Llama variant; -cpu:40b is the CPU-offload variant.
MODEL="${IQUEST_MODEL:-iquest-coder-v1:40b-instruct}"
exec .venv/bin/python3 scripts/team_adapters/qsb_ollama_ask.py --member iquest_coder --model "$MODEL" --task "$TASK" --timeout 240
