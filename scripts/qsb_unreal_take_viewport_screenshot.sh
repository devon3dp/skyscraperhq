#!/usr/bin/env bash
# qsb_unreal_take_viewport_screenshot.sh [out.png]
# Takes a screenshot of the focused UE editor window via scrot, falls back to engine plugin take_screenshot.

set -u
OUT="${1:-/tmp/qsb_viewport_$(date -u +%Y%m%dT%H%M%SZ).png}"
WID=$(DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool search --name "QSB_Skyscraper" 2>/dev/null | head -1)

if [[ -n "$WID" ]]; then
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool windowactivate "$WID"
  sleep 1
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority scrot -u -o "$OUT"
  if [[ -s "$OUT" ]]; then echo "scrot ok: $OUT"; exit 0; fi
fi

# Fallback: plugin take_screenshot (note: caches buffer, may be stale)
/vaults/nvme0/qsb_tower_v1/.venv/bin/python3 -c "
import socket,json
s=socket.socket(); s.settimeout(15); s.connect(('127.0.0.1',55557))
s.sendall(json.dumps({'type':'take_screenshot','params':{'filepath':'${OUT}'}}).encode())
buf=b''
while True:
    c=s.recv(65536)
    if not c: break
    buf+=c
    try: r=json.loads(buf.decode()); print(r); break
    except: pass
"
ls -l "$OUT" 2>/dev/null || echo "no screenshot produced"
