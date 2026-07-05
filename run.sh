#!/usr/bin/env bash
set -e
cd /vaults/nvme0/qsb_tower_v1
mkdir -p data/runtime data/logs
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src
# Load OANDA practice credentials if .env.oanda_practice exists.
# Module trading_telemetry / oanda_practice_trading also auto-load it,
# but exporting here makes them visible to every sub-import in one go.
if [ -f .env.oanda_practice ]; then
  set -a; . ./.env.oanda_practice; set +a
fi
nohup python3 src/dashboard/server.py > data/logs/dashboard.log 2>&1 &
echo $! > data/runtime/dashboard.pid
echo "QSB Tower V1.1 running at http://127.0.0.1:8765"
