#!/usr/bin/env bash
set -e
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

python3 scripts/create_coding_request.py "Prepare Claude Code port wiring" claude_code_handoff "Create future handoff path from Floor 5 to Floor 24."
python3 scripts/create_coding_request.py "Prepare local coder slot" code_generation "Create future local coder queue path through Floor 24."
python3 scripts/create_coding_request.py "Prepare test queue structure" test_generation "Generate future test worker queue."
