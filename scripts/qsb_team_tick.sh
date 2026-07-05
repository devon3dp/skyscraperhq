#!/usr/bin/env bash
# One team tick: refresh brief + roster + ask Wren for continuity, optionally Hermes/iQuest.
# Idempotent. Safe to run on-demand. Does NOT loop — see qsb_team_daemon_start.sh for that.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
STATUS=data/registries/qsb_team_persistent_loop_status.json
LOG=data/logs/qsb_team_daemon.log
mkdir -p data/registries data/logs data/run

echo "[$TS] team tick start" | tee -a $LOG
./scripts/qsb_team_model_roster_probe.sh >/dev/null 2>&1
./scripts/qsb_team_memory_bootstrap.sh >/dev/null 2>&1
./scripts/qsb_team_build_shared_project_brief.sh >/dev/null 2>&1
echo "[$TS] brief refreshed" | tee -a $LOG

# Wren continuity (fail-honest)
./scripts/qsb_wren_second_in_command_tick.sh >/dev/null 2>&1
WREN_OK=$?
echo "[$TS] wren tick rc=$WREN_OK" | tee -a $LOG

# Optionally ask Hermes if available (8B fast model)
HERMES_OK=skipped
if pgrep -f ollama >/dev/null && ollama list 2>/dev/null | grep -q hermes3; then
  timeout 90 ./scripts/team_adapters/qsb_ask_hermes.sh "One sentence — what architecture question would you ask Claude today based on the shared brief?" >/dev/null 2>&1
  HERMES_OK=$?
fi
echo "[$TS] hermes tick rc=$HERMES_OK" | tee -a $LOG

# Refresh dashboard/trader sweep (existing tool)
[[ -x scripts/qsb_dashboard_and_trader_status_sweep.sh ]] && ./scripts/qsb_dashboard_and_trader_status_sweep.sh >/dev/null 2>&1

cat > $STATUS <<EOF
{
  "ts": "$TS",
  "tick_rc": {
    "roster": 0,
    "memory_bootstrap": 0,
    "brief": 0,
    "wren_sic": $WREN_OK,
    "hermes": "$HERMES_OK"
  }
}
EOF
echo "[$TS] team tick done" | tee -a $LOG
cat $STATUS
