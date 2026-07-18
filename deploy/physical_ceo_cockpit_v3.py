#!/usr/bin/env python3
"""
PHYSICAL CEO COCKPIT V3 — one shared codebase, per-machine profile.
Single-screen professional command centre. Backend truth layer preserved from V2:
configured model != live brain, HTTP 200 != mind alive, no HQ surrogate as physical,
offline template always labelled, no shell endpoint, no secrets, no self-close.

Deploy (per machine):
  TP  : --worker-id tp_pip   --name "TP-Pip"        --title "ThinkPad Command Cathedral CEO" \
        --host DESKTOP-9RBVKSM --runtime-port 8871 --legacy-port 9110 --accent gold  --port 9120
  Acer: --worker-id acer_cass --name "Asa / Acer-Cass" --title "Acer Data Foundry CEO" \
        --host DESKTOP-1E2FB5N --runtime-port 8872 --legacy-port 9000 --accent purple --port 9120
"""
import argparse, json, socket, os, urllib.request, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

CFG = {}
OLLAMA = "http://127.0.0.1:11434"
HQ_CANDIDATES = ["http://192.168.1.92:8852", "http://192.168.1.72:8852", "http://192.168.1.84:8852"]
HIST = []
_HQ_CACHE = {"url": None, "ts": 0}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")


def _get(url, t=4):
    with urllib.request.urlopen(url, timeout=t) as r:
        return r.status, r.read(16384).decode("utf-8", "replace")


def _up(url, t=3):
    try:
        s, _ = _get(url, t); return 200 <= s < 400
    except Exception:
        return False


def _getj(url, t=4):
    try:
        return json.loads(_get(url, t)[1])
    except Exception:
        return None


def _post(url, payload, t=6):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=t) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": type(e).__name__ + ":" + str(e)[:80]}


def discover_hq():
    import time
    if _HQ_CACHE["url"] and time.time() - _HQ_CACHE["ts"] < 30:
        return _HQ_CACHE["url"]
    for b in HQ_CANDIDATES:
        d = _getj(b + "/api/hq_identity", 3)
        if d and d.get("service") == "qsb_boardroom":
            _HQ_CACHE.update({"url": b, "ts": time.time()}); return b
    return _HQ_CACHE["url"]


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("192.168.1.1", 80))
        ip = s.getsockname()[0]; s.close(); return ip
    except Exception:
        return "unknown"


def brain_truth():
    out = {"configured_model": CFG["model"], "local_ollama": "UNREACHABLE", "model_installed": False,
           "ollama_version": None, "current_response_path": "NONE", "brain_state": "UNAVAILABLE",
           "last_local_inference": CFG.get("last_infer"), "provider": "none", "latency_ms": None, "ts": utc()}
    v = _getj(OLLAMA + "/api/version", 4)
    if not v:
        return out
    out["local_ollama"] = "LIVE"; out["ollama_version"] = v.get("version")
    tags = _getj(OLLAMA + "/api/tags", 6) or {}
    out["model_installed"] = any(CFG["model"] in m.get("name", "") for m in tags.get("models", []))
    if out["model_installed"]:
        out["brain_state"] = "READY_LOCAL"; out["provider"] = "local_ollama"
        out["current_response_path"] = "LOCAL OLLAMA %s / %s" % (OLLAMA, CFG["model"])
    else:
        out["brain_state"] = "DEGRADED"; out["current_response_path"] = "LOCAL OLLAMA up, model MISSING"
    return out


