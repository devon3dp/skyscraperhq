#!/usr/bin/env bash
# Continuous backup loop — runs qsb_backup_to_ssk_full.sh every TICK_S (default 1800 = 30 min).
# Start:  nohup ./scripts/qsb_backup_loop.sh > logs/intelligence/backup_loop_supervisor.log 2>&1 &
# Stop:   kill $(cat data/run/qsb_backup_loop.pid)
TICK_S="${BACKUP_TICK_S:-1800}"
PIDFILE=/vaults/nvme0/qsb_tower_v1/data/run/qsb_backup_loop.pid
LOG=/vaults/nvme0/qsb_tower_v1/logs/intelligence/backup_loop.log
mkdir -p /vaults/nvme0/qsb_tower_v1/data/run
echo $$ > "$PIDFILE"
trap 'rm -f "$PIDFILE"; exit 0' SIGTERM SIGINT
while true; do
  if mountpoint -q "/media/ross/SSK Cloud"; then
    /vaults/nvme0/qsb_tower_v1/scripts/qsb_backup_to_ssk_full.sh >> "$LOG" 2>&1
  else
    echo "[$(date -u +%FT%TZ)] SSK NOT mounted — skipping this tick" >> "$LOG"
  fi
  sleep "$TICK_S"
done
