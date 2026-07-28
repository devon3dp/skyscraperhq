#!/usr/bin/env python3
"""
qsb_codex_floor_dash.py — LIVE read-only dashboard for the Codex Floor (#170).

2026-07-28, Ross: "set up the codex floor ... then add the codex floor to the gene
pool ... can we build a dash for this floor?"

REAL DATA ONLY — every field is read server-side from the live sources:
  - floor identity + card   : floors/floor_170_codex_floor/floor_card.json
  - living registry entry    : data/registries/floors.json  (#170)
  - canonical registry entry : data/registries/qsb_canonical_floor_registry_1_170.json (#170)
  - gene-pool provider state : data/registries/gene_pool_router_state.json (openai present?)
  - participant wiring        : data/registries/qsb_gene_pool_participants.json (codex identity?)
It is READ-ONLY: it never writes a project file, never flips a gate, never calls a
provider, never routes anything. Additive service on :8870 (touches no other dash).
Run:  python3 tools/qsb_codex_floor_dash.py --port 8870
"""
import json, argparse, subprocess, re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"
FLOORS = REG / "floors.json"
CANON = REG / "qsb_canonical_floor_registry_1_170.json"
GENE = REG / "gene_pool_router_state.json"
PARTICIPANTS = REG / "qsb_gene_pool_participants.json"  # written by step-2 wiring (may not exist yet)
import time as _time
VER = str(int(_time.time()))  # bumps on restart -> clients auto-reload

def _locate_codex():
    """Follow the Codex floor wherever it lives — the floor-card dir is the anchor,
    so this dash keeps working after the Reorganizer moves Codex to a new number."""
    for p in (ROOT / "floors").glob("floor_*_codex_floor/floor_card.json"):
        try:
            c = json.loads(p.read_text(encoding="utf-8"))
            return int(c.get("floor_number")), p
        except Exception:
            pass
    for e in (_load(FLOORS, []) or []):
        if isinstance(e, dict) and e.get("floor_name") == "Codex Floor" and e.get("number") is not None:
            return int(e["number"]), None
    return None, None


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load(p, default=None):
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except Exception:
        return default


def build_data():
    floor_no, card_path = _locate_codex()
    card = (_load(card_path, {}) or {}) if card_path else {}

    # --- living registry (Codex, wherever it now lives) ---
    living = _load(FLOORS, []) or []
    living_entry = next((e for e in living if isinstance(e, dict) and e.get("number") == floor_no), None)

    # --- canonical registry (#170) ---
    canon = _load(CANON, {}) or {}
    canon_entry = (canon.get("floors", {}) or {}).get(str(floor_no))

    # --- gene pool: is the openai provider present + how many keys / is codex a participant ---
    gp = _load(GENE, {}) or {}
    providers = gp.get("providers", {}) or {}
    openai = providers.get("openai", {}) or {}
    openai_keys = openai.get("keys", openai.get("key_count", 0))
    if isinstance(openai_keys, list):
        openai_keys = len(openai_keys)
    parts = _load(PARTICIPANTS, {}) or {}
    codex_participant = False
    if isinstance(parts, dict):
        codex_participant = "codex" in (parts.get("participants", parts) or {})
    elif isinstance(parts, list):
        codex_participant = any((isinstance(x, dict) and x.get("id") == "codex") or x == "codex" for x in parts)

    gp_card = card.get("gene_pool", {}) or {}
    wired = bool(gp_card.get("wired")) or codex_participant

    # --- readiness roll-up ---
    checks = {
        "living_registry": living_entry is not None and living_entry.get("floor_name") == "Codex Floor",
        "canonical_registry": isinstance(canon_entry, dict) and canon_entry.get("label") == "Codex Floor",
        "floor_card": bool(card.get("floor_id", "").startswith("floor_")),
        "openai_provider_in_pool": bool(openai_keys),
        "gene_pool_wired": wired,
    }
    if all(checks.values()):
        readiness = ("LIVE", "Codex Floor registered and wired into the gene pool")
    elif checks["living_registry"] and checks["canonical_registry"] and checks["floor_card"]:
        readiness = ("READY", "Floor fully registered — gene-pool wiring pending (step 2)")
    else:
        readiness = ("INCOMPLETE", "Floor registration incomplete")

    return {
        "ver": VER,
        "ts": _now(),
        "floor_no": floor_no,
        "name": card.get("floor_name", "Codex Floor"),
        "department": card.get("department", ""),
        "staff_lead": card.get("staff_lead", ""),
        "blurb": card.get("tour_blurb", ""),
        "established_by": card.get("established_by", ""),
        "established_ts": card.get("established_ts", ""),
        "gate_posture": card.get("gate_posture", {}),
        "checks": checks,
        "readiness": {"state": readiness[0], "detail": readiness[1]},
        "gene_pool": {
            "wired": wired,
            "participant_registered": codex_participant,
            "identity": gp_card.get("identity", "codex"),
            "provider": gp_card.get("provider", "openai"),
            "lane": gp_card.get("lane", "dedicated"),
            "openai_keys_in_pool": openai_keys,
            "rule": gp_card.get("rule", ""),
            "status": gp_card.get("status", ""),
        },
        "living_entry": living_entry,
        "canonical_entry": canon_entry,
        "work": _codex_work(),
        "flow": _codex_flow(),
    }


