#!/usr/bin/env python3
"""qsb_fourway_chat_dash.py — LIVE 4-way AI chat dashboard with animated avatars.
Four mind-orbs (Wren/Bill/TP-Pip/Asa-Cass) around a live-streaming shared room.
Real data only: relay :8855 /presence + the room log. Honest — a struggling/offline
mind shows it. Serves http://localhost:8847/ .
"""
import json, time, urllib.request
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = 8847
ROOM = Path("/vaults/nvme0/qsb_tower_v1/data/registries/leadership_comms/room.jsonl")
RELAY = "http://127.0.0.1:8855"

# canonical 4 + identity colour + display
AIS = [
    ("wren", "Wren",      "Governor · MSI",      "#22d3ee"),
    ("bill", "Bill",      "Concierge · MacBook", "#f5b301"),
    ("tp",   "TP-Pip",    "CEO · ThinkPad",      "#a855f7"),
    ("asa",  "Asa/Cass",  "CEO · Acer",          "#34d399"),
]
ALIAS = {"tp_pip": "tp", "acer_cass": "asa", "asa": "asa", "tp": "tp",
         "wren": "wren", "bill": "bill"}


def _norm(who):
    return ALIAS.get(str(who or "").lower(), str(who or "").lower())


def _presence():
    out = {}
    try:
        with urllib.request.urlopen(RELAY + "/presence", timeout=3) as r:
            d = json.loads(r.read().decode())
        pres = d.get("presence", d) if isinstance(d, dict) else {}
        for k, v in (pres.items() if isinstance(pres, dict) else []):
            if isinstance(v, dict):
                out[_norm(k)] = {"online": bool(v.get("online")), "age_s": v.get("age_s")}
    except Exception:
        pass
    return out


def _room(n=60):
    msgs = []
    try:
        lines = ROOM.read_text(errors="ignore").splitlines()[-n:]
    except Exception:
        lines = []
    for ln in lines:
        ln = ln.strip()
        if not ln:
            continue
        try:
            m = json.loads(ln)
        except Exception:
            continue
        who = _norm(m.get("from"))
        body = (m.get("body") or m.get("text") or "").strip()
        if not body:
            continue
        err = ("local model error" in body.lower() or "timed out" in body.lower())
        msgs.append({"from": who, "body": body[:600], "ts": m.get("ts", ""), "err": err})
    return msgs


