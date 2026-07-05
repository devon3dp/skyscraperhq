#!/usr/bin/env bash
# qsb_godot_visual_self_review.sh — review what we can see *without* OCR.
# Checks: window title, window present, process alive, last log lines.
set -uo pipefail
ROOT="${QSB_ROOT:-/vaults/nvme0/qsb_tower_v1}"

echo "============================================================"
echo "  Godot visual self-review (best-effort, no OCR available)"
echo "============================================================"

# 1. Process alive?
GODOT_PID="$(pgrep -f '/snap/godot-4/.*godot-4 --path /home/ross/qsb_godot_native_cockpit' 2>/dev/null | head -1)"
if [ -n "${GODOT_PID}" ]; then
  echo "  ✓ Godot process alive: PID ${GODOT_PID}"
else
  echo "  ✗ Godot process NOT alive"
fi

# 2. Window title (the cheap proxy for DEBUG check)
TITLE_LINE="$(xwininfo -tree -root 2>/dev/null | grep -oE '"QSB[^"]*"' | head -1)"
if [ -n "${TITLE_LINE}" ]; then
  echo "  ✓ window present: ${TITLE_LINE}"
  if echo "${TITLE_LINE}" | grep -qi debug; then
    echo "  ✗ TITLE still contains DEBUG — production gate fails"
  else
    echo "  ✓ TITLE does not say DEBUG"
  fi
else
  echo "  ✗ no QSB Godot window in xwininfo tree"
fi

# 3. Log signals
LOG=/tmp/godot.log
if [ -f "${LOG}" ]; then
  if grep -q "SCRIPT ERROR\|Parse Error" "${LOG}" 2>/dev/null; then
    echo "  ✗ log contains script errors:"
    grep "SCRIPT ERROR\|Parse Error" "${LOG}" | head -3 | sed 's/^/      /'
  else
    echo "  ✓ no script errors in /tmp/godot.log"
  fi
  if grep -q "llvmpipe" "${LOG}" 2>/dev/null; then
    echo "  ! renderer = llvmpipe SW fallback (NVIDIA driver mismatch — known)"
  fi
else
  echo "  - /tmp/godot.log not present (Godot wasn't launched via the tee pattern)"
fi

# Report file
TS="$(date +%Y%m%d_%H%M%S)"
REPORT="${ROOT}/data/logs/qsb_godot_visual_self_review_${TS}.txt"
mkdir -p "$(dirname "${REPORT}")"
{
  echo "ts=${TS}"
  echo "godot_pid=${GODOT_PID:-none}"
  echo "title=${TITLE_LINE:-none}"
  if [ -f "${LOG}" ]; then
    echo "log_has_errors=$(grep -q 'SCRIPT ERROR\|Parse Error' "${LOG}" 2>/dev/null && echo yes || echo no)"
  fi
} > "${REPORT}"
echo
echo "report: ${REPORT}"
