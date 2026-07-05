#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
PIDFILE=data/run/qsb_team_daemon.pid
[[ -f "$PIDFILE" ]] || { echo "no pidfile — daemon not running"; exit 0; }
PID=$(cat "$PIDFILE")
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  sleep 1
  kill -9 "$PID" 2>/dev/null || true
  echo "team daemon stopped pid=$PID"
else
  echo "stale pidfile (pid $PID not alive)"
fi
rm -f "$PIDFILE"
