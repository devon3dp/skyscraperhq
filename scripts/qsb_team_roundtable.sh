#!/usr/bin/env bash
# Quick roundtable: ./qsb_team_roundtable.sh "TASK HERE"
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TASK="${1:-status check}"
.venv/bin/python3 scripts/qsb_team_delegate_task.py --task "$TASK" --lead claude --reviewers "wren,hermes,iquest_coder"
.venv/bin/python3 scripts/qsb_team_collect_confirmations.py
