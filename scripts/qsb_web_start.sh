#!/usr/bin/env bash
# Start both Tower Studio and Lumen AI as background processes.
#
# Usage:
#   scripts/qsb_web_start.sh                       # default ports (8849, 8848)
#   scripts/qsb_web_start.sh --studio-port 9000 --lumen-port 9001
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
LOGDIR="${ROOT}/data/logs/web"
RUNDIR="${ROOT}/data/run"
mkdir -p "${LOGDIR}" "${RUNDIR}"

STUDIO_PORT=8849
LUMEN_PORT=8848
while [ $# -gt 0 ]; do
  case "$1" in
    --studio-port) STUDIO_PORT="$2"; shift 2;;
    --lumen-port)  LUMEN_PORT="$2";  shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

cd "${ROOT}"

start_one() {
  local name="$1"; local module="$2"; local port="$3"; local pidfile="$4"
  if [ -f "${pidfile}" ]; then
    local existing; existing="$(cat "${pidfile}" 2>/dev/null || true)"
    if [ -n "${existing}" ] && kill -0 "${existing}" 2>/dev/null; then
      echo "[${name}] already running PID ${existing}"
      return 0
    fi
    rm -f "${pidfile}"
  fi
  PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
    nohup python3 "${ROOT}/tools/${module}" --port "${port}" \
    >> "${LOGDIR}/${name}.log" 2>&1 &
  sleep 1
  if [ -f "${pidfile}" ]; then
    local pid; pid="$(cat "${pidfile}")"
    echo "[${name}] started PID ${pid} → http://127.0.0.1:${port}"
  else
    echo "[${name}] WARNING — pidfile not written after 1s. Check ${LOGDIR}/${name}.log."
    return 1
  fi
}

start_one tower_studio qsb_studio_serve.py "${STUDIO_PORT}" "${RUNDIR}/qsb_studio_serve.pid"
start_one lumen_ai     qsb_lumen_serve.py  "${LUMEN_PORT}"  "${RUNDIR}/qsb_lumen_serve.pid"

echo
echo "Open in your browser:"
echo "  Tower Studio : http://127.0.0.1:${STUDIO_PORT}"
echo "  Lumen AI     : http://127.0.0.1:${LUMEN_PORT}"
