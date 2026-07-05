#!/usr/bin/env bash
# Post a correction to the Retraction Wall (operator/kernel writes; I read).
# Usage: qsb_claude_retraction_log.sh "<claim>" "<date_claimed>" "<correction>" ["<lesson>"] ["<posted_by>"]
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CLAIM="${1:?claim required}"
WHEN="${2:?date_claimed required}"
CORR="${3:?correction required}"
LESSON="${4:-}"
BY="${5:-operator}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.retraction_wall import RetractionWall
e = RetractionWall().post_correction(claim=${CLAIM@Q}, date_claimed=${WHEN@Q}, correction=${CORR@Q}, lesson=${LESSON@Q}, posted_by=${BY@Q})
print("posted:", e["ts"])
PY
