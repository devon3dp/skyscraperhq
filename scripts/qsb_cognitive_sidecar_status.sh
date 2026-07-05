#!/usr/bin/env bash
# Show QSB Cognitive Kernel sidecar status — PID + last heartbeat.
set -euo pipefail

ROOT="/vaults/nvme0/qsb_tower_v1"
PIDFILE="${ROOT}/data/run/qsb_cognitive_sidecar.pid"
HEARTBEAT="${ROOT}/data/registries/cognitive/cognitive_sidecar_heartbeat.json"

if [ -f "${PIDFILE}" ]; then
    pid="$(cat "${PIDFILE}")"
    if kill -0 "${pid}" 2>/dev/null; then
        echo "[sidecar] running, PID ${pid}"
    else
        echo "[sidecar] pidfile present but PID ${pid} not alive (stale)"
    fi
else
    echo "[sidecar] not running (no pidfile)"
fi

if [ -f "${HEARTBEAT}" ]; then
    echo "[sidecar] last heartbeat:"
    python3 -c "
import json, sys
d = json.load(open('${HEARTBEAT}'))
for k in ('generated_ts','cycle','last_tick_id','last_duration_s','last_error','ok'):
    print(f'  {k}: {d.get(k)}')
print(f'  execution_allowed: {d.get(\"execution_allowed\")}')
print(f'  external_api_calls_enabled: {d.get(\"external_api_calls_enabled\")}')
"
else
    echo "[sidecar] no heartbeat registry yet"
fi
