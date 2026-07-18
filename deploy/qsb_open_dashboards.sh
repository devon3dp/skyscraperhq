#!/usr/bin/env bash
# Opens the SkyscraperHQ dashboards in a browser on the PC desktop at login (Ross 2026-07-09).
# Waits for the boardroom hub to be up first (services autostart via cron @reboot + watchdog).
export DISPLAY="${DISPLAY:-:0}"
LOG=/vaults/nvme0/qsb_tower_v1/logs/dashboards/open_dashboards.log
mkdir -p "$(dirname "$LOG")"
echo "=== open dashboards $(date) ===" >>"$LOG"
for i in $(seq 1 60); do
  if curl -s -m3 -o /dev/null -w '%{http_code}' http://127.0.0.1:8852/quad_monitor 2>/dev/null | grep -q 200; then break; fi
  sleep 3
done
# open the 4x wall fullscreen (the "everyone present" view)
setsid google-chrome --new-window --start-fullscreen "http://127.0.0.1:8852/quad_monitor" >>"$LOG" 2>&1 &
echo "opened quad_monitor $(date)" >>"$LOG"
