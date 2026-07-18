#!/usr/bin/env python3
"""
PHYSICAL CEO COCKPIT V2 — ONE shared codebase, per-machine config profile.
Runs ON the physical laptop (TP-Pip / Acer-Cass). Truth-first: a configured model
label is NOT a live model; HTTP 200 is NOT brain-alive; an offline template is
always labelled; no HQ surrogate is presented as the physical CEO.

Deploy (per machine):
  TP  : python physical_ceo_cockpit_v2.py --worker-id tp_pip   --name "TP-Pip" \
        --title "ThinkPad Command Cathedral CEO" --host DESKTOP-9RBVKSM \
        --runtime-port 8871 --legacy-port 9110 --model llama3.2 --port 9120
  Acer: python physical_ceo_cockpit_v2.py --worker-id acer_cass --name "Asa / Acer-Cass" \
        --title "Acer Data Foundry CEO" --host DESKTOP-1E2FB5N \
        --runtime-port 8872 --legacy-port 9000 --model llama3.2 --port 9120

No shell endpoint. No secrets. No self-close. Task Council actions post as the
physical CEO from THIS machine only.
"""
import argparse, json, socket, urllib.request, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

CFG = {}
OLLAMA = "http://127.0.0.1:11434"
HQ_CANDIDATES = ["http://192.168.1.92:8852", "http://192.168.1.72:8852", "http://192.168.1.84:8852"]


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url, t=4):
    with urllib.request.urlopen(url, timeout=t) as r:
        return r.status, r.read(8192).decode("utf-8", "replace")


def _up(url, t=3):
    try:
        s, _ = _get(url, t); return 200 <= s < 400
    except Exception:
        return False


def discover_hq():
    for b in HQ_CANDIDATES:
        try:
            if json.loads(_get(b + "/api/hq_identity")[1]).get("service") == "qsb_boardroom":
                return b
        except Exception:
            continue
    return None


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("192.168.1.1", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "unknown"


def brain_truth():
    """Separate CONFIGURED model from LIVE brain. Never conflate."""
    out = {"configured_model": CFG["model"], "local_ollama": "UNREACHABLE",
           "model_installed": False, "models": [], "ollama_version": None,
           "current_response_path": "NONE", "brain_state": "UNAVAILABLE", "ts": utc()}
    try:
        out["ollama_version"] = json.loads(_get(OLLAMA + "/api/version", 4)[1]).get("version")
        out["local_ollama"] = "LIVE"
    except Exception as e:
        out["local_ollama"] = "UNREACHABLE"; out["detail"] = type(e).__name__
        return out
    try:
        models = [m.get("name", "") for m in json.loads(_get(OLLAMA + "/api/tags", 6)[1]).get("models", [])]
        out["models"] = models
        out["model_installed"] = any(CFG["model"] in m for m in models)
    except Exception:
        pass
    if out["local_ollama"] == "LIVE" and out["model_installed"]:
        out["brain_state"] = "READY_LOCAL"; out["current_response_path"] = "LOCAL OLLAMA %s / %s" % (OLLAMA, CFG["model"])
    elif out["local_ollama"] == "LIVE":
        out["brain_state"] = "DEGRADED"; out["current_response_path"] = "LOCAL OLLAMA up, model %s MISSING" % CFG["model"]
    return out


def full_state():
    hq = discover_hq()
    b = brain_truth()
    return {"ts": utc(), "worker_id": CFG["worker_id"], "name": CFG["name"], "title": CFG["title"],
            "components": {
                "machine":   {"state": "ON", "host": CFG["host"], "source": "config (Ross-confirmed physical)"},
                "runtime":   {"state": "LIVE" if _up("http://127.0.0.1:%d/health" % CFG["runtime_port"]) or _up("http://127.0.0.1:%d/" % CFG["runtime_port"]) else "UNREACHABLE",
                              "endpoint": "127.0.0.1:%d" % CFG["runtime_port"], "source": "DIRECT PROBE"},
                "dashboard_v2": {"state": "LIVE", "endpoint": "%s:%d" % (local_ip(), CFG["port"]), "source": "SELF"},
                "legacy_dashboard": {"state": "LIVE" if _up("http://127.0.0.1:%d/" % CFG["legacy_port"]) else "UNREACHABLE",
                              "endpoint": "127.0.0.1:%d" % CFG["legacy_port"], "source": "DIRECT PROBE",
                              "label": "LEGACY DASHBOARD — HISTORICAL/DIAGNOSTIC VIEW"},
                "local_brain": {"state": b["brain_state"], "path": b["current_response_path"], "source": "DIRECT OLLAMA PROBE"},
                "hq_surrogate": {"state": "SEPARATE — HQ-hosted, NOT this physical CEO",
                              "endpoint": "HQ 127.0.0.1:%s" % ("8861" if CFG["worker_id"] == "tp_pip" else "8862")},
                "boardroom": {"state": "LIVE" if hq else "UNRESOLVED", "endpoint": hq or "unresolved", "source": "hq_identity discovery"},
                "network":   {"active_ip": local_ip(), "source": "route toward HQ"},
            },
            "brain": b, "no_surrogate_here": True}


def do_chat(prompt):
    """LOCAL model only. Truthful metadata. If unavailable -> honest offline notice (labelled)."""
    b = brain_truth()
    started = utc()
    if b["brain_state"] != "READY_LOCAL":
        return {"reply": "LOCAL BRAIN UNAVAILABLE — I will not fabricate a reasoning reply. Brain state: %s." % b["brain_state"],
                "offline_template": True, "model": None, "provider": "none", "local": True,
                "brain_state": b["brain_state"], "response_path": b["current_response_path"], "started": started, "ts": utc()}
    try:
        body = json.dumps({"model": CFG["model"], "prompt": prompt[:2000], "stream": False}).encode()
        req = urllib.request.Request(OLLAMA + "/api/generate", data=body, method="POST",
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=120) as r:
            d = json.loads(r.read().decode())
        return {"reply": d.get("response", "").strip(), "offline_template": False,
                "model": d.get("model"), "provider": "local_ollama", "local": True, "external": False,
                "endpoint": OLLAMA, "fallback_used": False, "brain_state": "READY_LOCAL",
                "response_path": "LOCAL OLLAMA / " + CFG["model"], "duration_ms": round((d.get("total_duration") or 0)/1e6),
                "started": started, "ts": utc(), "evidence": "direct local /api/generate on this physical machine"}
    except Exception as e:
        return {"reply": "LOCAL GENERATION FAILED: %s (not fabricating a reply)" % (type(e).__name__),
                "offline_template": True, "model": CFG["model"], "provider": "local_ollama", "local": True,
                "brain_state": "DEGRADED", "started": started, "ts": utc()}


def council_ack(task_id, note):
    hq = discover_hq()
    if not hq:
        return {"ok": False, "error": "HQ unresolved"}
    body = json.dumps({"id": task_id, "actor": CFG["worker_id"], "text": (note or "")[:400]}).encode()
    req = urllib.request.Request(hq + "/tasks/ack", data=body, method="POST", headers={"Content-Type": "application/json"})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=6).read().decode())
    except Exception as e:
        return {"ok": False, "error": str(e)[:80]}


PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>__NAME__ · Physical CEO Cockpit V2</title>
<style>
*{box-sizing:border-box}body{margin:0;font:15px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:#0b0f16;color:#e8eef6}
header{background:#0f1826;border-bottom:2px solid #1c2c44;padding:12px 16px;display:flex;align-items:center;gap:14px;flex-wrap:wrap}
.av{width:52px;height:52px;border-radius:12px;background:linear-gradient(135deg,#1e3a5f,#2a6cb0);display:flex;align-items:center;justify-content:center;font-size:24px;font-weight:800}
h1{font-size:19px;margin:0}.sub{color:#8aa0bd;font-size:12px}
nav{display:flex;gap:6px;flex-wrap:wrap;padding:8px 12px;background:#0d1420;border-bottom:1px solid #1c2c44}
nav button{background:#16233a;color:#cfe0f5;border:1px solid #24405f;border-radius:8px;padding:9px 13px;font-weight:700;cursor:pointer;min-height:42px}
nav button.on{background:#2a6cb0;color:#fff}
main{padding:14px;max-width:1100px;margin:auto}.panel{display:none}.panel.on{display:block}
.card{background:#101a2b;border:1px solid #1e3350;border-radius:10px;padding:12px 14px;margin-bottom:10px}
.row{display:flex;justify-content:space-between;gap:10px;padding:4px 0;border-bottom:1px solid #16263e;font-size:13px}
.k{color:#8aa0bd}.v{font-weight:700}
.green{color:#3ddc84}.amber{color:#ffca4a}.red{color:#ff6b6b}.grey{color:#8aa0bd}
textarea{width:100%;background:#0b1420;color:#e8eef6;border:1px solid #24405f;border-radius:8px;padding:10px;font:14px system-ui}
button.act{background:#2a6cb0;color:#fff;border:none;border-radius:8px;padding:11px 16px;font-weight:800;cursor:pointer;min-height:46px}
button.warn{background:#7a3030}
#chatlog{max-height:44vh;overflow:auto}.msg{margin:8px 0;padding:8px 10px;border-radius:8px;background:#0d1727}
.msg .meta{color:#7d94b3;font-size:11px;margin-top:4px}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:800}
</style></head><body>
<header>
  <div class=av id=avatar>__EMOJI__</div>
  <div><h1>__NAME__ <span id=avstate class=badge style="background:#16233a">…</span></h1>
    <div class=sub>__TITLE__ · __HOST__ · <span id=hdrbrain>brain: …</span> · <span id=hdrnet>…</span></div></div>
  <div style="margin-left:auto" class=sub id=clock></div>
</header>
<nav id=nav></nav>
<main>
  <div id=home class="panel on">
    <div class=card><b>Truthful component state</b><div id=state>loading…</div></div>
  </div>
  <div id=brain class=panel>
    <div class=card><b>Brain (configured model is NOT live proof)</b><div id=brainp>loading…</div>
      <button class=act onclick="testBrain()">Test local brain</button></div>
  </div>
  <div id=chat class=panel>
    <div class=card><div id=chatlog></div>
      <textarea id=ci rows=2 placeholder="Message __NAME__ (local model only)…"></textarea>
      <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
        <button class=act onclick="send()">Send</button>
        <button class=warn onclick="stopSpeak()">Stop speech</button>
        <label class=sub><input type=checkbox id=autospeak> auto-speak (off by default)</label>
      </div></div>
  </div>
  <div id=history class=panel><div class=card><b>History</b> <span class=sub>(dated; not mixed into current status)</span><div id=hist>loading…</div></div></div>
</main>
<script>
const NAV=[['home','HOME'],['brain','BRAIN'],['chat','CHAT'],['history','HISTORY']];
let cur='home';
function go(id){cur=id;document.querySelectorAll('.panel').forEach(p=>p.classList.toggle('on',p.id===id));
  document.querySelectorAll('#nav button').forEach(b=>b.classList.toggle('on',b.dataset.id===id));if(id==='brain')loadBrain();if(id==='history')loadHist();}
const nav=document.getElementById('nav');NAV.forEach(([id,l])=>{const b=document.createElement('button');b.textContent=l;b.dataset.id=id;b.onclick=()=>go(id);nav.appendChild(b);});go('home');
async function j(u,o){const r=await fetch(u,o);return r.json();}
function col(s){s=(s||'').toUpperCase();if(s.includes('LIVE')||s.includes('READY')||s==='ON'||s.includes('RUNNING'))return 'green';if(s.includes('DEGRAD')||s.includes('SEPARATE')||s.includes('UNRESOLVED'))return 'amber';if(s.includes('UNREACH')||s.includes('UNAVAIL')||s.includes('OFFLINE'))return 'red';return 'grey';}
async function loadState(){try{const d=await j('/api/state');const c=d.components;let h='';
  for(const[k,v]of Object.entries(c)){const st=v.state||v.active_ip||'';h+=`<div class=row><span class=k>${k}</span><span class="v ${col(st)}">${st}${v.endpoint?(' · '+v.endpoint):''}</span></div>`;}
  document.getElementById('state').innerHTML=h;
  const bs=d.brain.brain_state;document.getElementById('hdrbrain').textContent='brain: '+bs;document.getElementById('hdrbrain').className=col(bs);
  document.getElementById('hdrnet').textContent=c.network.active_ip;
  const av=document.getElementById('avstate');av.textContent=(bs==='READY_LOCAL')?'AT DESK':(bs==='DEGRADED'?'BRAIN DEGRADED':'NEEDS ATTENTION');
}catch(e){}}
async function loadBrain(){const b=await j('/api/brain');let h='';
  const fields=[['CONFIGURED MODEL',b.configured_model],['LOCAL OLLAMA',b.local_ollama],['MODEL INSTALLED',b.model_installed],['OLLAMA VERSION',b.ollama_version],['CURRENT RESPONSE PATH',b.current_response_path],['BRAIN STATE',b.brain_state]];
  fields.forEach(([k,v])=>{h+=`<div class=row><span class=k>${k}</span><span class="v ${col(''+v)}">${v}</span></div>`;});
  document.getElementById('brainp').innerHTML=h;}
async function testBrain(){document.getElementById('brainp').innerHTML='testing…';const d=await j('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:'Reply with exactly: BRAIN_OK'})});alert('Reply: '+d.reply+'\\nmodel='+d.model+' path='+d.response_path+' offline_template='+d.offline_template);loadBrain();}
let speaking=false;
function stopSpeak(){try{speechSynthesis.cancel()}catch(e){}speaking=false;}
function speak(t){if(!document.getElementById('autospeak').checked)return;if(document.hidden)return;stopSpeak();try{const u=new SpeechSynthesisUtterance(t);speechSynthesis.speak(u);}catch(e){}}
async function send(){const t=document.getElementById('ci').value.trim();if(!t)return;document.getElementById('ci').value='';
  const log=document.getElementById('chatlog');log.innerHTML+=`<div class=msg><b>Ross:</b> ${t}</div>`;
  const d=await j('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:t})});
  const tag=d.offline_template?'<span class="badge red">OFFLINE TEMPLATE</span>':'<span class="badge green">LOCAL '+(d.model||'')+'</span>';
  log.innerHTML+=`<div class=msg><b>__NAME__:</b> ${d.reply} <div class=meta>${tag} · path=${d.response_path||''} · ${d.duration_ms||'?'}ms · ${d.ts}</div></div>`;
  log.scrollTop=log.scrollHeight;speak(d.reply);}
async function loadHist(){try{const d=await j('/api/history');document.getElementById('hist').innerHTML=(d.rows||[]).map(r=>`<div class=row><span class=k>${r.ts||''}</span><span class=v>${(r.kind||'')+': '+(r.text||'').slice(0,80)}</span></div>`).join('')||'<span class=sub>no history yet</span>';}catch(e){}}
loadState();setInterval(loadState,7000);setInterval(()=>document.getElementById('clock').textContent=new Date().toLocaleTimeString(),1000);
</script></body></html>"""


HIST = []


def log_hist(kind, text):
    HIST.append({"ts": utc(), "kind": kind, "text": text[:200]})
    if len(HIST) > 500:
        del HIST[:250]


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _j(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Content-Length", str(len(b)))
        self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/cockpit"):
            html = PAGE.replace("__NAME__", CFG["name"]).replace("__TITLE__", CFG["title"]).replace("__HOST__", CFG["host"]).replace("__EMOJI__", CFG["emoji"])
            b = html.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if p == "/health":
            return self._j(200, {"ok": True, "service": "physical_ceo_cockpit_v2", "worker_id": CFG["worker_id"], "host": CFG["host"], "port": CFG["port"], "ts": utc()})
        if p == "/api/identity":
            return self._j(200, {"id": CFG["worker_id"], "name": CFG["name"], "title": CFG["title"], "host": CFG["host"],
                                 "hq_hosted": False, "physical_independent": True, "cockpit": "v2", "ts": utc()})
        if p == "/api/state":
            return self._j(200, full_state())
        if p == "/api/brain":
            return self._j(200, brain_truth())
        if p == "/api/history":
            return self._j(200, {"ts": utc(), "rows": list(reversed(HIST[-80:]))})
        return self._j(404, {"error": "not_found"})

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n).decode()) if n else {}
        except Exception:
            body = {}
        if p == "/api/chat":
            log_hist("ross_msg", body.get("prompt", ""))
            r = do_chat(body.get("prompt", ""))
            log_hist("reply(" + str(r.get("response_path", "")) + ")", r.get("reply", ""))
            return self._j(200, r)
        if p == "/api/council_ack":
            r = council_ack(body.get("id", ""), body.get("note", ""))
            log_hist("council_ack", str(r))
            return self._j(200, r)
        return self._j(404, {"error": "not_found"})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--worker-id", required=True); ap.add_argument("--name", required=True)
    ap.add_argument("--title", default=""); ap.add_argument("--host", required=True)
    ap.add_argument("--runtime-port", type=int, required=True); ap.add_argument("--legacy-port", type=int, required=True)
    ap.add_argument("--model", default="llama3.2"); ap.add_argument("--port", type=int, default=9120)
    a = ap.parse_args()
    CFG.update({"worker_id": a.worker_id, "name": a.name, "title": a.title, "host": a.host,
                "runtime_port": a.runtime_port, "legacy_port": a.legacy_port, "model": a.model, "port": a.port,
                "emoji": "🏛️" if a.worker_id == "tp_pip" else "🔬"})
    log_hist("cockpit_start", "%s cockpit v2 on %s:%d" % (a.worker_id, a.host, a.port))
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
