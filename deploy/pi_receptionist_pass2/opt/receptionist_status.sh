#!/bin/bash
# QSB Receptionist — status dump for Ross (SSH-friendly).
ENVF=/opt/skyscraper_receptionist/receptionist.env
[ -f "$ENVF" ] && . "$ENVF"
HQ_HOST="${HQ_HOST:-172.20.10.2}"
echo "=========== QSB RECEPTIONIST STATUS $(date -Is) ==========="
echo "hostname   : $(hostname)"
echo "IP address : $(hostname -I 2>/dev/null)"
echo "--- Wi-Fi ---"
(nmcli -t -f ACTIVE,SSID,SIGNAL dev wifi 2>/dev/null | grep '^yes' ) || iwgetid 2>/dev/null || echo "wifi tool n/a"
echo "HQ_HOST    : $HQ_HOST"
echo "--- dashboard reachability ---"
for u in "http://$HQ_HOST:8852/" "http://$HQ_HOST:8852/tasks" "http://$HQ_HOST:8860/" "http://$HQ_HOST:8851/"; do
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 4 "$u" 2>/dev/null)
  echo "  $u -> ${code:-timeout}"
done
echo "--- Pico ---"
lsusb 2>/dev/null | grep -qiE '2e8a|pico' && echo "Pico detected: YES" || echo "Pico detected: no"
echo "--- SSK ---"
lsblk -dn -o MODEL 2>/dev/null | grep -qiE 'ssk|ssm|nas' && echo "SSK detected: YES" || echo "SSK detected: no"
echo "--- display / rotation ---"
(cat /sys/class/drm/*/status 2>/dev/null | sort | uniq -c) || echo "no drm info"
grep -E '^display_rotate|^dtoverlay=.*rotate|rotate' /boot/firmware/config.txt 2>/dev/null || echo "no rotation set in config.txt"
echo "--- failed services ---"
systemctl --failed --no-legend 2>/dev/null || echo "(need systemd)"
echo "--- kiosk service ---"
systemctl status qsb-reception-kiosk --no-pager 2>/dev/null | head -6 || echo "kiosk service not found (may launch via desktop autostart)"
echo "=========================================================="
