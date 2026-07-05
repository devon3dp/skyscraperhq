#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
tail -f data/logs/sandbox_autoloop.out
