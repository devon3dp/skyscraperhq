#!/usr/bin/env bash
# qsb_ask_any_local_model.sh --member NAME --model OLLAMA_MODEL_ID --task "..."
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
exec .venv/bin/python3 scripts/team_adapters/qsb_ollama_ask.py "$@"
