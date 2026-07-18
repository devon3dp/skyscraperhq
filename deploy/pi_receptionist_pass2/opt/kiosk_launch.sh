#!/bin/bash
# QSB Receptionist kiosk launcher — Pass 2.
# Waits for network, tries each dashboard URL, falls back to local HTML.
# Runs inside the autologin desktop (labwc/wayfire) session as user ross.
set -u
ENVF=/opt/skyscraper_receptionist/receptionist.env
[ -f "$ENVF" ] && . "$ENVF"
HQ_HOST="${HQ_HOST:-172.20.10.2}"
LOCAL_HTML=/opt/skyscraper_receptionist/receptionist_local.html
LOG=/opt/skyscraper_receptionist/kiosk.log
echo "$(date -Is) kiosk_launch start HQ_HOST=$HQ_HOST" >> "$LOG"

# Single-instance guard: if a kiosk chromium is already running, do nothing.
if pgrep -f 'chromium.*--kiosk' >/dev/null 2>&1; then
  echo "$(date -Is) kiosk already running — exit" >> "$LOG"; exit 0
fi

# Start on-screen keyboard if one is present (Wayland: squeekboard; fallbacks).
for osk in squeekboard wvkbd-mobintl "matchbox-keyboard --daemon" onboard; do
  bin=$(echo "$osk" | awk '{print $1}')
  if command -v "$bin" >/dev/null 2>&1; then ( $osk & ) ; echo "$(date -Is) OSK: $osk" >> "$LOG"; break; fi
done

pick_url() {
  URLS="${KIOSK_URLS:-http://$HQ_HOST:8852/ http://$HQ_HOST:8852/tasks http://$HQ_HOST:8860/}"
  for u in $URLS; do
    if curl -s -o /dev/null --max-time 4 "$u" 2>/dev/null; then echo "$u"; return 0; fi
  done
  return 1
}

# Wait up to ~12s for a dashboard to answer, else show the local fallback page
# FAST (so the screen is never blank). Kiosk keeps the local page if HQ is down.
URL=""
for i in $(seq 1 6); do
  if URL=$(pick_url); then break; fi
  sleep 2
done
[ -z "$URL" ] && URL="file://$LOCAL_HTML"
echo "$(date -Is) kiosk URL=$URL" >> "$LOG"

# Pick a chromium binary.
CHROME=""
for c in chromium-browser chromium chromium-bin; do
  command -v "$c" >/dev/null 2>&1 && { CHROME="$c"; break; }
done
if [ -z "$CHROME" ]; then
  echo "$(date -Is) NO chromium found — cannot open kiosk" >> "$LOG"
  exit 1
fi

exec "$CHROME" \
  --kiosk --noerrdialogs --disable-infobars --no-first-run \
  --disable-session-crashed-bubble --disable-pinch \
  --check-for-update-interval=31536000 \
  --ozone-platform-hint=auto \
  --start-fullscreen \
  "$URL"