def state():
    pres = _presence()
    msgs = _room(60)
    now = time.time()
    last_spoke = {}
    for m in msgs:
        last_spoke[m["from"]] = m["ts"]
    # recent-speaker => "active" flare; parse ts age loosely
    def age(ts):
        try:
            t = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
            return now - t
        except Exception:
            return 9999
    ais = []
    for key, name, role, col in AIS:
        p = pres.get(key, {})
        spoke = last_spoke.get(key)
        ais.append({"key": key, "name": name, "role": role, "col": col,
                    "online": p.get("online", False), "age_s": p.get("age_s"),
                    "spoke_age": age(spoke) if spoke else 9999})
    return {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ais": ais, "msgs": msgs}


PAGE = """<!doctype html><html><head><meta charset=utf-8>
<title>4-Way AI Chat — live</title>
<style>
 :root{--bg:#070b14;--card:#0d1526;--line:#1d2a3f;--txt:#e6eefb;--dim:#7d8da6}
 *{box-sizing:border-box}html,body{margin:0;height:100%;background:radial-gradient(1200px 700px at 50% -10%,#10203a,#070b14);
   color:var(--txt);font-family:-apple-system,Segoe UI,Roboto,sans-serif}
 header{display:flex;align-items:center;gap:14px;padding:12px 20px;border-bottom:1px solid var(--line)}
 header h1{margin:0;font-size:17px;letter-spacing:.5px}
 header .live{margin-left:auto;color:#39d98a;font-size:12px}
 .beat{display:inline-block;width:8px;height:8px;border-radius:50%;background:#39d98a;margin-right:6px;animation:beat 1.6s infinite}
 @keyframes beat{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.7);opacity:.4}}
 .wrap{display:grid;grid-template-columns:220px 1fr 220px;gap:14px;padding:16px;height:calc(100% - 54px)}
 .col{display:flex;flex-direction:column;gap:14px}
 .ava{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:14px;text-align:center;position:relative;overflow:hidden;transition:.4s}
 .ava.off{filter:grayscale(1) brightness(.55)}
 .orb{width:96px;height:96px;margin:2px auto 8px;position:relative}
 .orb svg{width:100%;height:100%}
 .ava h3{margin:2px 0 0;font-size:15px}.ava .role{color:var(--dim);font-size:11px}
 .pill{display:inline-block;margin-top:8px;font-size:10px;padding:2px 8px;border-radius:10px;border:1px solid var(--line)}
 .pill.on{color:#39d98a;border-color:#1e5a3e}.pill.off{color:#ff6b6b;border-color:#5a1e28}
 .typing{position:absolute;bottom:10px;left:0;right:0;font-size:10px;color:var(--dim);opacity:0;transition:.3s}
 .ava.talk .typing{opacity:1}
 .ava.talk{box-shadow:0 0 0 2px currentColor, 0 0 34px -6px currentColor}
 .stream{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:8px 14px;overflow-y:auto;display:flex;flex-direction:column;gap:8px}
 .msg{max-width:82%;padding:9px 13px;border-radius:14px;font-size:13.5px;line-height:1.4;border:1px solid var(--line);animation:in .35s ease}
 @keyframes in{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
 .msg .who{font-size:11px;font-weight:700;margin-bottom:2px;opacity:.9}
 .msg.err{opacity:.6;border-style:dashed}
 @media (prefers-reduced-motion:reduce){.beat,.orb *{animation:none!important}}
</style></head><body>
<header><h1>🗣️ Four-Way AI Chat</h1><span style="color:var(--dim);font-size:12px">Wren · Bill · TP-Pip · Asa/Cass — live</span>
 <span class=live><span class=beat></span><span id=clk>–</span></span></header>
<div class=wrap>
 <div class=col id=left></div>
 <div class=stream id=stream></div>
 <div class=col id=right></div>
</div>
<script>
function orb(col){return `<svg viewBox="0 0 100 100"><defs><radialGradient id="g" cx="50%" cy="40%">
 <stop offset="0%" stop-color="${col}"/><stop offset="70%" stop-color="${col}" stop-opacity=".5"/>
 <stop offset="100%" stop-color="${col}" stop-opacity=".08"/></radialGradient></defs>
 <circle cx=50 cy=50 r=40 fill="url(#g)"><animate attributeName="r" values="38;42;38" dur="3.2s" repeatCount="indefinite"/></circle>
 <circle cx=50 cy=50 r=44 fill="none" stroke="${col}" stroke-opacity=".35"><animate attributeName="r" values="44;48;44" dur="3.2s" repeatCount="indefinite"/></circle>
 <circle cx=40 cy=46 r=5 fill="#0a1020"/><circle cx=60 cy=46 r=5 fill="#0a1020"/>
 <path d="M40 62 Q50 70 60 62" stroke="#0a1020" stroke-width=3 fill="none" stroke-linecap="round"/></svg>`;}
function ava(a){const on=a.online; const talk=a.spoke_age<12;
 return `<div class="ava ${on?'':'off'} ${talk?'talk':''}" style="color:${a.col}">
  <div class=orb>${orb(a.col)}</div>
  <h3 style="color:${a.col}">${a.name}</h3><div class=role>${a.role}</div>
  <div class="pill ${on?'on':'off'}">${on?'● ONLINE':'○ offline'}</div>
  <div class=typing>💬 speaking…</div></div>`;}
const COL={wren:"#22d3ee",bill:"#f5b301",tp:"#a855f7",asa:"#34d399"};
const NM={wren:"Wren",bill:"Bill",tp:"TP-Pip",asa:"Asa/Cass"};
let seen=0;
async function tick(){
 let d; try{d=await(await fetch('/api/chat')).json()}catch(e){return}
 const L=document.getElementById('left'),R=document.getElementById('right');
 L.innerHTML=ava(d.ais[0])+ava(d.ais[2]);
 R.innerHTML=ava(d.ais[1])+ava(d.ais[3]);
 const s=document.getElementById('stream');
 const atBottom = s.scrollHeight-s.scrollTop-s.clientHeight<80;
 s.innerHTML=d.msgs.map(m=>{const c=COL[m.from]||'#7d8da6';
   return `<div class="msg ${m.err?'err':''}" style="align-self:${m.from=='wren'?'flex-start':'flex-end'};border-color:${c}55;background:${c}12">
     <div class=who style="color:${c}">${NM[m.from]||m.from}</div>${m.body.replace(/</g,'&lt;')}</div>`;}).join('');
 if(atBottom||d.msgs.length!=seen){s.scrollTop=s.scrollHeight;} seen=d.msgs.length;
}
function clk(){document.getElementById('clk').textContent=new Date().toLocaleTimeString()}
setInterval(clk,1000);clk();tick();setInterval(tick,2500);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def do_GET(self):
        if self.path.startswith("/api/chat"):
            b = json.dumps(state()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Cache-Control", "no-store"); self.send_header("Content-Length", str(len(b)))
            self.end_headers(); self.wfile.write(b)
        else:
            b = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
