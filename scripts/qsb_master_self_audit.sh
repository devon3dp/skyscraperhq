#!/usr/bin/env bash
# QSB Master Self-Audit + Repair Roadmap
# Phase: QSB_MASTER_SYSTEM_SELF_AUDIT_AND_REPAIR_ROADMAP_V1
# Truthful, read-only audit. No rebuild.
set -uo pipefail
cd /vaults/nvme0/qsb_tower_v1
# shellcheck disable=SC1091
source scripts/qsb_env.sh
exec python3 -m tower.qsb_master_audit "$@"
