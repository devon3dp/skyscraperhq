#!/bin/bash
# QSB Receptionist — rotate the touchscreen 180 (upside-down fix).
# Handles both KMS (config.txt video=) and desktop (labwc/wayfire) rotation.
set -u
CFG=/boot/firmware/config.txt
[ -f "$CFG" ] || CFG=/boot/config.txt
echo "Setting 180-degree rotation..."

# 1) KMS console rotation via config.txt (applies at boot, before desktop).
if ! grep -q '^# QSB rotation' "$CFG" 2>/dev/null; then
  echo "" | sudo tee -a "$CFG" >/dev/null
  echo "# QSB rotation" | sudo tee -a "$CFG" >/dev/null
fi
# Legacy (fkms) fallback:
sudo sed -i '/^display_rotate=/d' "$CFG" 2>/dev/null
echo "display_rotate=2" | sudo tee -a "$CFG" >/dev/null

# 2) Desktop (Wayland) live rotation if a compositor is running.
if command -v wlr-randr >/dev/null 2>&1; then
  OUT=$(wlr-randr 2>/dev/null | awk 'NR==1{print $1}')
  [ -n "$OUT" ] && wlr-randr --output "$OUT" --transform 180 2>/dev/null && echo "live-rotated $OUT 180"
fi
echo "Done. Reboot to apply the boot-time rotation:  sudo reboot"
