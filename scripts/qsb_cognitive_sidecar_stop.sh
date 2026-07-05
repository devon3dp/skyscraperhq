#!/usr/bin/env bash
# Stop the QSB Cognitive Kernel tick sidecar.
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
PIDFILE="${ROOT}/data/run/qsb_cognitive_sidecar.pid"

if [ ! -f "${PIDFILE}" ]; then
    echo "[sidecar] no pidfile at ${PIDFILE} — sidecar not running"
    exit 0
fi

pid="$(cat "${PIDFILE}" 2>/dev/null || true)"
if [ -z "${pid}" ]; then
    echo "[sidecar] empty pidfile; removing"
    rm -f "${PIDFILE}"
    exit 0
fi

if ! kill -0 "${pid}" 2>/dev/null; then
    echo "[sidecar] PID ${pid} not alive; removing stale pidfile"
    rm -f "${PIDFILE}"
    exit 0
fi

echo "[sidecar] sending SIGTERM to PID ${pid}"
kill -TERM "${pid}"

# Wait up to 5 s
for _ in 1 2 3 4 5; do
    if ! kill -0 "${pid}" 2>/dev/null; then
        echo "[sidecar] stopped"
        exit 0
    fi
    sleep 1
done

echo "[sidecar] did not exit on SIGTERM — sending SIGKILL"
kill -KILL "${pid}" 2>/dev/null || true
rm -f "${PIDFILE}"
echo "[sidecar] force-stopped"
