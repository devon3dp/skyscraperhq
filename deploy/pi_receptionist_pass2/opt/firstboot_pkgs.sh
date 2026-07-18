#!/bin/bash
# QSB Receptionist first-boot package top-up. Runs ONCE when the network is up,
# installs an on-screen keyboard + chromium + helpers IF they are missing, then
# disables itself. No keyboard required — fully automatic.
set -u
LOG=/opt/skyscraper_receptionist/firstboot_pkgs.log
STAMP=/opt/skyscraper_receptionist/.pkgs_done
echo "$(date -Is) firstboot_pkgs start" >> "$LOG"
[ -f "$STAMP" ] && { echo "already done" >> "$LOG"; exit 0; }

# Wait up to 3 min for internet.
ok=0
for i in $(seq 1 36); do
  if curl -s -o /dev/null --max-time 5 http://deb.debian.org 2>/dev/null \
     || ping -c1 -W2 1.1.1.1 >/dev/null 2>&1; then ok=1; break; fi
  sleep 5
done
if [ "$ok" != 1 ]; then
  echo "$(date -Is) no internet — will retry next boot" >> "$LOG"; exit 0
fi

need=()
command -v chromium-browser >/dev/null 2>&1 || command -v chromium >/dev/null 2>&1 || need+=(chromium-browser)
# On-screen keyboard: prefer squeekboard (Wayland), fallback matchbox-keyboard.
if ! command -v squeekboard >/dev/null 2>&1 && ! command -v matchbox-keyboard >/dev/null 2>&1; then
  need+=(squeekboard matchbox-keyboard)
fi
command -v wlr-randr >/dev/null 2>&1 || need+=(wlr-randr)
command -v unclutter >/dev/null 2>&1 || need+=(unclutter)

if [ ${#need[@]} -gt 0 ]; then
  echo "$(date -Is) installing: ${need[*]}" >> "$LOG"
  export DEBIAN_FRONTEND=noninteractive
  apt-get update >> "$LOG" 2>&1
  apt-get install -y "${need[@]}" >> "$LOG" 2>&1 || echo "some pkgs failed (chromium may be 'chromium' not 'chromium-browser')" >> "$LOG"
  # Debian trixie names it 'chromium'; try that too.
  command -v chromium-browser >/dev/null 2>&1 || command -v chromium >/dev/null 2>&1 || apt-get install -y chromium >> "$LOG" 2>&1
fi

touch "$STAMP"
systemctl disable qsb-reception-firstboot-pkgs.service 2>/dev/null
echo "$(date -Is) firstboot_pkgs done" >> "$LOG"
