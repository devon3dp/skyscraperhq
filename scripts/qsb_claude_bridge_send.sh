#!/usr/bin/env bash
# qsb_claude_bridge_send.sh — drop a message into main_to_thinkpad/
# Usage: ./qsb_claude_bridge_send.sh <topic-slug> < message.md
# OR:    echo "..." | ./qsb_claude_bridge_send.sh <topic-slug>
set -u
BRIDGE="/media/ross/SSK Cloud/qsb_claude_bridge/main_to_thinkpad"
SLUG="${1:-message}"
TS=$(date -u +%Y%m%dT%H%M%SZ)
DEST="$BRIDGE/${TS}_${SLUG}.md"
[[ -d "$BRIDGE" ]] || { echo "bridge folder missing — is SSK Cloud mounted?"; exit 1; }
cat > "$DEST"
echo "queued → $DEST"
