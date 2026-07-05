#!/bin/bash
# Start HQ-Claude (claude --continue) in a detached tmux session so it runs
# headless + persistent, and can be (re)started remotely over SSH.
# Usage: start_hq_claude.sh ["optional kickoff prompt"]
DIR=/vaults/nvico/qsb_tower_v1
DIR=/vaults/nvme0/qsb_tower_v1
SESSION=hqclaude
KICK="${1:-Resume: check your /msg inbox (the ThinkPad CEO has updates) and continue your work.}"

# already running anywhere? do not double-start
if pgrep -f "claude --continue" >/dev/null; then
  echo "HQ-Claude already running (pid $(pgrep -f "claude --continue" | head -1)) — not starting another."
  exit 0
fi
# start in detached tmux with a real pty
tmux has-session -t "$SESSION" 2>/dev/null && tmux kill-session -t "$SESSION" 2>/dev/null
tmux new-session -d -s "$SESSION" -c "$DIR" "env HTTPS_PROXY=http://192.168.0.10:8888 HTTP_PROXY=http://192.168.0.10:8888 NO_PROXY=localhost,127.0.0.1,192.168.0.0/16 claude --continue --dangerously-skip-permissions"
sleep 4
if tmux has-session -t "$SESSION" 2>/dev/null && pgrep -f "claude --continue" >/dev/null; then
  # send a kickoff prompt so it actually engages, not just idles
  tmux send-keys -t "$SESSION" "$KICK" Enter
  echo "HQ-Claude STARTED in tmux session '$SESSION' (pid $(pgrep -f "claude --continue" | head -1)). Kickoff sent."
else
  echo "FAILED to start HQ-Claude in tmux — check: tmux attach -t $SESSION"
  exit 1
fi
