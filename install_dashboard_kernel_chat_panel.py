from pathlib import Path
from datetime import datetime, timezone
import re
import py_compile

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SERVER = ROOT / "src/dashboard/server.py"

ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
backup = SERVER.with_suffix(f".py.backup_before_kernel_chat_panel_{ts}")
text = SERVER.read_text(encoding="utf-8")
backup.write_text(text, encoding="utf-8")
print("Backup:", backup)

# ─────────────────────────────────────────────────────────────
# 1. Create local-only kernel chat sidecar API server
# ─────────────────────────────────────────────────────────────

sidecar = ROOT / "src/tower/kernel_chat_sidecar.py"
sidecar.write_text(r'''#!/usr/bin/env python3
"""
QSB Tower V1.3 — Kernel Chat Sidecar API

Local-only browser bridge:
Dashboard browser -> localhost:8766 -> kernel_dialogue_adapter -> active QSB Kernel

Safety:
- No external providers.
- No OpenClaw execution.
- No worker dispatch.
- No autonomous dispatch.
- Local Ollama only through existing kernel dialogue adapter.
"""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from datetime import datetime, timezone
import json
import sys
import urllib.parse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
SRC = ROOT / "src"
LOG = ROOT / "data/logs/kernel_dialogue.jsonl"

sys.path.insert(0, str(SRC))

HOST = "127.0.0.1"
PORT = 8766


def load_json(path, fallback=None):
    if fallback is None:
        fallback = {}
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return fallback


def tail_jsonl(path, limit=20):
    p = Path(path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()[-limit:]
    out = []
    for line in lines:
        try:
            out.append(json.loads(line))
        except Exception:
            out.append({"raw": line})
    return out


def health_payload():
    activation = load_json(ROOT / "data/registries/kernel_activation_report.json")
    local_model = load_json(ROOT / "data/registries/local_model_inference_status.json")
    policy = load_json(ROOT / "data/registries/local_model_inference_policy.json")

    return {
        "ok": True,
        "service": "qsb_kernel_chat_sidecar",
        "ts": datetime.now(timezone.utc).isoformat(),
        "host": HOST,
        "port": PORT,
        "kernel_installed": activation.get("kernel_installed"),
        "QSBKernelCore_instantiated": activation.get("QSBKernelCore_instantiated"),
        "activation_status": activation.get("activation_status"),
        "active_kernel_source": activation.get("active_kernel_source"),
        "selected_model": policy.get("selected_model") or local_model.get("selected_model"),
        "local_model_inference_enabled": local_model.get("local_model_inference_enabled"),
        "ollama_detected": local_model.get("ollama_detected"),
        "worker_execution_enabled": False,
        "provider_execution_enabled": False,
        "external_provider_execution_enabled": False,
        "openclaw_execution_enabled": False,
        "live_dispatch_enabled": False,
        "autonomous_workers_enabled": False,
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "QSBKernelChatSidecar/1.0"

    def log_message(self, fmt, *args):
        # Keep terminal clean; requests are already logged by kernel_dialogue_adapter.
        return

    def _headers(self, code=200, content_type="application/json"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "http://127.0.0.1:8765")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _json(self, payload, code=200):
        self._headers(code)
        self.wfile.write(json.dumps(payload, indent=2, default=str).encode("utf-8"))

    def do_OPTIONS(self):
        self._headers(204)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/kernel_chat_health":
            self._json(health_payload())
            return

        if parsed.path == "/api/kernel_chat_history":
            self._json({
                "ok": True,
                "history": tail_jsonl(LOG, 30),
            })
            return

        self._json({"ok": False, "error": "not found", "path": parsed.path}, 404)

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path != "/api/kernel_chat":
            self._json({"ok": False, "error": "not found", "path": parsed.path}, 404)
            return

        try:
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            body = json.loads(raw or "{}")
            message = str(body.get("message", "")).strip()
            symbolic_only = bool(body.get("symbolic_only", False))

            if not message:
                self._json({"ok": False, "error": "empty message"}, 400)
                return

            from tower.kernel_dialogue_adapter import ask_kernel

            result = ask_kernel(message, prefer_local_model=not symbolic_only)

            # Add explicit sidecar safety confirmation.
            result["sidecar"] = {
                "service": "qsb_kernel_chat_sidecar",
                "local_only": True,
                "worker_execution_enabled": False,
                "provider_execution_enabled": False,
                "external_provider_execution_enabled": False,
                "openclaw_execution_enabled": False,
                "live_dispatch_enabled": False,
                "autonomous_workers_enabled": False,
            }

            self._json(result)
        except Exception as exc:
            self._json({
                "ok": False,
                "error": str(exc),
                "sidecar": "qsb_kernel_chat_sidecar",
            }, 500)


def main():
    print(f"QSB Kernel Chat Sidecar running at http://{HOST}:{PORT}")
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
''', encoding="utf-8")

