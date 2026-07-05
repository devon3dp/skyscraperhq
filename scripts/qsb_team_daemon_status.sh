#!/usr/bin/env bash
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
PIDFILE=data/run/qsb_team_daemon.pid
if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  PID=$(cat "$PIDFILE")
  echo "team daemon RUNNING pid=$PID"
  ps -p "$PID" -o pid,etime,stat,cmd | tail -1
else
  echo "team daemon STOPPED"
fi
echo ""
echo "=== last 10 lines of daemon log ==="
tail -10 data/logs/qsb_team_daemon.log 2>/dev/null
