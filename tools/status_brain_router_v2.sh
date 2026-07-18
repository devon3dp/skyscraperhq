#!/usr/bin/env bash
set -euo pipefail
PORT="${QSB_BRAIN_ROUTER_V2_PORT:-8853}"
echo "---- port ----"
ss -ltnp | grep ":$PORT" || true
echo "---- health ----"
curl -sS --max-time 5 "http://127.0.0.1:$PORT/health.json" | python3 -m json.tool || true
echo "---- proof ----"
curl -sS --max-time 5 "http://127.0.0.1:$PORT/proof.json" | python3 -m json.tool || true
