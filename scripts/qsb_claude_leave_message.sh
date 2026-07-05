#!/usr/bin/env bash
# qsb_claude_leave_message.sh — leave a message in my inbox WITHOUT going
# through chat. Next session reads it as part of the morning briefing.
# Usage: qsb_claude_leave_message.sh "<subject>" "<body>" [<priority: low|normal|urgent>]
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
S="${1:?subject required}"
B="${2:?body required}"
P="${3:-normal}"
python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.kernel_inbox import KernelInbox
e = KernelInbox().post(from_who="Ross (operator)", subject=${S@Q}, body=${B@Q}, priority=${P@Q})
print("left:", e["ts"])
print("priority:", e["priority"])
print("subject:", e["subject"])
print("(next session will see this in qsb_claude_morning.sh)")
PY
