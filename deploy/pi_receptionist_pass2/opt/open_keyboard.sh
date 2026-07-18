#!/bin/bash
# QSB Receptionist — "Open Keyboard" button. Launches whatever OSK is present.
for osk in "squeekboard" "wvkbd-mobintl -L 280" "matchbox-keyboard" "onboard"; do
  bin=$(echo "$osk" | awk '{print $1}')
  if command -v "$bin" >/dev/null 2>&1; then
    exec $osk
  fi
done
# None installed — tell the user (uses a GUI dialog if available).
MSG="No on-screen keyboard is installed yet. Connect to Wi-Fi, then run:  sudo apt-get install -y squeekboard matchbox-keyboard"
if command -v zenity >/dev/null 2>&1; then zenity --info --text="$MSG"; else echo "$MSG"; fi
