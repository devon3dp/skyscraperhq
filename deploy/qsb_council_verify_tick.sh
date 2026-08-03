#!/bin/bash
# QSB autonomous evolution tick (bounded): Wren + Bill independently verify up to
# N green proposals; on both-approve the applier applies the signed ones.
# SAFETY: both minds required (3 unique-class sigs), sandbox-green precondition,
# SAFETY_PATHS (oanda/vault/.env/CLAUDE.md/gate) refused, backup+py_compile+rollback.
# KILL SWITCH: set data/registries/qsb_proposal_autoapply_gate.json enabled=false
#             → verify + apply both no-op immediately.
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
LOG=data/registries/qsb_council_verify_tick.log
echo "=== tick $(date -u +%Y-%m-%dT%H:%M:%SZ) ===" >> "$LOG"
/usr/bin/python3 tools/qsb_council_verify_signoff.py --limit 3 >> "$LOG" 2>&1 || echo "verify rc=$?" >> "$LOG"
/usr/bin/python3 tools/qsb_proposal_applier.py           >> "$LOG" 2>&1 || echo "apply rc=$?"  >> "$LOG"
# Autonomous TASK sign-off (Ross 2026-08-03): Wren + Bill independently verify
# tasks waiting on a human accept; BOTH approve → the task advances with no Ross
# gate. Same kill switch. Bounded to 2/tick so a slow Bill round-trip never piles up.
/usr/bin/python3 tools/qsb_council_verify_signoff.py --tasks --limit 2 >> "$LOG" 2>&1 || echo "tasks rc=$?" >> "$LOG"
