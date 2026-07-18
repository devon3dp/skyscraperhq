#!/usr/bin/env bash
set -u
TOWER="/vaults/nvme0/qsb_tower_v1"
PIDFILE="$TOWER/data/night_council/team_overnight.pid"
LATEST="$TOWER/data/night_council/latest_run_path.txt"
echo "============================================================"
echo " QSB V1 OVERNIGHT TEAM STATUS"
echo "============================================================"
if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  echo "PID: $PID"
  if ps -p "$PID" >/dev/null 2>&1; then echo "STATUS: RUNNING"; else echo "STATUS: NOT RUNNING"; fi
else
  echo "PID: none"
  echo "STATUS: NOT STARTED"
fi
if [ -f "$LATEST" ]; then
  RUN="$(cat "$LATEST")"
  echo "RUN_FOLDER: $RUN"
  echo
  echo "SUMMARY:"
  tail -n 80 "$RUN/team_latest_summary.txt" 2>/dev/null || true
  echo
  echo "LEDGER TAIL:"
  tail -n 5 "$RUN/team_overnight_ledger.jsonl" 2>/dev/null || true
fi
