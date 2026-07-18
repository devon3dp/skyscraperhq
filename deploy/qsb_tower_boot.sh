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
# 2026-07-17 Wren leadership-comms migration: canonical owner is systemd
# qsb-boardroom.service (enabled). The tmux 'br' launcher below is DISABLED to end
# the tmux/systemd :8852 port-fight that left the hub crash-looping (Errno 98) after
# reboot, which broke Bill↔Wren. Rollback: uncomment the start_tmux_if_missing "br" block.
log "─ boardroom hub (:8852) — owned by systemd qsb-boardroom.service ─"
# start_tmux_if_missing "br" \
#   "exec python3 tools/qsb_boardroom_hub.py --port 8852" \
#   "8852"

# 2. Wren dash — port 8851
# 2026-07-11 Wren Stage B: canonical owner is systemd qsb-wren-dash.service (enabled).
# The tmux 'wd' launcher below is DISABLED to end tmux/systemd :8851 port-fighting.
# Rollback: uncomment the start_tmux_if_missing "wd" block.
log "─ wren dash (:8851) — owned by systemd qsb-wren-dash.service ─"
# start_tmux_if_missing "wd" \
#   "exec python3 tools/qsb_wren_dash.py --port 8851" \
#   "8851"

# 3. HQ dash — port 8850  ── RETIRED 2026-07-17 (Ross canonical correction) ──
# "Claude HQ is retired. Claude is a governed specialist service caged under Wren."
# The Claude HQ dashboard is removed from the ACTIVE runtime roster. The tool file and
# systemd unit are preserved as legacy/provenance (NOT deleted); the unit is stopped +
# disabled separately. This launcher stays OFF so 8850 is never re-squatted at boot.
# Rollback: uncomment the block below (not advised — Claude HQ is retired).
# if [ -f tools/qsb_hq_claude_dash.py ]; then
#   log "─ hq dash (:8850) ─"
#   start_tmux_if_missing "hq" \
#     "exec python3 tools/qsb_hq_claude_dash.py --port 8850" \
#     "8850"
# fi

# 4. Wren evolution loop (headless — no port)
# 2026-07-11 Wren Stage B: canonical owner is systemd qsb-wren-mind.service (enabled).
# The tmux 'wrenloop' launcher below is DISABLED to keep exactly ONE evolution loop.
# (qsb-wren-loop.service was also stopped+disabled as a duplicate.)
# Rollback: uncomment the start_tmux_if_missing "wrenloop" block.
log "─ wren evolution loop — owned by systemd qsb-wren-mind.service ─"
# start_tmux_if_missing "wrenloop" \
#   "exec python3 tools/qsb_wren_evolution_loop.py --sleep 90" \
#   ""

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
