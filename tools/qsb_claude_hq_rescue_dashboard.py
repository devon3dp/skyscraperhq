#!/usr/bin/env python3
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from datetime import datetime, timezone
import json
import urllib.request
import urllib.error
from urllib.parse import urlparse

PROJECT = Path("/vaults/nvme0/qsb_tower_v1")
REG = PROJECT / "data" / "registries"

def now():
    return datetime.now(timezone.utc).isoformat()

def get_json(url, timeout=4):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
            try:
                return {"ok": True, "http": r.status, "data": json.loads(raw)}
            except Exception:
                return {"ok": True, "http": r.status, "raw": raw[:2000]}
    except Exception as e:
        return {"ok": False, "error": repr(e)}

def status():
    return {
        "ok": True,
        "service": "Claude HQ Rescue Dashboard",
        "name": "Claude HQ",
        "port": 8850,
        "ts": now(),
        "role": "HQ dashboard shell and service health view. This is not a Claude API fallback brain.",
        "doctrine": {
            "claude_hq_name": "Claude HQ",
            "ceos_use": "API Gene Pool only",
            "wren_fallback": "blocked",
            "no_key_changes": True,
            "no_trading": True,
        },
        "links": {
            "boardroom": "http://127.0.0.1:8852/ipad",
            "gene_pool": "http://127.0.0.1:8860/",
            "tasks": "http://127.0.0.1:8852/tasks",
            "town_square": "http://127.0.0.1:8852/town_square",
        },
        "boardroom_link_health": get_json("http://127.0.0.1:8852/link_health"),
        "gene_pool_live": get_json("http://127.0.0.1:8860/api/live"),
    }

def html():
    return """<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Claude HQ · Rescue Dashboard</title>
<style>
body{margin:0;background:#07111f;color:#e8f7ff;font:14px system-ui,-apple-system,Segoe UI,sans-serif}
header{padding:18px 20px;background:#0d213a;border-bottom:1px solid #25527e}
h1{margin:0;font-size:25px}.sub{opacity:.75;margin-top:4px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;padding:14px}
.card{background:#0b1728;border:1px solid #244766;border-radius:16px;padding:14px}
.k{opacity:.7;text-transform:uppercase;font-size:12px;letter-spacing:.08em}.v{font-size:26px;font-weight:800;margin-top:6px}
a{color:#67e8f9}pre{white-space:pre-wrap;background:#020712;border:1px solid #1d3552;border-radius:14px;padding:12px;max-height:460px;overflow:auto}
</style></head>
<body>
<header><h1>🧠 Claude HQ · Rescue Dashboard</h1>
<div class=sub>HQ dashboard service on 8850 · Brain Router remains API Gene Pool only · no Wren fallback</div></header>
<section class=grid>
<div class=card><div class=k>service</div><div class=v>LIVE</div></div>
<div class=card><div class=k>Brain Router</div><div class=v id=router>…</div></div>
<div class=card><div class=k>Boardroom</div><div class=v id=boardroom>…</div></div>
<div class=card><div class=k>Doctrine</div><div class=v>LOCKED</div></div>
</section>
<section class=grid>
<div class=card><b>Links</b><br>
<a href="http://127.0.0.1:8852/ipad">Boardroom iPad</a><br>
<a href="http://127.0.0.1:8852/tasks">Task Council</a><br>
<a href="http://127.0.0.1:8852/town_square">Town Square</a><br>
<a href="http://127.0.0.1:8860/">Gene Pool Router</a>
</div>
<div class=card style="grid-column:1/-1"><b>Live status</b><pre id=raw>loading…</pre></div>
</section>
<script>
async function tick(){
  try{
    const r=await fetch('/api/status',{cache:'no-store'});
    const d=await r.json();
    router.textContent = d.gene_pool_live?.ok ? 'LIVE' : 'DOWN';
    boardroom.textContent = d.boardroom_link_health?.ok ? 'LIVE' : 'CHECK';
    raw.textContent=JSON.stringify(d,null,2);
  }catch(e){raw.textContent='status error: '+e}
}
tick(); setInterval(tick,2000);
</script>
</body></html>"""

class H(BaseHTTPRequestHandler):
    server_version = "ClaudeHQRescue/1.0"

    def send_body(self, code, body, ctype="application/json; charset=utf-8"):
        raw = body.encode("utf-8") if isinstance(body, str) else json.dumps(body, indent=2, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except BrokenPipeError:
            pass

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/dashboard", "/hq"):
            return self.send_body(200, html(), "text/html; charset=utf-8")
        if p in ("/health", "/api/status"):
            return self.send_body(200, status())
        return self.send_body(404, {"ok": False, "error": "not found", "path": p}, "application/json; charset=utf-8")

if __name__ == "__main__":
    print("[BOOT] Claude HQ Rescue Dashboard on 0.0.0.0:8850", flush=True)
    ThreadingHTTPServer(("0.0.0.0", 8850), H).serve_forever()
