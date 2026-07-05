#!/usr/bin/env bash
# qsb_tower_boot.sh — canonical boot script for QSB Tower V1 (2026-07-03).
#
# Ross: "always online if the pc running make her also auto load at start up
# and then start up the system"
#
# Idempotent: safe to re-run. Checks each service before starting, skips
# already-running ones. Logs to logs/dashboards/boot.log.
#
# Install as @reboot cron:
#   crontab -l | grep -q qsb_tower_boot.sh || \
#     (crontab -l 2>/dev/null; echo "@reboot /vaults/nvme0/qsb_tower_v1/deploy/qsb_tower_boot.sh") | crontab -
#
# Manual re-run any time:
#   bash /vaults/nvme0/qsb_tower_v1/deploy/qsb_tower_boot.sh

set -u  # NOT -e — one failed service should not skip the rest
cd /vaults/nvme0/qsb_tower_v1
mkdir -p logs/dashboards
LOG=logs/dashboards/boot.log

log() {
  echo "[$(date -u +%FT%TZ)] $*" | tee -a "$LOG"
}

start_tmux_if_missing() {
  local session=$1
  local cmd=$2
  local port=$3
  if tmux has-session -t "$session" 2>/dev/null; then
    log "  ✓ tmux session '$session' already up — skipping"
    return 0
  fi
  # extra check by port for services with a listening socket
  if [ -n "$port" ] && ss -tlnp 2>/dev/null | grep -q ":$port"; then
    log "  ⚠ port $port already in use but no tmux '$session' — orphan? not touching"
    return 0
  fi
  tmux new-session -d -s "$session" "$cmd" 2>&1 | tee -a "$LOG"
  sleep 3
  if tmux has-session -t "$session" 2>/dev/null; then
    log "  ✓ started tmux '$session'"
  else
    log "  ✗ FAILED to start '$session'"
  fi
}

log "═══ QSB Tower boot — $(date -u +%FT%TZ) ═══"
log "user=$(whoami)  cwd=$(pwd)"

# 1. Boardroom Hub — port 8852
log "─ boardroom hub (:8852) ─"
start_tmux_if_missing "br" \
  "exec python3 tools/qsb_boardroom_hub.py --port 8852" \
  "8852"

# 2. Wren dash — port 8851
log "─ wren dash (:8851) ─"
start_tmux_if_missing "wd" \
  "exec python3 tools/qsb_wren_dash.py --port 8851" \
  "8851"

# 3. HQ dash — port 8850 (if present)
if [ -f tools/qsb_hq_dash.py ]; then
  log "─ hq dash (:8850) ─"
  start_tmux_if_missing "hq" \
    "exec python3 tools/qsb_hq_dash.py --port 8850" \
    "8850"
fi

# 4. Wren evolution loop (headless — no port)
log "─ wren evolution loop ─"
start_tmux_if_missing "wrenloop" \
  "exec python3 tools/qsb_wren_evolution_loop.py --sleep 90" \
  ""

# 5. Voice server — port 8795 (if present)
if [ -f tools/qsb_voice_server.py ]; then
  log "─ voice server (:8795) ─"
  start_tmux_if_missing "voice" \
    "exec python3 tools/qsb_voice_server.py --port 8795" \
    "8795"
fi

# 6. Session wakeup — read pitstop + surface state (one-shot, not tmux)
if [ -f tools/qsb_session_wakeup.py ]; then
  log "─ session wakeup (one-shot) ─"
  timeout 20 python3 tools/qsb_session_wakeup.py >> "$LOG" 2>&1 || \
    log "  ⚠ wakeup returned non-zero"
fi

# 7. Streams layer — F41 OANDA / F42 Binance / F43 Alpaca + bus + helpers
if [ -x scripts/spawn_streams_layer.sh ]; then
  log "─ streams layer ─"
  bash scripts/spawn_streams_layer.sh >> "$LOG" 2>&1 &
  disown
  sleep 4
  log "  streams layer fired"
fi

# 8. Trader fleet — belief-driven traders across all markets
if [ -x scripts/spawn_all_traders_setsid.sh ]; then
  log "─ trader fleet ─"
  bash scripts/spawn_all_traders_setsid.sh >> "$LOG" 2>&1 &
  disown
  sleep 4
  ALIVE=$(ps -eo cmd ww | grep -c 'qsb_belief_driven_trader.py' || echo 0)
  log "  trader fleet fired — $ALIVE alive after start"
fi

# 9. Report state
log "─ final state ─"
tmux ls 2>&1 | tee -a "$LOG" | sed 's/^/  /'
log "  listening ports:"
ss -tlnp 2>/dev/null | awk 'NR>1 {print "    " $4}' | tee -a "$LOG"

log "═══ boot done ═══"
echo "$(date -u +%FT%TZ) tower boot complete — see $LOG"