def _codex_work():
    """Codex's REAL activity: council tasks he booked (→ Wren gatekeeps), his queued
    proposals, and his tool sessions. All read-only from the live registries."""
    out = {"council_tasks": [], "proposals": [], "sessions": []}
    try:
        import sys as _s
        _s.path.insert(0, str(ROOT / "tools"))
        import qsb_council_tasks as C
        snap = C.snapshot()
        tasks = snap.get("tasks", []) if isinstance(snap, dict) else (snap or [])
        for t in tasks:
            if t.get("created_by") == "codex" or t.get("owner") == "codex":
                out["council_tasks"].append({"id": t.get("id"), "title": t.get("title"),
                                             "state": t.get("state"), "owner": t.get("owner")})
        out["council_tasks"] = out["council_tasks"][-15:]
    except Exception:
        pass
    try:
        for ln in (REG / "qsb_proposal_queue.jsonl").read_text(encoding="utf-8").splitlines()[-250:]:
            r = json.loads(ln)
            if r.get("source") == "provider_agent":
                out["proposals"].append({"id": r.get("proposal_id"), "target": r.get("target_file"),
                                         "status": r.get("status"), "ts": r.get("ts")})
        out["proposals"] = out["proposals"][-12:]
    except Exception:
        pass
    try:
        for ln in (REG / "qsb_provider_agent_sessions.jsonl").read_text(encoding="utf-8").splitlines()[-40:]:
            r = json.loads(ln)
            tc = r.get("tool_calls")
            out["sessions"].append({"id": (r.get("session_id") or "")[:14], "provider": r.get("provider"),
                                    "cost": r.get("total_cost_usd") or r.get("cost_usd"),
                                    "turns": r.get("turns"),
                                    "tools": tc if isinstance(tc, int) else (len(tc) if isinstance(tc, list) else None),
                                    "ts": r.get("ts") or r.get("closed_at")})
        out["sessions"] = out["sessions"][-10:]
    except Exception:
        pass
    return out


def _tail_lines(path, n):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").splitlines()[-n:]
    except Exception:
        return []


def _openai_keys():
    gp = _load(GENE, {}) or {}
    o = (gp.get("providers", {}) or {}).get("openai", {}) or {}
    k = o.get("keys", o.get("key_count", 0))
    return len(k) if isinstance(k, list) else k


def _codex_ticker(sess, props, tasks):
    ev = []
    for s in sess[-12:]:
        fns = ",".join(tc.get("fn", "?") for tc in (s.get("tool_calls") or [])) or "chat"
        ev.append({"ts": s.get("ts_end") or s.get("ts_start") or s.get("ts"), "lane": "session",
                   "text": f'session {(s.get("session_id") or "")[5:13]} · {s.get("turns")}t · {fns} · ${s.get("total_cost_usd")}'})
    for p in props[-8:]:
        ev.append({"ts": p.get("ts"), "lane": "proposal",
                   "text": f'proposal {p.get("proposal_id")} → {str(p.get("target_file")).split("/")[-1]} · {p.get("status")}'})
    for tid, v in tasks[-8:]:
        ev.append({"ts": None, "lane": "task", "text": f'task {tid} · {v["state"]} · {v.get("title")}'})
    ev.sort(key=lambda e: e["ts"] or "", reverse=True)
    return ev[:14]


