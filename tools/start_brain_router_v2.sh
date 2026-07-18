#!/usr/bin/env bash
set -euo pipefail
ROOT="/vaults/nvme0/qsb_tower_v1"
PORT="${QSB_BRAIN_ROUTER_V2_PORT:-8853}"
LOG="$ROOT/data/logs/qsb_brain_router_v2.log"

mkdir -p "$ROOT/data/logs"

if ss -ltnp | grep -q ":$PORT"; then
  echo "Brain Router V2 port already listening on $PORT"
  ss -ltnp | grep ":$PORT"
  exit 0
fi

nohup python3 -u "$ROOT/tools/qsb_brain_router_v2.py" > "$LOG" 2>&1 &
echo $! > "$ROOT/data/registries/qsb_brain_router_v2.pid"
sleep 3

echo "Started Brain Router V2 PID $(cat "$ROOT/data/registries/qsb_brain_router_v2.pid")"
curl -sS --max-time 5 "http://127.0.0.1:$PORT/health.json" | python3 -m json.tool
