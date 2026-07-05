#!/usr/bin/env bash
# Start a background team-tick loop with configurable interval (default 30 min).
# Only runs if the user explicitly invokes this script.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
INTERVAL="${TEAM_DAEMON_INTERVAL_S:-1800}"
PIDFILE=data/run/qsb_team_daemon.pid
LOG=data/logs/qsb_team_daemon.log
mkdir -p data/run data/logs

if [[ -f "$PIDFILE" ]] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "team daemon already running pid=$(cat $PIDFILE)"
  exit 0
fi

nohup bash -c "
  while true; do
    /vaults/nvme0/qsb_tower_v1/scripts/qsb_team_tick.sh >> $LOG 2>&1
    sleep $INTERVAL
  done
" >/dev/null 2>&1 &
echo $! > "$PIDFILE"
echo "team daemon started pid=$(cat $PIDFILE) interval=${INTERVAL}s"
