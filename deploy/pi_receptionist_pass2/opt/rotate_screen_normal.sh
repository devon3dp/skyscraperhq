#!/bin/bash
# QSB Receptionist — restore normal (0-degree) screen rotation.
set -u
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
echo "Restoring normal rotation..."
sudo sed -i '/^display_rotate=/d' "$CFG" 2>/dev/null
echo "display_rotate=0" | sudo tee -a "$CFG" >/dev/null
if command -v wlr-randr >/dev/null 2>&1; then
  OUT=$(wlr-randr 2>/dev/null | awk 'NR==1{print $1}')
  [ -n "$OUT" ] && wlr-randr --output "$OUT" --transform normal 2>/dev/null && echo "live-rotated $OUT normal"
fi
echo "Done. Reboot to apply:  sudo reboot"
