#!/usr/bin/env bash
# Stop Tower Studio + Lumen AI servers.
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
RUNDIR="${ROOT}/data/run"

stop_one() {
  local name="$1"; local pidfile="$2"
  if [ ! -f "${pidfile}" ]; then
    echo "[${name}] not running (no pidfile)"
    return 0
  fi
  local pid; pid="$(cat "${pidfile}" 2>/dev/null || true)"
  if [ -z "${pid}" ] || ! kill -0 "${pid}" 2>/dev/null; then
    rm -f "${pidfile}"
    echo "[${name}] stale pidfile cleared"
    return 0
  fi
  echo "[${name}] sending SIGTERM to PID ${pid}"
  kill -TERM "${pid}"
  for _ in 1 2 3 4 5; do
    if ! kill -0 "${pid}" 2>/dev/null; then
      echo "[${name}] stopped"
      rm -f "${pidfile}"
      return 0
    fi
    sleep 1
  done
  kill -KILL "${pid}" 2>/dev/null || true
  rm -f "${pidfile}"
  echo "[${name}] force-stopped"
}

stop_one tower_studio "${RUNDIR}/qsb_studio_serve.pid"
stop_one lumen_ai     "${RUNDIR}/qsb_lumen_serve.pid"
