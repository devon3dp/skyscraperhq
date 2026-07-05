#!/usr/bin/env bash
# Daily cadence — meant for cron / systemd-user timer. Runs ONE tick + learning + proof + stamp.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
./scripts/qsb_team_tick.sh >> data/logs/qsb_team_daemon.log 2>&1
./scripts/qsb_team_learning_tick.sh >> data/logs/qsb_team_daemon.log 2>&1 || true
./scripts/qsb_team_prove_full_system.sh >> data/logs/qsb_team_daemon.log 2>&1 || true
echo "[$TS] daily cadence done"
