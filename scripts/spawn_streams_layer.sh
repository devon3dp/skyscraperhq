#!/usr/bin/env bash
# Spawn the streams + bus + helpers layer.
#
# Added 2026-06-30 after the GPU-crash gap exposed that qsb-stack.service
# does NOT auto-recover F41/F42/F43 streams + belief_updater + regime_detector
# + thermal_guard. Without these, traders connect to the bus but get no price
# ticks, so they appear "not trading".
#
# Liveness check uses `ps -eo cmd ww | awk index($0,t)` instead of `pgrep -f`
# because pgrep self-matches the bash command containing the tool name and
# silently blocks the spawn.

cd /vaults/nvme0/qsb_tower_v1
LOG=logs/intelligence
mkdir -p "$LOG"

TOOLS=(
  qsb_f41_oanda_stream.py
  qsb_f42_binance_stream.py
  qsb_f43_alpaca_stream.py
  qsb_belief_updater.py
  qsb_regime_detector.py
  qsb_thermal_guard.py
)

is_alive() {
  # 1 if at least one matching python process exists, 0 otherwise.
  ps -eo cmd ww 2>/dev/null \
    | awk -v t="$1" '$1 ~ /python/ && index($0, t) { found=1 } END { exit !found }'
}

spawned=0
skipped=0
missing=0

for f in "${TOOLS[@]}"; do
  if is_alive "$f"; then
    skipped=$((skipped + 1))
    echo "[spawn_streams] skip alive: $f"
    continue
  fi
  if [ ! -f "tools/$f" ]; then
    missing=$((missing + 1))
    echo "[spawn_streams] MISSING tool: tools/$f"
    continue
  fi
  setsid python3 "tools/$f" </dev/null >"$LOG/${f%.py}.log" 2>&1 &
  spawned=$((spawned + 1))
  echo "[spawn_streams] spawned: $f"
done

sleep 4

alive_count=0
for f in "${TOOLS[@]}"; do
  if is_alive "$f"; then
    alive_count=$((alive_count + 1))
  else
    echo "[spawn_streams] WARN died-on-startup: $f"
  fi
done

echo "[spawn_streams] summary spawned=$spawned skipped=$skipped missing=$missing alive=$alive_count/${#TOOLS[@]}"
