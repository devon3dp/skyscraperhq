#!/usr/bin/env bash
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
mkdir -p "$ROOT/data/logs" "$ROOT/data/registries"

start_one(){
  local name="$1"
  local port="$2"
  local script="$3"
  local log="$4"
  local pidfile="$5"

  if ss -ltnp | grep -q ":$port"; then
    echo "$name already listening on $port"
    ss -ltnp | grep ":$port"
  else
    nohup python3 -u "$script" > "$log" 2>&1 &
    echo $! > "$pidfile"
    sleep 3
    echo "started $name pid $(cat "$pidfile") on $port"
  fi
}

start_one "Asa" 9122 "$ROOT/tools/qsb_asa_node.py" "$ROOT/data/logs/qsb_asa_node.log" "$ROOT/data/registries/qsb_asa_node.pid"
start_one "Task Council" 8854 "$ROOT/tools/qsb_task_council.py" "$ROOT/data/logs/qsb_task_council.log" "$ROOT/data/registries/qsb_task_council.pid"

echo "---- Asa proof ----"
curl -sS --max-time 8 http://127.0.0.1:9122/proof.json | python3 -m json.tool

echo "---- Task Council health ----"
curl -sS --max-time 8 http://127.0.0.1:8854/health.json | python3 -m json.tool
