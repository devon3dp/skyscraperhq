#!/usr/bin/env bash
# Start the QSB Cognitive Kernel tick sidecar.
#
# Cognition only. No execution. No external providers. No autonomy.
#
# Usage:
#   scripts/qsb_cognitive_sidecar_start.sh                  # 30s cadence
#   scripts/qsb_cognitive_sidecar_start.sh --interval 60    # 60s cadence
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
PIDFILE="${ROOT}/data/run/qsb_cognitive_sidecar.pid"
LOGDIR="${ROOT}/data/logs/cognitive"
LOGFILE="${LOGDIR}/sidecar_stdout.log"

cd "${ROOT}"
mkdir -p "${LOGDIR}" "$(dirname "${PIDFILE}")"

if [ -f "${PIDFILE}" ]; then
    existing="$(cat "${PIDFILE}" 2>/dev/null || true)"
    if [ -n "${existing}" ] && kill -0 "${existing}" 2>/dev/null; then
        echo "[sidecar] already running at PID ${existing}"
        exit 0
    else
        echo "[sidecar] stale pidfile (PID ${existing}); removing"
        rm -f "${PIDFILE}"
    fi
fi

# Start detached, append to log. PYTHONPATH so 'tower' package resolves.
echo "[sidecar] starting (args: $*)"
PYTHONPATH="${ROOT}/src${PYTHONPATH:+:${PYTHONPATH}}" \
    nohup python3 -m tower.cognitive_kernel.sidecar "$@" \
    >> "${LOGFILE}" 2>&1 &
sleep 1

# Verify
if [ -f "${PIDFILE}" ]; then
    pid="$(cat "${PIDFILE}")"
    echo "[sidecar] started PID ${pid}; log=${LOGFILE}"
    echo "[sidecar] heartbeat registry: data/registries/cognitive/cognitive_sidecar_heartbeat.json"
else
    echo "[sidecar] WARNING — pidfile not written after 1s. Check ${LOGFILE}."
    exit 1
fi
