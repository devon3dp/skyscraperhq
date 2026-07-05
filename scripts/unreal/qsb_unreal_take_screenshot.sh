#!/usr/bin/env bash
# Capture UE editor window via scrot (uses focused-window mode; falls back to engine plugin).
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
OUT_DIR=data/screenshots/unreal_cli_driver
mkdir -p "$OUT_DIR"
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT="${1:-$OUT_DIR/screenshot_${TS}.png}"

WID=$(DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool search --name "QSB_Skyscraper" 2>/dev/null | head -1)
if [[ -n "$WID" ]]; then
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool windowactivate "$WID" >/dev/null
  sleep 0.5
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority scrot -u -o "$OUT" 2>/dev/null
  echo "$OUT"
  exit 0
fi
# fallback: plugin take_screenshot (may serve stale buffer — last resort)
.venv/bin/python3 -c "
import socket,json
s=socket.socket(); s.settimeout(15); s.connect(('127.0.0.1',55557))
s.sendall(json.dumps({'type':'take_screenshot','params':{'filepath':'$OUT'}}).encode())
buf=b''
while True:
    c=s.recv(65536)
    if not c: break
    buf+=c
    try: print(json.loads(buf.decode())); break
    except: pass
" 2>&1 | head -3
echo "$OUT"
