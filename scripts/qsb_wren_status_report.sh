#!/usr/bin/env bash
# Show the latest Wren second-in-command outputs.
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
echo "=== Wren second-in-command status ==="
cat data/registries/qsb_wren_second_in_command_status.json 2>/dev/null || echo "(no status — run qsb_wren_second_in_command_tick.sh)"
echo ""
echo "=== Wren continuity report (tail) ==="
tail -40 data/team_memory/wren/wren_continuity_report.md 2>/dev/null || echo "(no continuity report yet)"
