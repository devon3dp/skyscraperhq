#!/usr/bin/env bash
# qsb_iris_worker_supervisor.sh — keep Iris's reception work loop alive.
# Lineage: Floor 0 Reception back office. PID-watch + restart ONLY.
# Does NOT touch money gates / vault / .env. Does NOT disturb the Telegram
# receptionist or the WhatsApp bridge — it only supervises qsb_iris_worker.py.
#
# CANONICAL SUPERVISOR IS NOW SYSTEMD: qsb-iris-worker.service (user unit)
# supervises the worker directly (Restart=always) and auto-starts at boot via
# linger. This bash supervisor remains as a manual fallback ONLY — it refuses
# to run while the systemd service is active so it can never start a second,
# duplicate worker.
#
#   Manual start (only if the systemd unit is NOT in use; survives logout):
#     setsid bash tools/qsb_iris_worker_supervisor.sh >/dev/null 2>&1 &
#   Stop:
#     pkill -f qsb_iris_worker_supervisor.sh ; pkill -f qsb_iris_worker.py
set -u

ROOT="/vaults/nvme0/qsb_tower_v1"
PY="$ROOT/.venv/bin/python3"
WORKER="$ROOT/tools/qsb_iris_worker.py"
LOG="$ROOT/data/logs/qsb_iris_worker.log"
HEALTH="$ROOT/data/registries/qsb_iris_worker_supervisor.jsonl"
CHECK_INTERVAL="${CHECK_INTERVAL:-30}"

# Defer to systemd: if the user service is active, do not run — avoids a
# duplicate worker fighting the systemd-managed one over cursors/activity.
if systemctl --user is-active --quiet qsb-iris-worker.service 2>/dev/null; then
  echo "qsb-iris-worker.service is active — systemd is supervising Iris; exiting." >&2
  exit 0
fi

mkdir -p "$(dirname "$LOG")" 2>/dev/null || true
now() { date -u +%FT%TZ; }
health() { echo "{\"ts\":\"$(now)\",\"event\":\"$1\",\"pid\":\"${2:-}\"}" >> "$HEALTH" 2>/dev/null || true; }

health "supervisor_start"
while true; do
  if ! pgrep -f "qsb_iris_worker.py" >/dev/null 2>&1; then
    "$PY" "$WORKER" >> "$LOG" 2>&1 &
    health "worker_launched" "$!"
  fi
  sleep "$CHECK_INTERVAL"
done