# ─────────────────────────────────────────────────────────────
# 2. Create sidecar start/stop/status scripts
# ─────────────────────────────────────────────────────────────

scripts = ROOT / "scripts"
runtime = ROOT / "data/runtime"
logs = ROOT / "data/logs"
scripts.mkdir(exist_ok=True)
runtime.mkdir(parents=True, exist_ok=True)
logs.mkdir(parents=True, exist_ok=True)

(scripts / "run_kernel_chat_sidecar.sh").write_text(r'''#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1
export PYTHONPATH=/vaults/nvme0/qsb_tower_v1/src

PIDFILE="data/runtime/kernel_chat_sidecar.pid"
LOGFILE="data/logs/kernel_chat_sidecar.out"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Kernel chat sidecar already running: PID $(cat "$PIDFILE")"
  exit 0
fi

nohup python3 src/tower/kernel_chat_sidecar.py > "$LOGFILE" 2>&1 &
echo $! > "$PIDFILE"

sleep 1
echo "Kernel chat sidecar started: PID $(cat "$PIDFILE")"
echo "Health: http://127.0.0.1:8766/api/kernel_chat_health"
''', encoding="utf-8")

(scripts / "stop_kernel_chat_sidecar.sh").write_text(r'''#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/kernel_chat_sidecar.pid"

if [ -f "$PIDFILE" ]; then
  PID="$(cat "$PIDFILE")"
  if kill -0 "$PID" 2>/dev/null; then
    kill "$PID" || true
    sleep 1
  fi
  rm -f "$PIDFILE"
fi

echo "Kernel chat sidecar stopped."
''', encoding="utf-8")

(scripts / "kernel_chat_sidecar_status.sh").write_text(r'''#!/usr/bin/env bash
set -euo pipefail
cd /vaults/nvme0/qsb_tower_v1

PIDFILE="data/runtime/kernel_chat_sidecar.pid"

if [ -f "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE")" 2>/dev/null; then
  echo "Kernel chat sidecar running: PID $(cat "$PIDFILE")"
else
  echo "Kernel chat sidecar not running"
fi

curl -s http://127.0.0.1:8766/api/kernel_chat_health | python3 -m json.tool || true
''', encoding="utf-8")

for p in [
    scripts / "run_kernel_chat_sidecar.sh",
    scripts / "stop_kernel_chat_sidecar.sh",
    scripts / "kernel_chat_sidecar_status.sh",
]:
    p.chmod(0o755)

# ─────────────────────────────────────────────────────────────
# 3. Inject dashboard frontend chat panel
# ─────────────────────────────────────────────────────────────

