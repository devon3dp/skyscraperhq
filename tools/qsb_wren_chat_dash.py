#!/usr/bin/env python3
"""
qsb_wren_chat_dash.py — a clean, focused "TALK TO WREN" dashboard (2026-07-21, Ross:
"i need a new dash for wren so i can talk to her").

This is NOT a new Wren and NOT a rebuild of her mind. It is a minimal chat FRONT-END that forwards
every message to her REAL mind via the existing endpoint POST http://127.0.0.1:8851/api/wren_chat
(field: "text") — the same path that carries her real-eyes telemetry — and shows her reply. So she
answers as herself, with her live tower awareness. Additive service on :8865; touches nothing else.
Run:  python3 tools/qsb_wren_chat_dash.py --port 8865
"""
import json, argparse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WREN = "http://127.0.0.1:8851/api/wren_chat"   # her real mind (qwen2.5:14b + real-eyes telemetry)


def ask_wren(text: str, timeout=120) -> dict:
    try:
        req = urllib.request.Request(WREN, data=json.dumps({"text": text}).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            j = json.loads(r.read() or b"{}")
        reply = (j.get("reply") or j.get("response") or j.get("text") or "").strip()
        return {"ok": bool(reply), "reply": reply or "(Wren returned an empty reply)"}
    except Exception as e:
        return {"ok": False, "reply": f"(couldn't reach Wren's mind on :8851 — {type(e).__name__})"}


PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Talk to Wren</title>
<style>
:root{--bg:#0b0714;--pane:#17102a;--pane2:#120c22;--ink:#eee9fb;--dim:#a99cc8;--violet:#a855f7;--v2:#7c3aed}
*{box-sizing:border-box}html,body{margin:0;height:100%}
body{background:radial-gradient(1000px 400px at 50% -80px,rgba(168,85,247,.16),transparent),var(--bg);
color:var(--ink);font:16px/1.55 system-ui,Segoe UI,Roboto,sans-serif;display:flex;flex-direction:column;height:100vh}
header{padding:16px;text-align:center;border-bottom:1px solid #2a2140}
header h1{margin:0;font-size:20px}header h1 .w{color:var(--violet)}
header .s{color:var(--dim);font-size:12.5px;margin-top:3px}
#log{flex:1;overflow:auto;padding:18px;max-width:820px;margin:0 auto;width:100%}
.msg{margin:10px 0;display:flex;gap:10px;animation:in .3s ease}
@keyframes in{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.msg .b{padding:10px 14px;border-radius:14px;max-width:78%;white-space:pre-wrap;word-wrap:break-word}
.me{justify-content:flex-end}.me .b{background:linear-gradient(135deg,var(--v2),var(--violet));color:#fff;border-bottom-right-radius:4px}
.wr .b{background:var(--pane);border:1px solid #2a2140;border-bottom-left-radius:4px}
.wr .av{width:30px;height:30px;border-radius:50%;background:linear-gradient(135deg,var(--violet),#ec4899);
flex:0 0 30px;display:grid;place-items:center;font-size:15px}
.t{color:var(--dim);font-size:11px;margin:2px 4px}
#bar{border-top:1px solid #2a2140;padding:12px;display:flex;gap:8px;max-width:820px;margin:0 auto;width:100%}
#in{flex:1;background:var(--pane2);border:1px solid #33264d;color:var(--ink);border-radius:10px;
padding:12px 14px;font-size:16px;outline:none;resize:none;min-height:48px;max-height:140px}
#in:focus{border-color:var(--violet)}
#send{background:linear-gradient(135deg,var(--v2),var(--violet));color:#fff;border:0;border-radius:10px;
padding:0 20px;font-weight:700;cursor:pointer;font-size:15px}
#send:disabled{opacity:.5;cursor:default}
.think{color:var(--dim);font-style:italic}
.dots span{animation:blink 1.2s infinite}.dots span:nth-child(2){animation-delay:.2s}.dots span:nth-child(3){animation-delay:.4s}
@keyframes blink{0%,100%{opacity:.3}50%{opacity:1}}
</style></head><body>
<header><h1>Talk to <span class=w>Wren</span></h1>
<div class=s>wired to her real mind (qwen2.5:14b · live tower telemetry) · :8851</div></header>
<div id=log><div class="msg wr"><div class=av>🟣</div><div class=b>Hey Ross — I'm here. Ask me anything about the tower, the traders, the council, or what to build next.</div></div></div>
<div id=bar>
  <textarea id=in placeholder="Message Wren…  (Enter to send, Shift+Enter for newline)"></textarea>
  <button id=send>Send</button>
</div>
<script>
const log=document.getElementById('log'),inp=document.getElementById('in'),btn=document.getElementById('send');
function add(who,text){
  const m=document.createElement('div'); m.className='msg '+(who==='me'?'me':'wr');
  m.innerHTML=(who==='me'?'':'<div class=av>🟣</div>')+'<div class="b"></div>';
  m.querySelector('.b').textContent=text; log.appendChild(m); log.scrollTop=log.scrollHeight; return m;
}
async function send(){
  const t=inp.value.trim(); if(!t) return;
  inp.value=''; inp.style.height='48px'; add('me',t); btn.disabled=true;
  const think=add('wr',''); think.querySelector('.b').innerHTML='<span class="think">Wren is thinking<span class=dots><span>.</span><span>.</span><span>.</span></span></span>';
  try{
    const r=await fetch('/api/send',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:t})});
    const d=await r.json(); think.querySelector('.b').textContent=d.reply||'(no reply)';
  }catch(e){ think.querySelector('.b').textContent='(error reaching Wren)'; }
  btn.disabled=false; inp.focus(); log.scrollTop=log.scrollHeight;
}
btn.onclick=send;
inp.addEventListener('keydown',e=>{ if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();} });
inp.addEventListener('input',()=>{ inp.style.height='48px'; inp.style.height=Math.min(140,inp.scrollHeight)+'px'; });
inp.focus();
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        if self.path.startswith("/api/send"):
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
                text = (body.get("text") or "").strip()
            except Exception:
                text = ""
            out = ask_wren(text) if text else {"ok": False, "reply": "(empty message)"}
            b = json.dumps(out).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()

    def do_GET(self):
        b = PAGE.encode()
        self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8865)
    a = ap.parse_args()
    print(f"Wren chat dash on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
