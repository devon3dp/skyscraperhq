#!/bin/bash
# 2026-07-23: safety net for the event-bus FD leak. If the bus's open-fd count crosses
# THRESHOLD (60% of its LimitNOFILE), restart it BEFORE it hits EMFILE and strangles the
# trader fleet. Logs every check. Self-healing until the code leak is fully patched.
UNIT=qsb-event-bus.service
PID=$(systemctl show $UNIT -p MainPID --value 2>/dev/null)
LOG=/vaults/nvme0/qsb_tower_v1/data/registries/qsb_event_bus_fd_watchdog.jsonl
[ -z "$PID" ] || [ "$PID" = "0" ] && { echo "{\"ts\":\"$(date -Iseconds)\",\"event\":\"bus_down\",\"action\":\"restart\"}" >>"$LOG"; systemctl restart $UNIT; exit 0; }
LIMIT=$(cat /proc/$PID/limits 2>/dev/null | awk '/open files/{print $4}')
FDS=$(ls /proc/$PID/fd 2>/dev/null | wc -l)
[ -z "$LIMIT" ] && LIMIT=1048576
THRESH=$(( LIMIT * 60 / 100 ))
if [ "$FDS" -gt "$THRESH" ]; then
  echo "{\"ts\":\"$(date -Iseconds)\",\"event\":\"fd_high\",\"fds\":$FDS,\"limit\":$LIMIT,\"action\":\"restart\"}" >>"$LOG"
  systemctl restart $UNIT
else
  echo "{\"ts\":\"$(date -Iseconds)\",\"event\":\"ok\",\"fds\":$FDS,\"limit\":$LIMIT}" >>"$LOG"
fi
