#!/usr/bin/env bash
set -u
TOWER="/vaults/nvme0/qsb_tower_v1"
PIDFILE="$TOWER/data/night_council/team_overnight.pid"
LOGFILE="$TOWER/data/logs/qsb_v1_overnight_team.log"
mkdir -p "$TOWER/data/night_council" "$TOWER/data/logs"
if [ -f "$PIDFILE" ]; then
  OLD="$(cat "$PIDFILE" 2>/dev/null || true)"
  if [ -n "$OLD" ] && ps -p "$OLD" >/dev/null 2>&1; then
    echo "already running PID $OLD"
    exit 0
  fi
fi
nohup python3 "$TOWER/tools/qsb_v1_overnight_team.py" > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"
echo "started V1 overnight team PID $(cat "$PIDFILE")"
