#!/usr/bin/env bash
# Show Tower Studio + Lumen AI status.
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
RUNDIR="${ROOT}/data/run"
LOGDIR="${ROOT}/data/logs/web"

check_one() {
  local name="$1"; local pidfile="$2"; local port="$3"
  if [ -f "${pidfile}" ]; then
    local pid; pid="$(cat "${pidfile}")"
    if kill -0 "${pid}" 2>/dev/null; then
      echo "[${name}] running PID ${pid}  → http://127.0.0.1:${port}"
      if command -v curl >/dev/null 2>&1; then
        local code; code="$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${port}/healthz" || true)"
        echo "         healthz HTTP ${code}"
      fi
    else
      echo "[${name}] pidfile present, PID ${pid} not alive"
    fi
  else
    echo "[${name}] not running"
  fi
  if [ -f "${LOGDIR}/${name}.log" ]; then
    echo "         log tail:"
    tail -3 "${LOGDIR}/${name}.log" | sed 's/^/             /'
  fi
}

check_one tower_studio "${RUNDIR}/qsb_studio_serve.pid" 8849
check_one lumen_ai     "${RUNDIR}/qsb_lumen_serve.pid"  8848