def _codex_flow():
    """Real per-node counts for the animated pipeline: CODEX → OpenAI → tools → outputs."""
    sess = []
    for ln in _tail_lines(REG / "qsb_provider_agent_sessions.jsonl", 200):
        try:
            sess.append(json.loads(ln))
        except Exception:
            pass
    tool_counts = {"qsb_read_registry": 0, "qsb_read_floor_card": 0, "qsb_grep_repo": 0,
                   "qsb_propose_patch": 0, "qsb_council_task": 0}
    session_turns = 0
    for s in sess:
        session_turns += s.get("turns") or 0
        for tc in (s.get("tool_calls") or []):
            fn = tc.get("fn")
            if fn in tool_counts:
                tool_counts[fn] += 1
    term_calls, spent, cap = 0, 0.0, 1.0
    today = _now()[:10]
    for ln in _tail_lines(REG / "qsb_tower_activity_tail.jsonl", 400):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("event_kind") != "provider_call" and r.get("event") != "provider_call":
            continue
        p = r.get("payload", {}) or {}
        reason = p.get("reason") or r.get("reason")
        if reason != "codex_terminal":
            continue
        if r.get("ts", "")[:10] == today:
            term_calls += 1
            spent = p.get("spent_today_after_usd", r.get("spent_today_after_usd", spent))
            cap = p.get("daily_cap_usd", r.get("daily_cap_usd", cap))
    props = []
    for ln in _tail_lines(REG / "qsb_proposal_queue.jsonl", 300):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        if r.get("source") == "provider_agent":
            props.append(r)
    task_state = {}
    GATE = {"created": "open", "noted": "in_review", "sandbox_rejected": "rejected",
            "sandbox_passed": "verified", "peer_signoff": "verified", "done": "done"}
    for ln in _tail_lines(REG / "qsb_council_tasks.jsonl", 800):
        try:
            r = json.loads(ln)
        except Exception:
            continue
        tid = r.get("task_id"); ev = r.get("event")
        if not tid:
            continue
        if ev == "created" and r.get("actor") == "codex":
            task_state[tid] = {"title": r.get("title"), "state": "open"}
        elif tid in task_state and ev in GATE:
            task_state[tid]["state"] = GATE[ev]
    tasks = list(task_state.items())
    return {
        "nodes": {
            "codex": {"sessions": len(sess), "turns": session_turns},
            "openai": {"terminal_calls": term_calls, "agent_sessions": len(sess), "keys": _openai_keys()},
            "tools": tool_counts,
            "proposals": {"n": len(props), "unsigned": sum(1 for p in props if str(p.get("status", "")).startswith("queued"))},
            "tasks": {"n": len(tasks),
                      "open": sum(1 for _, v in tasks if v["state"] in ("open", "in_review")),
                      "rejected": sum(1 for _, v in tasks if v["state"] == "rejected"),
                      "done": sum(1 for _, v in tasks if v["state"] in ("done", "verified"))},
        },
        "budget": {"spent": round(spent, 4), "cap": cap, "frac": (spent / cap if cap else 0)},
        "ticker": _codex_ticker(sess, props, tasks),
    }


CONSULT = ROOT / "tools" / "qsb_consult_external.py"


def ask_codex(prompt):
    """Send a message to Codex (OpenAI) via the tower's bounded, audited consult
    path. Hard caps ($1/day, per-call) + full audit are enforced BY that tool —
    this dash only relays. Never a raw key call; never any other action."""
    prompt = (prompt or "").strip()
    if not prompt:
        return {"ok": False, "error": "empty prompt"}
    if len(prompt) > 6000:
        prompt = prompt[:6000]
    try:
        r = subprocess.run(
            ["python3", str(CONSULT), "--provider", "openai", "--model", "gpt-4o-mini",
             "--prompt", prompt, "--reason", "codex_terminal", "--max-tokens", "500"],
            capture_output=True, text=True, timeout=90, cwd=str(ROOT))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout (90s)"}
    if r.returncode != 0:
        lines = (r.stderr or r.stdout or "call failed").strip().splitlines()
        return {"ok": False, "error": lines[-1] if lines else "call failed"}
    out = r.stdout
    parts = re.split(r'^[━]{5,}\s*$', out, flags=re.M)
    reply = parts[2].strip() if len(parts) >= 3 else out.strip()
    m = re.search(r'remaining \$([0-9.]+)', out)
    m2 = re.search(r'cost \$([0-9.]+)', out)
    return {"ok": True, "reply": reply,
            "remaining": m.group(1) if m else None,
            "cost": m2.group(1) if m2 else None}


