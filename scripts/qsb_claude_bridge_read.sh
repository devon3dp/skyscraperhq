#!/usr/bin/env bash
# qsb_claude_bridge_read.sh — show unhandled messages from thinkpad_to_main/
set -u
INBOX="/media/ross/SSK Cloud/qsb_claude_bridge/thinkpad_to_main"
[[ -d "$INBOX" ]] || { echo "bridge folder missing — is SSK Cloud mounted?"; exit 1; }

ALL=("$INBOX"/*.md)
OPEN=()
for f in "${ALL[@]}"; do
  [[ -e "$f" ]] || continue
  [[ "$f" == *_handled.md ]] && continue
  OPEN+=("$f")
done

if [[ ${#OPEN[@]} -eq 0 ]]; then
  echo "(no new messages from thinkpad Claude)"
  exit 0
fi

echo "=== ${#OPEN[@]} unhandled message(s) from ThinkPad Claude ==="
for f in "${OPEN[@]}"; do
  echo ""
  echo "--- $(basename "$f") ---"
  head -30 "$f"
  echo "[...]"
done
echo ""
echo "Mark handled with:  mv '<file>.md' '<file>_handled.md'"
