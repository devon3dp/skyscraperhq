#!/usr/bin/env bash
# QSB Tower — Canonical Dashboard Start
# Phase: QSB_V2_FULL_SYSTEM_RECHECK_AND_DASHBOARD_REPAIR_V1
#
# Idempotent launcher:
#   * if a dashboard PID exists and is alive, prints the URL and exits.
#   * else clears any stale PID, frees port 8765 if held by a dead
#     process, then starts dashboard via nohup and writes the PID file.
#   * always writes data/logs/dashboard_latest.log
#   * never enables execution.

set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh

PORT=8765
URL="http://127.0.0.1:${PORT}"
LOG=/vaults/nvme0/qsb_tower_v1/data/logs/dashboard_latest.log
PIDFILE=/vaults/nvme0/qsb_tower_v1/data/runtime/dashboard.pid

mkdir -p "$(dirname "$LOG")" "$(dirname "$PIDFILE")"

# Already running?
if [ -f "$PIDFILE" ]; then
  EXIST_PID="$(cat "$PIDFILE" 2>/dev/null || echo "")"
  if [ -n "$EXIST_PID" ] && kill -0 "$EXIST_PID" 2>/dev/null; then
    echo "Dashboard already running (pid $EXIST_PID)"
    echo "Dashboard started:"
    echo "${URL}/?v=unified"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

# Port busy without a PID file? Free it.
if ss -tln 2>/dev/null | grep -q ":${PORT} " ; then
  fuser -k "${PORT}/tcp" 2>/dev/null || true
  sleep 0.5
fi

# Load all credentials from Floor 28 vault (chmod 600 each; gitignored).
# Falls back to project-root .env.oanda_practice for backwards compatibility.
VAULT_DIR="floors/floor_28_security_department/vault"
if [ -d "$VAULT_DIR" ]; then
  for envfile in "$VAULT_DIR"/.env.*; do
    [ -f "$envfile" ] && set -a && . "$envfile" && set +a
  done
fi
if [ -f .env.oanda_practice ] && [ ! -f "$VAULT_DIR/.env.oanda_practice" ]; then
  set -a; . ./.env.oanda_practice; set +a
fi