def full_state():
    hq = discover_hq(); b = brain_truth(); ip = local_ip()
    rt = "LIVE" if (_up("http://127.0.0.1:%d/health" % CFG["runtime_port"]) or _up("http://127.0.0.1:%d/" % CFG["runtime_port"])) else "UNREACHABLE"
    lg = "LIVE" if _up("http://127.0.0.1:%d/" % CFG["legacy_port"]) else "UNREACHABLE"
    wren = "LIVE" if (hq and _up(hq.replace("8852", "8851") + "/status", 3)) else "UNKNOWN"
    return {"ts": utc(), "worker_id": CFG["worker_id"], "name": CFG["name"], "title": CFG["title"], "host": CFG["host"],
            "machine": "ON", "runtime": {"state": rt, "endpoint": "127.0.0.1:%d" % CFG["runtime_port"]},
            "dashboard_v2": {"state": "LIVE", "endpoint": "%s:%d" % (ip, CFG["port"])},
            "legacy_dashboard": {"state": lg, "endpoint": "127.0.0.1:%d" % CFG["legacy_port"], "label": "LEGACY / DIAGNOSTIC"},
            "local_brain": {"state": b["brain_state"], "path": b["current_response_path"], "model": b["configured_model"]},
            "hq_surrogate": {"state": "SEPARATE — HQ-hosted, NOT this physical CEO",
                             "endpoint": "HQ:%s" % ("8861" if CFG["worker_id"] == "tp_pip" else "8862")},
            "boardroom": {"state": "LIVE" if hq else "UNRESOLVED", "endpoint": hq or "unresolved"},
            "wren": {"state": wren, "endpoint": (hq.replace("8852", "8851") if hq else "unknown")},
            "network": {"active_ip": ip, "type": CFG.get("conn", "Wi-Fi")},
            "brain": b}


def council_for_me():
    hq = discover_hq()
    if not hq:
        return {"ts": utc(), "hq": None, "tasks": []}
    snap = _getj(hq + "/tasks/data", 6) or {}
    tasks = snap.get("tasks", []) if isinstance(snap, dict) else []
    mine = []
    for t in tasks:
        blob = (str(t.get("owner")) + " " + str(t.get("acknowledged_by")) + " " + (t.get("title") or "") + " " + (t.get("description") or "")).lower()
        if CFG["worker_id"] in blob or CFG["name"].split()[0].lower() in blob:
            mine.append({"id": t.get("id"), "title": (t.get("title") or "")[:80], "state": t.get("state"),
                         "owner": t.get("owner"), "acknowledged_by": t.get("acknowledged_by")})
    return {"ts": utc(), "hq": hq, "tasks": mine[:12], "total_council": len(tasks)}


def ppf():
    st = full_state(); b = st["brain"]
    past = [h for h in HIST if h.get("kind", "").startswith("reply") or h.get("kind") == "cockpit_start"][-4:]
    return {"ts": utc(),
            "past": [("%s — %s" % (h["ts"][11:19], h["text"][:60])) for h in past] or ["(no prior cockpit events yet)"],
            "present": ["Runtime: " + st["runtime"]["state"], "Local brain: " + b["brain_state"] + " (" + b["current_response_path"] + ")",
                        "Network: " + st["network"]["active_ip"] + " (" + st["network"]["type"] + ")",
                        "Boardroom: " + st["boardroom"]["state"], "Council tasks for me: " + str(len(council_for_me()["tasks"]))],
            "future": ["Next: await Ross / Task Council assignment", "Approvals required: none pending locally",
                       "Risk: brain is CPU-only" if CFG["worker_id"] == "tp_pip" else "Risk: none flagged",
                       "Must not happen without approval: model download, router change, self-close"]}


def do_chat(prompt):
    b = brain_truth(); started = utc()
    if b["brain_state"] != "READY_LOCAL":
        return {"reply": "LOCAL BRAIN UNAVAILABLE (%s) — I will not fabricate reasoning." % b["brain_state"],
                "offline_template": True, "model": None, "provider": "none", "local": True, "confidence": "UNKNOWN",
                "response_path": b["current_response_path"], "ts": utc(), "evidence": "direct ollama probe"}
    d = _post(OLLAMA + "/api/generate", {"model": CFG["model"], "prompt": prompt[:2000], "stream": False}, 120)
    if d.get("ok") is False:
        return {"reply": "LOCAL GENERATION FAILED (%s) — not fabricating." % d.get("error"), "offline_template": True,
                "model": CFG["model"], "provider": "local_ollama", "local": True, "confidence": "UNKNOWN", "ts": utc()}
    CFG["last_infer"] = utc()
    return {"reply": (d.get("response") or "").strip(), "offline_template": False, "model": d.get("model"),
            "provider": "local_ollama", "local": True, "external": False, "endpoint": OLLAMA, "fallback_used": False,
            "response_path": "LOCAL OLLAMA / " + CFG["model"], "duration_ms": round((d.get("total_duration") or 0)/1e6),
            "confidence": "LIKELY", "started": started, "ts": utc(),
            "evidence": "direct local /api/generate on " + CFG["host"]}


