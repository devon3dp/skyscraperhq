#!/usr/bin/env bash
# Per Ross 2026-06-25: hourly memory write for every team member.
# Run via cron or systemd timer every hour.
cd /vaults/nvme0/qsb_tower_v1
python3 tools/qsb_team_memory.py all write_hourly
HOUR=$(date -u +%H)
if [ "$HOUR" = "23" ]; then
    python3 tools/qsb_team_memory.py all write_daily
    for m in openai deepseek; do
        python3 tools/qsb_team_memory.py "$m" inject_provider_header \
            --output "data/registries/team_memory/${m}/header_latest.txt"
    done
fi
# cleanup hourly files older than 48h
find data/registries/team_memory/*/hourly/ -name "hourly_*.md" -mmin +2880 -delete 2>/dev/null || true
