#!/usr/bin/env bash
# qsb_unreal_visible_build_status.sh — report whether UE editor + plugin + dashboards are live.
# Writes data/registries/qsb_unreal_visible_build_loop_status.json

set -u
ROOT="${ROOT:-/vaults/nvme0/qsb_tower_v1}"
cd "$ROOT" || exit 1
TS_UTC=$(date -u +%Y-%m-%dT%H:%M:%SZ)
mkdir -p data/registries data/logs

editor_pid=$(pgrep -f 'UnrealEditor.*QSB_Skyscraper.uproject' | head -1 || true)
tcp_listen=$(ss -tnlp 2>/dev/null | grep -c ':55557 ')
ue_log=/tmp/qsb_skyscraper_editor.log
dash_8847=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8847/ 2>/dev/null || echo 000)
dash_8849=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8849/ 2>/dev/null || echo 000)
live_pulse_pid=$(pgrep -f 'qsb_ue5_live_pulse.py' | head -1 || true)

# Count actors via TCP if listening
actor_count="unknown"
if [[ "$tcp_listen" -gt 0 ]]; then
  actor_count=$(.venv/bin/python3 -c "
import socket,json,sys
try:
    s=socket.socket(); s.settimeout(8); s.connect(('127.0.0.1',55557))
    s.sendall(json.dumps({'type':'get_actors_in_level','params':{}}).encode())
    buf=b''
    while True:
        c=s.recv(65536)
        if not c: break
        buf+=c
        try:
            r=json.loads(buf.decode())
            print(len(r['result']['actors'])); break
        except: pass
except Exception as e:
    print('err:'+str(e)[:60])
" 2>/dev/null || echo "tcp_err")
fi

out=data/registries/qsb_unreal_visible_build_loop_status.json
cat > "$out" <<EOF
{
  "ts": "${TS_UTC}",
  "editor_pid": "${editor_pid:-none}",
  "tcp_55557_listening": ${tcp_listen},
  "ue_editor_log": "${ue_log}",
  "actor_count_in_level": "${actor_count}",
  "live_pulse_pid": "${live_pulse_pid:-none}",
  "dashboard_8847_http": "${dash_8847}",
  "dashboard_8849_http": "${dash_8849}"
}
EOF
cat "$out"