# Rebuild Command Center registries before launch so the dashboard
# opens with fresh workforce / profit / telemetry / audit data.
# Each refresh is non-fatal — failure does not block the dashboard.
python3 -m tower.qsb_workers_reconciliation >/dev/null 2>&1 || true
python3 -m tower.qsb_workforce >/dev/null 2>&1 || true
python3 -m tower.qsb_profit_command >/dev/null 2>&1 || true
python3 -m tower.qsb_dashboard_visual_audit >/dev/null 2>&1 || true
python3 -m tower.qsb_command_center_audit >/dev/null 2>&1 || true
# Observatory + Hardware Floor + Telemetry Repair (V1) — read-only.
python3 -m tower.qsb_hardware_floor >/dev/null 2>&1 || true
python3 -m tower.eqsb_observatory all >/dev/null 2>&1 || true
python3 -m tower.qsb_live_telemetry_repairs >/dev/null 2>&1 || true
# Worker Truth (V1) — must run before live telemetry so the truth_debug
# block is populated.
python3 -m tower.qsb_worker_truth >/dev/null 2>&1 || true
# Workforce Operations Redesign V1 — taxonomy, rosters, manifests.
python3 -m tower.qsb_workforce_operations >/dev/null 2>&1 || true
# Workforce Expansion V1 — 1000 new workers + 9 departments.
python3 -m tower.qsb_workforce_expansion_v1 >/dev/null 2>&1 || true
# Re-reconcile to merge expansion roster.
python3 -m tower.qsb_workers_reconciliation >/dev/null 2>&1 || true
# Dashboard Total Rebuild V1 — root-cause audit, OpenClaw supervisor,
# task board, department interiors. Rebuilds EVERY launch.
python3 -m tower.qsb_dashboard_rebuild_v1 >/dev/null 2>&1 || true
# Cadence-driven paper strategy tick — grows movements/tasks each launch.
python3 -m tower.eqsb_cadence >/dev/null 2>&1 || true
python3 -m tower.qsb_paper_strategy_runner >/dev/null 2>&1 || true
# Dashboard 3D Total Revamp V1 — root-cause + scene state + gates.
python3 -m tower.qsb_dashboard_3d_revamp >/dev/null 2>&1 || true
# Render Visible V1 — trading floor rooms (must run after workforce_operations
# + workforce_expansion_v1 since they overwrite qsb_worker_room_assignments).
python3 -m tower.qsb_trading_floor_room_assignments >/dev/null 2>&1 || true
# Render Visible V1 — lift_scene_state, worker_scene_state, render_budget,
# render_health, selected_floor_state_audit, worker_render_health.
python3 -m tower.qsb_render_visible_layer >/dev/null 2>&1 || true
# Floor 41 OANDA Full Trading Floor V1 — paper/practice only.
python3 -m tower.qsb_floor41_oanda >/dev/null 2>&1 || true
# Floor 42 Binance Department (testnet preview only)
python3 -m tower.qsb_floor42_binance >/dev/null 2>&1 || true
# Penthouse / Kernel Command (V1 reality fix) — gauges + zones + repair board
python3 -m tower.qsb_penthouse >/dev/null 2>&1 || true
# Floor 43 Stocks (paper preview only)
python3 -m tower.qsb_floor43_stocks >/dev/null 2>&1 || true
# Inter-floor sealed-packet bus (41/42/43 via lifts only)
python3 -m tower.qsb_floor_intercom_bus >/dev/null 2>&1 || true
# 3D Skyscraper V2 live state (lifts + workers + openclaw + pnl + intercom)
python3 -m tower.qsb_3d_skyscraper_state >/dev/null 2>&1 || true
# Full Skyscraper Occupancy + Commerce Wing V1 (1000 new workers)
python3 -m tower.qsb_skyscraper_occupancy all >/dev/null 2>&1 || true
# Completion engine — score + acceptance gates.
python3 -m tower.qsb_completion_engine 0 >/dev/null 2>&1 || true
# Live telemetry runs LAST so it picks up everything above.
python3 -m tower.qsb_dashboard_live_telemetry >/dev/null 2>&1 || true
# Auto-close evaluator — resolves open paper trades against strategy targets.
# Runs BEFORE F44 so the accounts roll-up reflects fresh closes.
python3 -m tower.qsb_auto_close_evaluator >/dev/null 2>&1 || true
# V17 — ops tick: maintenance + smoke-test workers do their per-launch work
python3 tools/qsb_ops_tick.py >/dev/null 2>&1 || true
# F30 Sentinels — continuous watchers over critical components.
# Always runs, always stamps to qsb_sentinels_report.json + activity tail.
python3 -m tower.qsb_sentinels >/dev/null 2>&1 || true
# Floor 44 — Accounts/PnL roll-up across F41/F42/F43 (runs after auto-close).
python3 -m tower.qsb_floor44_accounts >/dev/null 2>&1 || true
# Master audit refresh.
python3 -m tower.qsb_master_audit >/dev/null 2>&1 || true

# Launch
nohup python3 src/dashboard/server.py > "$LOG" 2>&1 &
NEW_PID=$!
echo "$NEW_PID" > "$PIDFILE"
sleep 1.0

# Verify it actually started
if ! kill -0 "$NEW_PID" 2>/dev/null; then
  echo "Dashboard failed to start. Log tail:"
  tail -40 "$LOG" 2>/dev/null
  exit 1
fi

# Best-effort readiness probe — non-fatal if curl is not installed.
for _ in 1 2 3 4 5 6 7 8; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "${URL}/api/unified" 2>/dev/null || echo "000")
  if [ "$CODE" = "200" ]; then break; fi
  sleep 0.5
done

echo "Dashboard started:"
echo "${URL}/?v=unified"