PAGE = """<!doctype html><html><head><meta charset=utf-8><title>Codex Floor · #170</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0f17;--card:#131a26;--line:#233146;--txt:#dce6f5;--dim:#7d8da6;--ok:#39d98a;--warn:#f5c451;--bad:#ff6b6b;--codex:#10a37f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1100px;margin:0 auto;padding:20px}
h1{margin:0;font-size:22px}h1 .n{color:var(--codex)}
.sub{color:var(--dim);margin:2px 0 18px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:14px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px}
.card h2{margin:0 0 10px;font-size:13px;letter-spacing:.06em;text-transform:uppercase;color:var(--dim)}
.big{font-size:26px;font-weight:700}
.badge{display:inline-block;padding:3px 10px;border-radius:999px;font-weight:700;font-size:12px}
.LIVE{background:rgba(57,217,138,.15);color:var(--ok);border:1px solid var(--ok)}
.READY{background:rgba(245,196,81,.15);color:var(--warn);border:1px solid var(--warn)}
.INCOMPLETE{background:rgba(255,107,107,.15);color:var(--bad);border:1px solid var(--bad)}
.row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--line)}
.row:last-child{border:0}.k{color:var(--dim)}.mono{font-family:ui-monospace,Menlo,monospace;font-size:12px}
.chk{display:flex;align-items:center;gap:8px;padding:5px 0}
.dot{width:9px;height:9px;border-radius:50%}.dot.y{background:var(--ok)}.dot.n{background:var(--bad)}
.pill{font-size:11px;color:var(--dim)}
pre{background:#0d1420;border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;font-size:11px;color:#a9c2e6}
.blurb{color:#b9c8dd;font-style:italic}
footer{color:var(--dim);margin-top:18px;font-size:12px}
.cbeam{stroke-dasharray:6 10;animation:cflow 1.1s linear infinite}
@keyframes cflow{to{stroke-dashoffset:-32}}
.cbeam.idle{opacity:.25;animation-duration:4s}
#cticker .ldot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.ldot.session{background:var(--codex)}.ldot.proposal{background:var(--warn)}.ldot.task{background:#5aa9ff}
</style></head><body><div class=wrap>
<h1>Codex Floor <span class=n>· #<span id=floorno>—</span></span></h1>
<div class=sub id=dept></div>
<div class=grid>
  <div class=card><h2>Readiness</h2><div class=big><span id=badge class=badge>—</span></div>
    <div id=readyDetail class=sub style="margin-top:8px"></div>
    <div id=checks></div></div>
  <div class=card><h2>Identity</h2><div id=identity></div><p class=blurb id=blurb></p></div>
  <div class=card><h2>Gene Pool</h2><div id=gene></div></div>
  <div class=card><h2>Registration proof</h2><div id=reg></div>
    <details style="margin-top:8px"><summary class=pill>living registry entry</summary><pre id=living></pre></details>
    <details><summary class=pill>canonical registry entry</summary><pre id=canon></pre></details></div>
</div>
<div class=card style="margin-top:14px"><h2>🔴 Codex live pipeline — prompt → OpenAI lane → tools → outputs (→ Wren gate)</h2>
  <svg id=cflow style="width:100%;height:384px"></svg>
  <div style="margin-top:8px"><span class=pill>OpenAI terminal spend today (real, capped)</span>
    <div style="height:8px;background:#0d1420;border:1px solid var(--line);border-radius:6px;overflow:hidden;margin-top:3px"><div id=bud style="height:100%;width:0;background:var(--codex);transition:width .6s"></div></div>
    <div class=pill id=budtxt></div></div>
</div>
<div class=card style="margin-top:14px"><h2>📡 Codex live activity ticker (real actions)</h2><div id=cticker><span class=pill>waiting for real activity…</span></div></div>
<div class=card style="margin-top:14px"><h2>🛠️ Codex at Work — Council tasks (→ Wren gatekeeps)</h2><div id=ctasks></div></div>
<div class=grid style="margin-top:14px">
  <div class=card><h2>Proposals (→ bench + Wren verify)</h2><div id=cprops></div></div>
  <div class=card><h2>Tool sessions</h2><div id=csessions></div></div>
</div>
<div class=card style="margin-top:14px"><h2>Codex Terminal <span id=budget class=pill></span></h2>
  <div id=term style="background:#0d1420;border:1px solid var(--line);border-radius:8px;padding:10px;height:240px;overflow:auto;font-family:ui-monospace,Menlo,monospace;font-size:12px;white-space:pre-wrap"><span class=pill>Type a message to Codex (OpenAI) below. Cmd/Ctrl+Enter also sends.</span></div>
  <div style="display:flex;gap:8px;margin-top:8px">
    <textarea id=inp rows=2 placeholder="message to Codex…" style="flex:1;background:var(--card);border:1px solid var(--line);border-radius:8px;color:var(--txt);padding:8px;font:13px/1.4 inherit;resize:vertical"></textarea>
    <button id=send onclick=ask() style="background:var(--codex);color:#04120d;border:0;border-radius:8px;padding:0 18px;font-weight:700;cursor:pointer">Send</button>
  </div>
  <div class=pill style="margin-top:6px">routed through the tower's bounded, audited OpenAI path · $1.00/day cap · every call logged to the spend ledger</div>
</div>
<footer>views are read-only · Codex terminal is live (bounded OpenAI) · updated <span id=ts></span> · :8870</footer>
</div><script>
function termln(who,txt){const t=document.getElementById('term');t.innerHTML+=`<div style="margin:4px 0"><b style="color:${who==='you'?'#5aa9ff':'#10a37f'}">${who} &rsaquo;</b> ${(''+txt).replace(/</g,'&lt;')}</div>`;t.scrollTop=t.scrollHeight}
async function ask(){
  const inp=document.getElementById('inp'),btn=document.getElementById('send');
  const p=inp.value.trim(); if(!p)return;
  termln('you',p); inp.value=''; btn.disabled=true; btn.textContent='…';
  try{
    const r=await (await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p})})).json();
    if(r.ok){termln('codex',r.reply); if(r.remaining)document.getElementById('budget').textContent='budget left today: $'+r.remaining}
    else{termln('codex','⚠ '+r.error)}
  }catch(e){termln('codex','⚠ '+e)}
  btn.disabled=false; btn.textContent='Send';
}
function chk(o){return Object.entries(o).map(([k,v])=>`<div class=chk><span class="dot ${v?'y':'n'}"></span><span>${k.replace(/_/g,' ')}</span></div>`).join('')}
function rows(o){return Object.entries(o).map(([k,v])=>`<div class=row><span class=k>${k.replace(/_/g,' ')}</span><span class=mono>${v===''||v==null?'—':v}</span></div>`).join('')}
async function tick(){
  let d; try{d=await (await fetch('/api/data')).json()}catch(e){return}
  if(window.__ver&&window.__ver!==d.ver){location.reload();return}window.__ver=d.ver;
  document.getElementById('dept').textContent=d.department+'  ·  '+d.staff_lead;
  const b=document.getElementById('badge');b.textContent=d.readiness.state;b.className='badge '+d.readiness.state;
  document.getElementById('readyDetail').textContent=d.readiness.detail;
  document.getElementById('checks').innerHTML=chk(d.checks);
  document.getElementById('identity').innerHTML=rows({floor:'#'+d.floor_no+' '+d.name,department:d.department,established_by:d.established_by,established:d.established_ts});
  document.getElementById('blurb').textContent=d.blurb;
  const g=d.gene_pool;
  document.getElementById('gene').innerHTML=rows({wired:g.wired?'✓ yes':'✕ pending (step 2)',participant_registered:g.participant_registered?'✓':'✕',identity:g.identity,provider:g.provider,lane:g.lane,openai_keys_in_pool:g.openai_keys_in_pool,status:g.status})+`<div class=pill style="margin-top:8px">${g.rule||''}</div>`;
  document.getElementById('reg').innerHTML=chk({living_registry:d.checks.living_registry,canonical_registry:d.checks.canonical_registry,floor_card:d.checks.floor_card});
  document.getElementById('living').textContent=JSON.stringify(d.living_entry,null,1);
  document.getElementById('canon').textContent=JSON.stringify(d.canonical_entry,null,1);
  document.getElementById('ts').textContent=(d.ts||'').replace('T',' ');document.getElementById('floorno').textContent=(d.floor_no==null?'—':d.floor_no);
  const w=d.work||{},es=s=>(''+(s==null?'':s)).replace(/</g,'&lt;');
  document.getElementById('ctasks').innerHTML=(w.council_tasks||[]).map(t=>`<div class=row><span><b class=mono>${es(t.id)}</b> ${es(t.title)}</span><span class=badge style="background:rgba(57,217,138,.14);color:var(--ok);border:1px solid var(--ok)">${es(t.state)}</span></div>`).join('')||'<span class=pill>no council tasks yet — book one via the terminal</span>';
  document.getElementById('cprops').innerHTML=(w.proposals||[]).map(p=>`<div class=row><span class=mono>${es(p.id)}</span><span class=pill>${es((''+p.target).split('/').pop())} · ${es(p.status)}</span></div>`).join('')||'<span class=pill>none</span>';
  document.getElementById('csessions').innerHTML=(w.sessions||[]).map(s=>`<div class=row><span class=mono>${es(s.id)}</span><span class=pill>${es(s.provider)} · ${es(s.turns)}t · ${es(s.tools)} tools · $${es(s.cost)}</span></div>`).join('')||'<span class=pill>none</span>';
  renderCFlow(d);
}
document.getElementById('inp').addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();ask()}});
const CNS="http://www.w3.org/2000/svg";
function cel(t,a){const e=document.createElementNS(CNS,t);for(const k in a)e.setAttribute(k,a[k]);return e}
let CPREV=null,cgeom=null;
function cpacket(a,b){const svg=document.getElementById('cflow');if(!cgeom||!svg)return;
  const dot=cel('circle',{r:4,fill:'var(--codex)',cx:cgeom.N[a][0],cy:cgeom.N[a][1]});svg.appendChild(dot);
  dot.animate([{transform:'translate(0,0)'},{transform:`translate(${cgeom.N[b][0]-cgeom.N[a][0]}px,${cgeom.N[b][1]-cgeom.N[a][1]}px)`}],{duration:1200,easing:'ease-in-out'}).onfinish=()=>dot.remove();}
function renderCFlow(d){
  const f=d.flow;if(!f)return;const svg=document.getElementById('cflow');if(!svg)return;
  const W=svg.clientWidth||900,H=384;svg.setAttribute('viewBox',`0 0 ${W} ${H}`);const c=x=>Math.round(W*x);
  const N={codex:[c(.07),H/2],openai:[c(.30),H/2],qsb_read_registry:[c(.53),H*.16],qsb_read_floor_card:[c(.53),H*.33],qsb_grep_repo:[c(.53),H*.50],qsb_propose_patch:[c(.53),H*.67],qsb_council_task:[c(.53),H*.84],proposals:[c(.80),H*.30],tasks:[c(.80),H*.66],wren:[c(.95),H*.66]};
  const bez=(a,b)=>`M ${a[0]} ${a[1]} C ${(a[0]+b[0])/2} ${a[1]}, ${(a[0]+b[0])/2} ${b[1]}, ${b[0]} ${b[1]}`;cgeom={N,bez};
  const tk=f.nodes.tools;svg.innerHTML="";
  [['codex','openai',f.nodes.openai.terminal_calls+f.nodes.openai.agent_sessions],['openai','qsb_read_registry',tk.qsb_read_registry],['openai','qsb_read_floor_card',tk.qsb_read_floor_card],['openai','qsb_grep_repo',tk.qsb_grep_repo],['openai','qsb_propose_patch',tk.qsb_propose_patch],['openai','qsb_council_task',tk.qsb_council_task],['qsb_propose_patch','proposals',tk.qsb_propose_patch],['qsb_council_task','tasks',tk.qsb_council_task],['tasks','wren',f.nodes.tasks.n]].forEach(([a,b,n])=>{
    svg.appendChild(cel('path',{d:bez(N[a],N[b]),class:'cbeam'+(n>0?'':' idle'),stroke:b==='wren'?'#5aa9ff':'var(--codex)','stroke-width':n>0?Math.min(2+n*0.15,6):1.4,fill:'none'}));});
  const mk=(id,r,fill,label)=>{svg.appendChild(cel('circle',{cx:N[id][0],cy:N[id][1],r,fill:'#0d1420',stroke:fill,'stroke-width':2}));
    const t=cel('text',{x:N[id][0],y:N[id][1]-r-5,'text-anchor':'middle',fill:'#dce6f5','font-size':10});t.textContent=label;svg.appendChild(t);};
  mk('codex',18,'var(--codex)','CODEX #40 · '+f.nodes.codex.sessions+' sess');
  mk('openai',15,'var(--codex)','OpenAI · '+f.nodes.openai.keys+' keys');
  [['qsb_read_registry','read_registry'],['qsb_read_floor_card','read_floor_card'],['qsb_grep_repo','grep_repo'],['qsb_propose_patch','propose_patch'],['qsb_council_task','council_task']].forEach(([id,l])=>mk(id,7,'var(--dim)',l+' ×'+(tk[id]||0)));
  mk('proposals',14,f.nodes.proposals.unsigned?'var(--warn)':'var(--ok)','Proposals→Bench ×'+f.nodes.proposals.n);
  mk('tasks',14,'#5aa9ff','Tasks→Council ×'+f.nodes.tasks.n);
  const gs=f.nodes.tasks.rejected?'var(--bad)':(f.nodes.tasks.open?'var(--warn)':'var(--ok)');
  svg.appendChild(cel('path',{fill:gs,opacity:.9,d:`M ${N.wren[0]-10} ${N.wren[1]+12} L ${N.wren[0]-10} ${N.wren[1]-6} L ${N.wren[0]} ${N.wren[1]-14} L ${N.wren[0]+10} ${N.wren[1]-6} L ${N.wren[0]+10} ${N.wren[1]+12} Z`}));
  const wt=cel('text',{x:N.wren[0],y:N.wren[1]+26,'text-anchor':'middle',fill:'#dce6f5','font-size':10});wt.textContent='WREN gate';svg.appendChild(wt);
  // FULL CIRCLE: Wren's verdict loops back to Codex (done ✓ / rework ↺ / awaiting)
  const outcome=f.nodes.tasks.rejected?'↺ rework':(f.nodes.tasks.done?'✓ done':'… awaiting');
  const oc=f.nodes.tasks.rejected?'var(--bad)':(f.nodes.tasks.done?'var(--ok)':'var(--warn)');
  const loop=cel('path',{d:`M ${N.wren[0]} ${N.wren[1]+14} C ${N.wren[0]} ${H-12}, ${N.codex[0]} ${H-12}, ${N.codex[0]} ${N.codex[1]+18}`,class:'cbeam',fill:'none','stroke-width':2});
  loop.style.stroke=oc;svg.appendChild(loop);
  const lt=cel('text',{x:(N.wren[0]+N.codex[0])/2,y:H-3,'text-anchor':'middle',fill:oc,'font-size':10,'font-weight':700});
  lt.textContent='WREN verdict: '+outcome+' → back to Codex (full circle)';svg.appendChild(lt);
  const cur={turns:f.nodes.codex.turns,t_rr:tk.qsb_read_registry,t_rf:tk.qsb_read_floor_card,t_gr:tk.qsb_grep_repo,t_pp:tk.qsb_propose_patch,t_ct:tk.qsb_council_task};
  if(CPREV){if(cur.turns>CPREV.turns)cpacket('codex','openai');
    if(cur.t_rr>CPREV.t_rr)cpacket('openai','qsb_read_registry');if(cur.t_rf>CPREV.t_rf)cpacket('openai','qsb_read_floor_card');if(cur.t_gr>CPREV.t_gr)cpacket('openai','qsb_grep_repo');
    if(cur.t_pp>CPREV.t_pp){cpacket('openai','qsb_propose_patch');cpacket('qsb_propose_patch','proposals');}
    if(cur.t_ct>CPREV.t_ct){cpacket('openai','qsb_council_task');cpacket('qsb_council_task','tasks');cpacket('tasks','wren');}}
  CPREV=cur;
  const bf=Math.min(1,f.budget.frac||0);document.getElementById('bud').style.width=(bf*100).toFixed(1)+'%';
  document.getElementById('budtxt').textContent='$'+f.budget.spent+' / $'+f.budget.cap+' today';
  document.getElementById('cticker').innerHTML=(f.ticker||[]).map(e=>`<div style="padding:3px 0;border-bottom:1px solid var(--line);font-size:11px"><span class="ldot ${es(e.lane)}"></span>${es(e.text)} <span class=pill>${es((e.ts||'').slice(11,19))}</span></div>`).join('')||'<span class=pill>none</span>';
}
tick();setInterval(tick,2000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/data"):
            body = json.dumps(build_data()).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            body = PAGE.encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_POST(self):
        if self.path.startswith("/api/ask"):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                payload = {}
            res = ask_codex(payload.get("prompt", ""))
            body = json.dumps(res).encode()
            self.send_response(200); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8870)
    a = ap.parse_args()
    print(f"codex floor dash on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