def log_hist(kind, text):
    HIST.append({"ts": utc(), "kind": kind, "text": (text or "")[:200]})
    if len(HIST) > 800:
        del HIST[:400]


PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>__NAME__ · CEO Cockpit V3</title>
<style>
:root{--acc:__ACC__;--acc2:__ACC2__;--bg:#080b12;--panel:#0e1420;--pb:#1b2740;--tx:#e9f0fb;--dim:#8ea6c8}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:radial-gradient(1200px 700px at 70% -10%,#12203a,var(--bg));color:var(--tx);font:14px/1.45 "Segoe UI",system-ui,Roboto,sans-serif;overflow:hidden}
.wrap{display:grid;grid-template-rows:auto 1fr auto;height:100vh;gap:8px;padding:8px}
/* command bar */
.cmd{display:flex;align-items:center;gap:14px;background:linear-gradient(90deg,var(--panel),#0b1626);border:1px solid var(--pb);border-radius:14px;padding:10px 16px;box-shadow:0 0 0 1px rgba(255,255,255,.02),0 8px 30px rgba(0,0,0,.4)}
.port{width:60px;height:60px;border-radius:14px;background:radial-gradient(circle at 35% 30%,var(--acc),#0a1220);position:relative;box-shadow:0 0 22px var(--acc);flex:0 0 auto}
.cmd h1{font-size:20px;margin:0;letter-spacing:.3px}.cmd .role{color:var(--dim);font-size:12px}
.chips{display:flex;gap:8px;flex-wrap:wrap;margin-left:6px}
.chip{background:#0b1524;border:1px solid var(--pb);border-radius:20px;padding:3px 11px;font-size:11.5px;white-space:nowrap}
.chip b{color:var(--acc)}
.cbtns{margin-left:auto;display:flex;gap:6px;flex-wrap:wrap}
button{font:inherit;cursor:pointer;border-radius:9px;border:1px solid var(--pb);background:#152238;color:var(--tx);padding:8px 12px;font-weight:700;min-height:40px}
button:hover{border-color:var(--acc)}button.p{background:linear-gradient(120deg,var(--acc),var(--acc2));color:#071018;border:none}
button.w{background:#5a2330;border-color:#7a3040}button.sm{min-height:32px;padding:6px 10px;font-size:12px}
/* main grid */
.grid{display:grid;grid-template-columns:1.05fr 1.1fr 1fr;gap:8px;min-height:0}
.col{display:grid;gap:8px;min-height:0}
.pnl{background:var(--panel);border:1px solid var(--pb);border-radius:14px;padding:10px 12px;min-height:0;display:flex;flex-direction:column;overflow:hidden}
.pnl h3{margin:0 0 6px;font-size:12.5px;letter-spacing:.6px;color:var(--acc);text-transform:uppercase}
.scroll{overflow:auto;min-height:0;flex:1}
/* chat */
#chatlog .m{margin:7px 0;padding:8px 10px;border-radius:10px;background:#0c1626;border:1px solid #14223a}
#chatlog .m.ross{background:#122033;border-color:#1d3352}
#chatlog .who{font-weight:800;color:var(--acc)}#chatlog .meta{color:var(--dim);font-size:10.5px;margin-top:4px}
.badge{display:inline-block;padding:1px 7px;border-radius:9px;font-size:10px;font-weight:800}
.b-green{background:#0d3b26;color:#6ff0b0}.b-amber{background:#3a2f0d;color:#ffd479}.b-red{background:#3b1414;color:#ff9a9a}.b-dim{background:#1a2438;color:#9db3d4}
textarea{width:100%;background:#0a121f;color:var(--tx);border:1px solid var(--pb);border-radius:9px;padding:8px;resize:none;font:inherit}
/* avatar */
.avwrap{align-items:center;justify-content:flex-start;text-align:center}
.avatar{width:180px;height:180px;margin:2px auto 6px;position:relative}
.face{width:100%;height:100%;border-radius:50%;background:radial-gradient(circle at 40% 32%,#1b3355,#0a1424);border:2px solid var(--acc);box-shadow:0 0 34px var(--acc),inset 0 0 26px rgba(0,0,0,.6);position:relative;transition:box-shadow .3s}
.ring{position:absolute;inset:-10px;border-radius:50%;border:1px dashed color-mix(in srgb,var(--acc) 55%,transparent);animation:spin 14s linear infinite;opacity:.5}
.eye{position:absolute;top:64px;width:26px;height:26px;border-radius:50%;background:var(--acc);box-shadow:0 0 14px var(--acc)}
.eye.l{left:48px}.eye.r{right:48px}.mouth{position:absolute;left:50%;transform:translateX(-50%);bottom:44px;width:52px;height:8px;border-radius:6px;background:var(--acc2);transition:height .12s,width .2s}
.avatar.speaking .mouth{animation:talk .28s ease-in-out infinite}
.avatar.thinking .face{box-shadow:0 0 34px var(--acc2),inset 0 0 26px rgba(0,0,0,.6)}
.avatar.thinking .eye{animation:blink 1s infinite}
.avatar.working .ring{animation:spin 3s linear infinite;opacity:.9}
.avatar.warning .face{border-color:#ff6b6b;box-shadow:0 0 34px #ff6b6b}
.avatar.muted{opacity:.55;filter:grayscale(.5)}
@keyframes talk{0%,100%{height:6px;width:34px}50%{height:20px;width:52px}}
@keyframes blink{0%,90%,100%{height:26px}95%{height:4px}}
@keyframes spin{to{transform:rotate(360deg)}}
.state{font-size:22px;font-weight:900;letter-spacing:1px}.doing{color:var(--dim);font-size:12.5px;margin-top:4px;text-align:left;width:100%}
.doing div{padding:2px 0;border-bottom:1px solid #14223a}
/* rows list */
.row{display:flex;justify-content:space-between;gap:8px;padding:3px 0;border-bottom:1px solid #12203a;font-size:12.5px}
.k{color:var(--dim)}.v{font-weight:700;text-align:right}
.bottom{display:grid;grid-template-columns:1fr 1.1fr 1fr;gap:8px;height:190px}
.btnrow{display:flex;gap:6px;flex-wrap:wrap}
small.cos{color:#5b6f8f;font-weight:800;letter-spacing:.5px;align-self:center;margin-right:2px}
</style></head><body>
<div class=wrap>
  <!-- 1. COMMAND BAR -->
  <div class=cmd>
    <div class=port></div>
    <div>
      <h1>__NAME__ <span id=hstate class="badge b-dim">…</span></h1>
      <div class=role>__TITLE__ · __HOST__</div>
    </div>
    <div class=chips id=chips></div>
    <div class=cbtns>
      <button class=sm onclick="speakStatus()">🔊 Speak status</button>
      <button class=sm id=combtn onclick="toggleCommentary()">💬 Commentary: OFF</button>
      <button class=sm onclick="testVoice()">🎤 Test voice</button>
      <button class="sm w" onclick="killAudio()">⛔ Kill sound</button>
      <button class=sm onclick="refresh()">↻ Refresh</button>
      <button class=sm onclick="openExt('/status')">Boardroom</button>
      <button class=sm onclick="openLegacy()">Legacy/Diag</button>
    </div>
  </div>
  <!-- MAIN 3 COLUMNS -->
  <div class=grid>
    <!-- LEFT: conversation -->
    <div class="pnl">
      <h3>Conversation</h3>
      <div class="scroll" id=chatlog></div>
      <div style="margin-top:6px">
        <textarea id=ci rows=2 placeholder="Talk to __NAME__ (local model)…"></textarea>
        <div class="btnrow" style="margin-top:6px">
          <button class="p sm" onclick="send()">Send ▶</button>
          <button class="sm" onclick="askProof()">Ask for proof</button>
          <button class="sm" onclick="speakLast()">Speak reply</button>
          <label class="chip"><input type=checkbox id=autospeak> auto-speak</label>
        </div>
      </div>
    </div>
    <!-- CENTRE: avatar -->
    <div class="pnl avwrap">
      <h3>Live CEO</h3>
      <div class="avatar" id=avatar><div class=ring></div><div class=face><div class="eye l"></div><div class="eye r"></div><div class=mouth></div></div></div>
      <div class=state id=avstate>AT DESK</div>
      <div class=doing id=doing></div>
    </div>
    <!-- RIGHT: jobs + council -->
    <div class="pnl">
      <h3>Active jobs · Task Council</h3>
      <div class="scroll" id=jobs></div>
      <div class="btnrow" style="margin-top:6px">
        <button class="p sm" onclick="councilAction('ack')">Acknowledge</button>
        <button class="sm" onclick="councilAction('note')">Submit progress</button>
        <button class="sm" onclick="councilAction('decline')">Decline (reason)</button>
        <button class="sm" onclick="genReport()">Generate report</button>
      </div>
    </div>
  </div>
  <!-- BOTTOM 3 -->
  <div class=bottom>
    <div class="pnl"><h3>Past · Present · Future</h3><div class="scroll" id=ppf></div>
      <div class=btnrow><button class="sm" onclick="speakPPF()">🔊 Speak</button><button class="sm" onclick="rossNote('ppf')">Add note</button></div></div>
    <div class="pnl"><h3>Decisions · Approvals · Chance/Choice/Change</h3><div class="scroll" style="flex:0 0 auto">
      <div class=btnrow>
        <button class="p sm" onclick="decide('approve')">Approve</button><button class="w sm" onclick="decide('deny')">Deny</button>
        <button class="sm" onclick="decide('accept')">Accept</button><button class="sm" onclick="decide('reject')">Reject</button>
        <button class="sm" onclick="decide('return_for_correction')">Return</button><button class="sm" onclick="decide('request_evidence')">Req evidence</button>
        <button class="sm" onclick="decide('request_smoke')">Req smoke</button><button class="sm" onclick="decide('sign_off')">Sign off</button></div>
      <div class=btnrow style="margin-top:6px"><small class=cos>CHANCE</small>
        <button class="sm" onclick="decide('chance_explore')">Explore</button><button class="sm" onclick="decide('chance_risk')">Risk/Reward</button><button class="sm" onclick="decide('chance_council15')">Council of 15</button></div>
      <div class=btnrow style="margin-top:6px"><small class=cos>CHOICE</small>
        <button class="sm" onclick="decide('choice_a')">Option A</button><button class="sm" onclick="decide('choice_b')">Option B</button><button class="sm" onclick="decide('choice_reco')">Recommended</button><button class="sm" onclick="decide('choice_wait')">Wait</button></div>
      <div class=btnrow style="margin-top:6px"><small class=cos>CHANGE</small>
        <button class="sm" onclick="decide('change_scope')">Scope</button><button class="sm" onclick="decide('change_owner')">Owner</button><button class="sm" onclick="decide('change_verifier')">Verifier</button><button class="sm" onclick="decide('change_repair')">Send back</button></div>
    </div></div>
    <div class="pnl"><h3>History · Evidence · Warnings</h3><div class="scroll" id=hist></div></div>
  </div>
</div>
<script>
const WID="__WID__",NAME="__NAME__";
let COMMENTARY=false, lastReply="", lastState=null;
const chan=('BroadcastChannel' in window)?new BroadcastChannel('cockpit_speak_'+WID):null;
if(chan)chan.onmessage=e=>{if(e.data==='speak')speechSynthesis.cancel();};  // another tab spoke -> we stay quiet
function col(s){s=(''+s).toUpperCase();if(/LIVE|READY|ON|RUNNING|ACKNOWLEDG/.test(s))return 'b-green';if(/DEGRAD|SEPARATE|UNRESOLV|WAIT|UNKNOWN/.test(s))return 'b-amber';if(/UNREACH|UNAVAIL|OFFLINE|FAIL|DOWN/.test(s))return 'b-red';return 'b-dim';}
async function j(u,o){const r=await fetch(u,o);return r.json();}
function av(cls){const a=document.getElementById('avatar');a.className='avatar'+(cls?(' '+cls):'');}
// ---- speech (safe) ----
let speaking=false;
function canSpeak(){return 'speechSynthesis' in window && !document.hidden;}
function killAudio(){try{speechSynthesis.cancel()}catch(e){}speaking=false;av('');}
function speak(t){if(!canSpeak())return;if(chan)chan.postMessage('speak');speechSynthesis.cancel();
  const u=new SpeechSynthesisUtterance(t);u.rate=1;u.onstart=()=>{speaking=true;av('speaking')};u.onend=()=>{speaking=false;av('')};speechSynthesis.speak(u);}
function testVoice(){speak(NAME+" voice online. This line is also shown as text.");}
function speakStatus(){if(!lastState)return;const b=lastState.local_brain;speak(NAME+" at desk. Brain "+b.state+". Runtime "+lastState.runtime.state+". "+ (lastState.council_n||0) +" council tasks.");}
function speakLast(){if(lastReply)speak(lastReply);}
function toggleCommentary(){COMMENTARY=!COMMENTARY;document.getElementById('combtn').textContent='💬 Commentary: '+(COMMENTARY?'ON':'OFF');if(!COMMENTARY)killAudio();}
document.addEventListener('visibilitychange',()=>{if(document.hidden)killAudio();});
// ---- data ----
async function loadState(){try{const d=await j('/api/state');lastState=d;const b=d.brain;
  document.getElementById('chips').innerHTML=[
   ['brain',b.brain_state],['model',b.configured_model],['path',(b.current_response_path||'').slice(0,26)],
   ['runtime',d.runtime.state],['net',d.network.active_ip],['boardroom',d.boardroom.state],['wren',d.wren.state],['surrogate','SEPARATE']
  ].map(([k,v])=>`<span class=chip>${k}: <b>${v}</b></span>`).join('');
  document.getElementById('hstate').textContent=(b.brain_state==='READY_LOCAL')?'AT DESK':(b.brain_state==='DEGRADED'?'BRAIN DEGRADED':'NEEDS ATTENTION');
  document.getElementById('hstate').className='badge '+col(b.brain_state);
  if(!speaking){av(b.brain_state==='READY_LOCAL'?'':(b.brain_state==='UNAVAILABLE'?'warning':''));}
  document.getElementById('avstate').textContent=speaking?'SPEAKING':(b.brain_state==='READY_LOCAL'?'AT DESK':'NEEDS ATTENTION');
  document.getElementById('doing').innerHTML=[
   'Brain path: '+(b.current_response_path||''),'Runtime: '+d.runtime.endpoint+' ('+d.runtime.state+')',
   'Network: '+d.network.active_ip+' · '+d.network.type,'HQ surrogate: '+d.hq_surrogate.state,
   'Legacy: '+d.legacy_dashboard.endpoint,'<small class=cos>idle ring = COSMETIC</small>'
  ].map(x=>'<div>'+x+'</div>').join('');
}catch(e){}}
async function loadJobs(){try{const d=await j('/api/council');lastState&&(lastState.council_n=d.tasks.length);
  document.getElementById('jobs').innerHTML=(d.tasks.length?d.tasks.map(t=>`<div class=row><span class=k>${t.id}</span><span class="v"><span class="badge ${col(t.state)}">${t.state}</span></span></div><div style="font-size:11.5px;color:var(--dim);margin:-2px 0 4px">${t.title} · owner=${t.owner||'—'} ack=${t.acknowledged_by||'—'}</div>`).join(''):'<div class=k>No Task Council tasks reference me yet. (Total on council: '+d.total_council+')</div>')+`<div style="font-size:10.5px;color:var(--dim);margin-top:4px">HQ: ${d.hq||'unresolved'} · actions post as ${WID} from this machine; no auto-complete/self-close.</div>`;
}catch(e){}}
async function loadPPF(){try{const d=await j('/api/ppf');const s=(t,arr)=>`<div style="margin-bottom:4px"><b style="color:var(--acc)">${t}</b>${arr.map(x=>'<div class=row><span class=v style="text-align:left;font-weight:500">'+x+'</span></div>').join('')}</div>`;
  document.getElementById('ppf').innerHTML=s('PAST',d.past)+s('PRESENT',d.present)+s('FUTURE',d.future);window._ppf=d;}catch(e){}}
async function loadHist(){try{const d=await j('/api/history');document.getElementById('hist').innerHTML=(d.rows||[]).map(r=>`<div class=row><span class=k>${(r.ts||'').slice(11,19)}</span><span class=v style="font-weight:500">${(r.kind||'')}: ${(r.text||'').slice(0,54)}</span></div>`).join('')||'<div class=k>no events yet</div>';}catch(e){}}
function refresh(){loadState();loadJobs();loadPPF();loadHist();}
// ---- chat ----
async function send(){const t=document.getElementById('ci').value.trim();if(!t)return;document.getElementById('ci').value='';
  const log=document.getElementById('chatlog');log.innerHTML+=`<div class="m ross"><span class=who>Ross</span>: ${t}</div>`;log.scrollTop=log.scrollHeight;
  av('thinking');document.getElementById('avstate').textContent='THINKING';
  const d=await j('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:t})});
  av('');lastReply=d.reply;
  const bd=d.offline_template?'<span class="badge b-red">OFFLINE TEMPLATE</span>':'<span class="badge b-green">LOCAL '+(d.model||'')+'</span>';
  const conf='<span class="badge '+(d.confidence==='PROVEN'?'b-green':d.confidence==='LIKELY'?'b-amber':'b-dim')+'">'+(d.confidence||'?')+'</span>';
  log.innerHTML+=`<div class=m><span class=who>${NAME}</span>: ${d.reply}<div class=meta>${bd} ${conf} · ${d.provider||''}/${d.model||''} · ${d.local?'local':'external'} · ${d.duration_ms||'?'}ms · path=${d.response_path||''} · ${(d.ts||'').slice(11,19)} · evidence: ${d.evidence||''}</div></div>`;
  log.scrollTop=log.scrollHeight;if(document.getElementById('autospeak').checked)speak(d.reply);loadHist();}
function askProof(){document.getElementById('ci').value='Give me the exact evidence and source for your last answer.';send();}
// ---- actions ----
async function decide(kind){const note=prompt('Optional note for "'+kind+'":')||'';await j('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision:kind,note:note,actor:'ross'})});loadHist();alert('Logged decision: '+kind+' (record only, no execution)');}
async function councilAction(kind){const id=prompt('Task ID for '+kind+':');if(!id)return;const note=(kind==='decline'||kind==='note')?(prompt('Note/reason:')||''):'';const d=await j('/api/council_action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({action:kind,id:id,note:note})});loadJobs();loadHist();alert(JSON.stringify(d));}
async function genReport(){const d=await j('/api/ppf');const r=`${NAME} report ${new Date().toISOString()}\nPAST:\n - ${d.past.join('\n - ')}\nPRESENT:\n - ${d.present.join('\n - ')}\nFUTURE:\n - ${d.future.join('\n - ')}`;const w=window.open('','_blank');w.document.write('<pre>'+r+'</pre>');}
function rossNote(ctx){const t=prompt('Ross note:');if(!t)return;j('/api/decision',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({decision:'ross_note',note:'['+ctx+'] '+t,actor:'ross'})}).then(loadHist);}
function speakPPF(){const d=window._ppf;if(!d)return;speak('Present: '+d.present.join('. ')+'. Next: '+d.future[0]);}
function openExt(path){if(lastState&&lastState.boardroom.endpoint&&lastState.boardroom.endpoint.startsWith('http'))window.open(lastState.boardroom.endpoint.replace('8852','8851'),'_blank');}
function openLegacy(){window.open('http://localhost:__LEGACY__/','_blank');}
document.getElementById('ci').addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
// commentary: describe REAL state changes only
setInterval(()=>{if(!COMMENTARY||!lastState)return;const b=lastState.local_brain.state;if(window._lastBrain&&window._lastBrain!==b){speak(NAME+': brain state changed to '+b);}window._lastBrain=b;},4000);
refresh();setInterval(loadState,6000);setInterval(loadJobs,12000);setInterval(loadPPF,15000);setInterval(loadHist,9000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _j(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code)
        self.send_header("Content-Type", "application/json"); self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/cockpit"):
            html = (PAGE.replace("__NAME__", CFG["name"]).replace("__TITLE__", CFG["title"]).replace("__HOST__", CFG["host"])
                    .replace("__WID__", CFG["worker_id"]).replace("__ACC__", CFG["acc"]).replace("__ACC2__", CFG["acc2"])
                    .replace("__LEGACY__", str(CFG["legacy_port"])))
            b = html.encode(); self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        if p == "/health":
            return self._j(200, {"ok": True, "service": "physical_ceo_cockpit_v3", "worker_id": CFG["worker_id"], "host": CFG["host"], "port": CFG["port"], "ts": utc()})
        if p == "/api/identity":
            return self._j(200, {"id": CFG["worker_id"], "name": CFG["name"], "title": CFG["title"], "host": CFG["host"], "hq_hosted": False, "physical_independent": True, "cockpit": "v3", "ts": utc()})
        if p == "/api/state":
            return self._j(200, full_state())
        if p == "/api/brain":
            return self._j(200, brain_truth())
        if p == "/api/council":
            return self._j(200, council_for_me())
        if p == "/api/ppf":
            return self._j(200, ppf())
        if p == "/api/history":
            return self._j(200, {"ts": utc(), "rows": list(reversed(HIST[-90:]))})
        return self._j(404, {"error": "not_found"})

    def do_POST(self):
        p = urlparse(self.path).path
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            body = json.loads(self.rfile.read(n).decode()) if n else {}
        except Exception:
            body = {}
        if p == "/api/chat":
            log_hist("ross_msg", body.get("prompt", "")); r = do_chat(body.get("prompt", ""))
            log_hist("reply(" + str(r.get("response_path", "")) + ")", r.get("reply", "")); return self._j(200, r)
        if p == "/api/decision":
            log_hist("decision:" + str(body.get("decision")), str(body.get("note", ""))); return self._j(200, {"ok": True, "logged": body.get("decision"), "execution": False, "ts": utc()})
        if p == "/api/council_action":
            hq = discover_hq(); act = body.get("action"); tid = body.get("id"); note = body.get("note", "")
            if not hq or not tid:
                return self._j(400, {"ok": False, "error": "need HQ + task id"})
            route = {"ack": "/tasks/ack", "note": "/tasks/note", "decline": "/tasks/note"}.get(act, "/tasks/note")
            txt = note if act != "decline" else ("DECLINED by %s: %s" % (CFG["worker_id"], note))
            r = _post(hq + route, {"id": tid, "actor": CFG["worker_id"], "text": txt})
            log_hist("council_" + str(act), "%s -> %s" % (tid, str(r)[:60])); return self._j(200, r)
        return self._j(404, {"error": "not_found"})


def main():
    ap = argparse.ArgumentParser()
    for k in ("worker-id", "name", "title", "host"):
        ap.add_argument("--" + k, required=(k in ("worker-id", "name", "host")), default="")
    ap.add_argument("--runtime-port", type=int, required=True); ap.add_argument("--legacy-port", type=int, required=True)
    ap.add_argument("--model", default="llama3.2"); ap.add_argument("--port", type=int, default=9120)
    ap.add_argument("--accent", default="gold")
    a = ap.parse_args()
    acc = {"gold": ("#f2c14e", "#39d0d8"), "purple": ("#b98cff", "#ff6ad5")}.get(a.accent, ("#f2c14e", "#39d0d8"))
    CFG.update({"worker_id": a.worker_id, "name": a.name, "title": a.title, "host": a.host,
                "runtime_port": a.runtime_port, "legacy_port": a.legacy_port, "model": a.model, "port": a.port,
                "acc": acc[0], "acc2": acc[1], "conn": "Wi-Fi", "last_infer": None})
    log_hist("cockpit_start", "%s cockpit v3 on %s:%d" % (a.worker_id, a.host, a.port))
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()


if __name__ == "__main__":
    main()
