#!/usr/bin/env bash
# Cinematic camera + screenshot, output goes to data/screenshots/unreal_cinematic_build/<ts>.png
set -u
cd /vaults/nvme0/qsb_tower_v1 || exit 1
TS=$(date -u +%Y%m%dT%H%M%SZ)
OUT_DIR=data/screenshots/unreal_cinematic_build
mkdir -p "$OUT_DIR"
OUT="$OUT_DIR/cinematic_${TS}.png"

# Move viewport to cinematic hero-shot location
.venv/bin/python3 -c "
import socket,json
def send(cmd,p,t=10):
    s=socket.socket(); s.settimeout(t); s.connect(('127.0.0.1',55557))
    s.sendall(json.dumps({'type':cmd,'params':p}).encode())
    buf=b''
    while True:
        c=s.recv(65536)
        if not c: break
        buf+=c
        try: return json.loads(buf.decode())
        except: pass
print(send('focus_viewport', {'location':[0,0,2500.0], 'distance':14000.0, 'orientation':[-15.0, 30.0, 0.0]}))
"
sleep 2
WID=$(DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool search --name "QSB_Skyscraper" 2>/dev/null | head -1)
if [[ -n "$WID" ]]; then
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool windowactivate "$WID"
  # click+End to force viewport focus
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool mousemove 666 432
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool click 1
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority xdotool key End
  sleep 1
  DISPLAY=:0 XAUTHORITY=/run/user/$(id -u)/gdm/Xauthority scrot -u -o "$OUT"
fi
echo "$OUT"
ls -la "$OUT" 2>/dev/null
