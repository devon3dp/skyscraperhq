#!/usr/bin/env bash
# QSB Paper Strategy Tick — cadence-driven paper-only.
# Phase: QSB_NEXT_SAFE_IMPROVEMENTS_V1
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
# Advance cadence first so the tick count grows.
python3 -m tower.eqsb_cadence >/dev/null 2>&1 || true
# Then run the paper strategy tick (deterministic, no random).
python3 -m tower.qsb_paper_strategy_runner
# Re-derive movements/tasks/lift-state from the new ticks.
python3 -m tower.qsb_live_telemetry_repairs >/dev/null 2>&1 || true
python3 -m tower.qsb_dashboard_rebuild_v1 >/dev/null 2>&1 || true
python3 -m tower.qsb_dashboard_live_telemetry >/dev/null 2>&1 || true