snippet = r'''
<script id="qsb-kernel-chat-panel">
(function(){
  const API = 'http://127.0.0.1:8766';

  function el(tag, attrs={}, text=''){
    const node = document.createElement(tag);
    for(const [k,v] of Object.entries(attrs)){
      if(k === 'style') node.style.cssText = v;
      else if(k === 'class') node.className = v;
      else node.setAttribute(k,v);
    }
    if(text) node.textContent = text;
    return node;
  }

  function appendMsg(role, text){
    const log = document.getElementById('qsbKernelChatLog');
    if(!log) return;

    const wrap = el('div', {
      style: [
        'margin:7px 0',
        'padding:8px 10px',
        'border-radius:9px',
        'white-space:pre-wrap',
        'line-height:1.35',
        'border:1px solid ' + (role === 'user' ? 'rgba(106,184,255,.35)' : 'rgba(77,255,176,.35)'),
        'background:' + (role === 'user' ? 'rgba(20,45,75,.65)' : 'rgba(10,55,35,.65)'),
        'color:#d8eaff'
      ].join(';')
    });

    const head = el('div', {
      style:'font-size:10px;font-weight:800;letter-spacing:.5px;margin-bottom:4px;color:' + (role === 'user' ? '#6ab8ff' : '#4dffb0')
    }, role === 'user' ? 'ROSS' : 'QSB KERNEL');

    const body = el('div', {}, text);
    wrap.appendChild(head);
    wrap.appendChild(body);
    log.appendChild(wrap);
    log.scrollTop = log.scrollHeight;
  }

  async function refreshKernelChatHealth(){
    const status = document.getElementById('qsbKernelChatStatus');
    if(!status) return;

    try{
      const res = await fetch(API + '/api/kernel_chat_health?t=' + Date.now(), {cache:'no-store'});
      const data = await res.json();

      if(data.ok && data.kernel_installed && data.activation_status === 'active_local_only'){
        status.textContent = `ACTIVE LOCAL — ${data.selected_model || 'symbolic'} — locks closed`;
        status.style.color = '#4dffb0';
      }else{
        status.textContent = 'NOT READY';
        status.style.color = '#ff6060';
      }
    }catch(e){
      status.textContent = 'CHAT SIDECAR OFFLINE';
      status.style.color = '#ffaa50';
    }
  }

  async function sendKernelChat(){
    const input = document.getElementById('qsbKernelChatInput');
    const btn = document.getElementById('qsbKernelChatSend');
    if(!input || !btn) return;

    const message = input.value.trim();
    if(!message) return;

    input.value = '';
    appendMsg('user', message);

    btn.disabled = true;
    btn.textContent = 'Thinking…';

    try{
      const res = await fetch(API + '/api/kernel_chat', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body:JSON.stringify({message})
      });
      const data = await res.json();

      if(data.ok){
        appendMsg('kernel', data.reply || JSON.stringify(data, null, 2));
      }else{
        appendMsg('kernel', 'Kernel chat error: ' + (data.error || JSON.stringify(data)));
      }
    }catch(e){
      appendMsg('kernel', 'Kernel chat sidecar is offline. Run: ./scripts/run_kernel_chat_sidecar.sh');
    }finally{
      btn.disabled = false;
      btn.textContent = 'Send';
      refreshKernelChatHealth();
    }
  }

  function createPanel(){
    if(document.getElementById('qsbKernelChatPanel')) return;

    const panel = el('div', {
      id:'qsbKernelChatPanel',
      style:[
        'position:fixed',
        'right:18px',
        'bottom:58px',
        'width:460px',
        'max-width:calc(100vw - 110px)',
        'height:430px',
        'z-index:99998',
        'display:flex',
        'flex-direction:column',
        'background:rgba(4,12,24,.96)',
        'border:1px solid rgba(77,255,176,.45)',
        'box-shadow:0 0 24px rgba(77,255,176,.20)',
        'border-radius:14px',
        'overflow:hidden',
        'font-family:Segoe UI,system-ui,Arial,sans-serif'
      ].join(';')
    });

    const header = el('div', {
      style:[
        'display:flex',
        'align-items:center',
        'justify-content:space-between',
        'padding:10px 12px',
        'background:rgba(5,35,25,.95)',
        'border-bottom:1px solid rgba(77,255,176,.35)'
      ].join(';')
    });

    const title = el('div', {}, '');
    title.innerHTML = '<div style="font-weight:900;color:#4dffb0;letter-spacing:.4px">QSB Kernel Chat</div><div id="qsbKernelChatStatus" style="font-size:11px;color:#ffaa50;margin-top:2px">checking…</div>';

    const buttons = el('div', {style:'display:flex;gap:6px'});
    const mini = el('button', {
      style:'background:#071528;color:#d8eaff;border:1px solid #1a3a5c;border-radius:8px;padding:5px 8px;cursor:pointer'
    }, 'Hide');

    mini.onclick = function(){
      const body = document.getElementById('qsbKernelChatBody');
      if(!body) return;
      const hidden = body.style.display === 'none';
      body.style.display = hidden ? 'flex' : 'none';
      panel.style.height = hidden ? '430px' : '54px';
      mini.textContent = hidden ? 'Hide' : 'Show';
    };

    buttons.appendChild(mini);
    header.appendChild(title);
    header.appendChild(buttons);

    const body = el('div', {
      id:'qsbKernelChatBody',
      style:'display:flex;flex-direction:column;min-height:0;flex:1'
    });

    const log = el('div', {
      id:'qsbKernelChatLog',
      style:[
        'flex:1',
        'overflow:auto',
        'padding:10px',
        'background:linear-gradient(180deg,rgba(5,18,34,.88),rgba(4,12,24,.88))',
        'font-size:12px'
      ].join(';')
    });

    const inputWrap = el('div', {
      style:'display:flex;gap:8px;padding:10px;border-top:1px solid rgba(77,255,176,.25);background:rgba(5,15,28,.96)'
    });

    const input = el('textarea', {
      id:'qsbKernelChatInput',
      rows:'2',
      placeholder:'Speak to the active local-only QSB Kernel…',
      style:[
        'flex:1',
        'resize:none',
        'border-radius:9px',
        'border:1px solid #1a3a5c',
        'background:#061120',
        'color:#d8eaff',
        'padding:8px',
        'outline:none',
        'font-size:12px'
      ].join(';')
    });

    input.addEventListener('keydown', function(e){
      if(e.key === 'Enter' && !e.shiftKey){
        e.preventDefault();
        sendKernelChat();
      }
    });

    const send = el('button', {
      id:'qsbKernelChatSend',
      style:[
        'width:76px',
        'border-radius:9px',
        'border:1px solid rgba(77,255,176,.55)',
        'background:rgba(10,80,50,.8)',
        'color:#4dffb0',
        'font-weight:900',
        'cursor:pointer'
      ].join(';')
    }, 'Send');

    send.onclick = sendKernelChat;

    inputWrap.appendChild(input);
    inputWrap.appendChild(send);
    body.appendChild(log);
    body.appendChild(inputWrap);
    panel.appendChild(header);
    panel.appendChild(body);
    document.body.appendChild(panel);

    appendMsg('kernel', 'Kernel chat panel online. Local-only route active. Workers, external providers, OpenClaw execution, and autonomous dispatch remain disabled.');
    refreshKernelChatHealth();
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', createPanel);
  }else{
    createPanel();
  }

  setInterval(refreshKernelChatHealth, 5000);
})();
</script>
'''

# Remove previous copy if present.
text = re.sub(
    r'\n?<script id="qsb-kernel-chat-panel">.*?</script>\n?',
    "\n",
    text,
    flags=re.S,
)

if "</body>" in text:
    text = text.replace("</body>", snippet + "\n</body>", 1)
elif "</html>" in text:
    text = text.replace("</html>", snippet + "\n</html>", 1)
else:
    raise SystemExit("Could not find </body> or </html> insertion point.")

SERVER.write_text(text, encoding="utf-8")
py_compile.compile(str(SERVER), doraise=True)
py_compile.compile(str(sidecar), doraise=True)

print("Installed dashboard kernel chat panel.")
print("Sidecar:", sidecar)
print("server.py compiles cleanly.")
