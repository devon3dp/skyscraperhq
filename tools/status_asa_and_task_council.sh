#!/usr/bin/env bash
set -euo pipefail

echo "---- ports ----"
ss -ltnp | grep -E ':9122|:8854|:8853|:8852' || true

echo "---- Asa heartbeat ----"
curl -sS --max-time 8 http://127.0.0.1:9122/heartbeat.json | python3 -m json.tool || true

echo "---- Asa proof ----"
curl -sS --max-time 8 http://127.0.0.1:9122/proof.json | python3 -m json.tool || true

echo "---- Council health ----"
curl -sS --max-time 8 http://127.0.0.1:8854/health.json | python3 -m json.tool || true

echo "---- Council nodes ----"
curl -sS --max-time 8 http://127.0.0.1:8854/nodes.json | python3 -m json.tool || true
