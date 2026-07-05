#!/usr/bin/env bash
# qsb_claude_inbox.sh — read messages addressed to Claude (F47).
# Usage:
#   qsb_claude_inbox.sh                # show unread
#   qsb_claude_inbox.sh all            # show all
#   qsb_claude_inbox.sh post "subject" "body" [from] [priority]
#   qsb_claude_inbox.sh mark-read
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "${ROOT}"
CMD="${1:-unread}"
case "${CMD}" in
  unread)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.kernel_inbox import KernelInbox
i = KernelInbox()
ms = i.unread()
print(f"unread: {len(ms)}")
for m in ms:
    print(f"  --- [{m['priority']}] {m['ts']}  from {m['from']}")
    print(f"      {m['subject']}")
    print(f"      {m['body'][:300]}")
PY
    ;;
  all)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.kernel_inbox import KernelInbox
for m in KernelInbox().all():
    flag = " " if m["read"] else "•"
    print(f"  {flag} [{m['priority']:<6}] {m['ts']}  {m['subject']}")
PY
    ;;
  post)
    S="${2:?subject required}"; B="${3:?body required}"; F="${4:-Kernel (F55)}"; P="${5:-normal}"
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.kernel_inbox import KernelInbox
e = KernelInbox().post(from_who=${F@Q}, subject=${S@Q}, body=${B@Q}, priority=${P@Q})
print("posted:", e["ts"])
PY
    ;;
  mark-read)
    python3 - <<PY
import sys; sys.path.insert(0, "${ROOT}")
from src.tower.model_floors.claude_floor.kernel_inbox import KernelInbox
n = KernelInbox().mark_all_read()
print(f"marked {n} as read")
PY
    ;;
  *) echo "usage: qsb_claude_inbox.sh unread|all|post|mark-read"; exit 1;;
esac
