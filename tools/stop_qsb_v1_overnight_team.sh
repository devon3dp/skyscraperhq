#!/usr/bin/env bash
set -u
TOWER="/vaults/nvme0/qsb_tower_v1"
PIDFILE="$TOWER/data/night_council/team_overnight.pid"
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE" 2>/dev/null || true)"
  [ -n "$PID" ] && kill "$PID" 2>/dev/null || true
  echo "stop sent to PID $PID"
else
  echo "no pidfile"
fi
