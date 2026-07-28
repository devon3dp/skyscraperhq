#!/usr/bin/env python3
"""
qsb_council_live_dash.py — LIVE ANIMATED Task Council flow dashboard (:8864).

2026-07-28, Ross: "liveflow diagrams animations!!!!" — an animated pipeline of the
council actually working: Open → Claimed → Sandbox → Quorum Verify → Wren Gate → Done.

EVERYTHING REAL — every pulse is a real event, every count a real task:
  - task board / states : data/registries/qsb_council_tasks_snapshot.json
  - live motion (pulses) : data/registries/qsb_council_tasks.jsonl  (append-only event log)
  - autorunner health    : data/registries/qsb_autorunner_activity.jsonl + qsb_autorunner_gate.json
No demo motion — a token only glides when a real event newer than last-seen appears.
Read-only. systemd qsb-council-live-dash.service.
"""
import json
from collections import Counter, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REG = Path("/vaults/nvme0/qsb_tower_v1/data/registries")
SNAP = REG / "qsb_council_tasks_snapshot.json"
LOG = REG / "qsb_council_tasks.jsonl"
AUTO_LOG = REG / "qsb_autorunner_activity.jsonl"
AUTO_GATE = REG / "qsb_autorunner_gate.json"
import time as _time
VER = str(int(_time.time()))  # bumps on every service restart -> clients auto-reload

STAGE = {
    "pending_admission": "intake",
    "open": "open", "recycled": "open",
    "claimed": "claimed", "assigned": "claimed", "acknowledged": "claimed",
    "in_progress": "working",
    "awaiting_peer_signoff": "sandbox",
    "awaiting_verification": "quorum", "needs_second_verifier": "quorum",
    "ready_to_ship": "wren_gate",
    "done": "done",
    "blocked": "blocked",
}
COLS = ["open", "claimed", "working", "sandbox", "quorum", "wren_gate", "done"]
EVENT_TO_STAGE = {
    "created": "open", "proposed": "intake", "admission_voted": "open", "recycled": "open",
    "unblocked": "open", "claimed": "claimed", "assigned": "claimed", "acknowledged": "claimed",
    "updated": "working", "noted": "working", "tool_selected": "working",
    "sandbox_passed": "sandbox", "sandbox_rejected": "working",
    "awaiting_verification": "quorum", "peer_signoff": "wren_gate",
    "done": "done", "blocked": "blocked",
}


def _load(p, d):
    try:
        return json.loads(Path(p).read_text(errors="ignore"))
    except Exception:
        return d


def _tail(path, n):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return [json.loads(x) for x in deque(f, maxlen=n) if x.strip()]
    except Exception:
        return []


def build():
    snap = _load(SNAP, {"tasks": []})
    stages = {c: {"count": 0, "tokens": []} for c in COLS}
    stages["intake"] = {"count": 0, "tokens": []}
    stages["blocked"] = {"count": 0, "tokens": []}
    owner_ct, awaiting = Counter(), []
    for t in snap.get("tasks", []):
        col = STAGE.get((t.get("state") or "").lower())
        if not col:
            continue
        stages[col]["count"] += 1
        own = t.get("owner") or t.get("assignee") or ""
        if own:
            owner_ct[own] += 1
        if len(stages[col]["tokens"]) < 40:
            stages[col]["tokens"].append({"id": t["id"], "title": (t.get("title") or t["id"])[:46],
                                          "owner": own, "rework": t.get("rework_rounds", 0)})
        if col in ("sandbox", "quorum"):
            awaiting.append({"id": t["id"], "title": (t.get("title") or t["id"])[:46], "owner": own,
                             "sandbox_by": t.get("sandbox_passed_by"), "signoff_by": t.get("peer_signoff_by"),
                             "verdict": t.get("peer_signoff_verdict"), "rework": t.get("rework_rounds", 0)})

    ev = _tail(LOG, 500)
    actor, ev_types = Counter(), Counter()
    ticker, pulses, edge = [], [], Counter()
    for e in ev:
        st = EVENT_TO_STAGE.get(e.get("event"))
        actor[e.get("actor", "?")] += 1
        ev_types[e.get("event", "?")] += 1
        if not st:
            continue
        to = st
        if e.get("event") == "peer_signoff" and e.get("verdict") == "reject":
            to = "working"
        if e.get("event") == "recycled":
            to = "open"
        edge[to] += 1
        ticker.append({"ts": e.get("ts"), "event": e.get("event"), "task": e.get("task_id"),
                       "actor": e.get("actor", "?"), "verdict": e.get("verdict", ""), "to": to})
    for r in ticker[-22:]:
        pulses.append({"to": r["to"], "actor": r["actor"], "ts": r["ts"], "event": r["event"], "task": r["task"]})

    # ── rating /10 (honest: more corrections = lower) + interactive sign-off queue ──
    def rate(t):
        base = 10 - min(10, t.get("rework_rounds") or 0)
        if t.get("peer_signoff_verdict") == "approve":
            base += 1
        if t.get("peer_signoff_verdict") == "reject":
            base -= 2
        return max(0, min(10, base))

    awaiting_signoff, wstat = [], {}
    for t in snap.get("tasks", []):
        st = (t.get("state") or "").lower()
        if st in ("awaiting_peer_signoff", "awaiting_verification", "ready_to_ship"):
            awaiting_signoff.append({"id": t["id"], "title": (t.get("title") or t["id"])[:64], "state": st,
                                     "owner": t.get("owner"), "rework": t.get("rework_rounds") or 0,
                                     "signoff_by": t.get("peer_signoff_by"), "verdict": t.get("peer_signoff_verdict"),
                                     "rating": rate(t), "created_by": t.get("created_by")})
        who = t.get("owner") or t.get("created_by")
        if who:
            w = wstat.setdefault(who, {"tasks": 0, "done": 0, "rework": 0, "rating": 0})
            w["tasks"] += 1
            w["rework"] += (t.get("rework_rounds") or 0)
            w["rating"] += rate(t)
            if st == "done":
                w["done"] += 1
    awaiting_signoff.sort(key=lambda x: -x["rework"])
    worker_stats = sorted(
        [{"actor": a, "tasks": w["tasks"], "done": w["done"],
          "avg_rework": round(w["rework"] / w["tasks"], 1) if w["tasks"] else 0,
          "avg_rating": round(w["rating"] / w["tasks"], 1) if w["tasks"] else 0} for a, w in wstat.items()],
        key=lambda x: -x["tasks"])[:8]

    codex_feed = sum(1 for t in snap.get("tasks", []) if t.get("created_by") == "codex")
    # what WREN does — her live decision trail on tasks (she's the gatekeeper)
    WREN_ICON = {"claimed": "claimed", "assigned": "assigned partner", "tool_selected": "picked tool",
                 "sandbox_passed": "sandbox ✓", "sandbox_rejected": "sandbox ✕", "peer_signoff": "signed off",
                 "blocked": "blocked", "recycled": "recycled ↺", "done": "marked done ✓",
                 "noted": "noted", "updated": "updated", "created": "created"}
    wren_actions = [{"ts": r["ts"], "event": r["event"], "task": r["task"],
                     "label": WREN_ICON.get(r["event"], r["event"])}
                    for r in ticker if r["actor"] == "wren"][-16:]
    wren_actions.reverse()

    gate = _load(AUTO_GATE, {})
    last = _tail(AUTO_LOG, 1)
    lastt = last[-1] if last else {}
    auto = {"enabled": gate.get("enabled"), "tick": lastt.get("tick"),
            "reason": lastt.get("reason", ""), "ts": lastt.get("ts", ""),
            "stalled": lastt.get("tick") == "skip"}

    return {
        "ver": VER,
        "ts": snap.get("ts"),
        "kpis": {"total": snap.get("total"), "open": snap.get("open"),
                 "in_progress": snap.get("in_progress"), "blocked": snap.get("blocked"),
                 "done": snap.get("done"), "awaiting_verify": len(awaiting)},
        "stages": stages, "edges": dict(edge),
        "actors": dict(actor.most_common(8)),
        "owners": dict(owner_ct.most_common(6)),
        "pulses": pulses, "awaiting": awaiting[:12],
        "autorunner": auto,
        "ticker": list(reversed(ticker[-30:])),
        "awaiting_signoff": awaiting_signoff[:14],
        "worker_stats": worker_stats,
        "codex_feed": codex_feed,
        "wren_actions": wren_actions,
    }


def act(payload):
    """Ross's OWNER gate — accept/reject a task escalated to him. Recorded as
    ross_knechtel (his own authority), never a faked peer quorum. Append-only."""
    tid = payload.get("task_id")
    action = payload.get("action")
    note = (payload.get("note") or "")[:300]
    if not tid or action not in ("accept", "reject"):
        return {"ok": False, "error": "bad request"}
    snap = _load(SNAP, {"tasks": []})
    t = next((x for x in snap.get("tasks", []) if x.get("id") == tid), None)
    if not t:
        return {"ok": False, "error": "task not found"}
    if (t.get("state") or "").lower() not in ("awaiting_peer_signoff", "awaiting_verification", "ready_to_ship"):
        return {"ok": False, "error": "task is not awaiting sign-off"}
    import sys
    sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
    try:
        import qsb_council_tasks as C
        if action == "accept":
            C.note(tid, "ross_knechtel", "ACCEPTED by Ross via dash" + (": " + note if note else ""))
            C.update(tid, "ross_knechtel", state="done")
        else:
            C.note(tid, "ross_knechtel", "REJECTED by Ross via dash" + (": " + note if note else ""))
            C.update(tid, "ross_knechtel", state="blocked")
        return {"ok": True, "action": action, "task": tid}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


PAGE = r"""<!doctype html><html><head><meta charset=utf-8><title>Task Council · Live Flow · :8864</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0f17;--card:#131a26;--line:#233146;--txt:#dce6f5;--dim:#7d8da6;--wren:#8a5cf6;--tp:#5aa9ff;--asa:#39d98a;--bill:#f5c451;--codex:#ff9d5c;--bad:#ff6b6b;--ok:#39d98a;--warn:#f5c451}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);font:13px/1.45 -apple-system,Segoe UI,Roboto,sans-serif}
.wrap{max-width:1340px;margin:0 auto;padding:16px}
h1{margin:0;font-size:20px}h1 .n{color:var(--wren)}
.sub{color:var(--dim);margin:2px 0 10px;font-style:italic}
.kpis{display:flex;gap:9px;flex-wrap:wrap;margin-bottom:10px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:9px;padding:7px 13px}
.kpi .v{font-size:19px;font-weight:700}.kpi .l{color:var(--dim);font-size:10px;text-transform:uppercase}
.auto{padding:8px 13px;border-radius:9px;margin-bottom:10px;font-size:12px;border:1px solid var(--line)}
.auto.ok{background:rgba(57,217,138,.10);border-color:var(--ok)}
.auto.stall{background:rgba(255,107,107,.12);border-color:var(--bad)}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:12px}
.card h2{margin:0 0 8px;font-size:12px;letter-spacing:.05em;text-transform:uppercase;color:var(--dim)}
#flow{width:100%;height:400px}
.beam{fill:none;stroke:var(--line);stroke-width:2;stroke-dasharray:6 10;animation:march var(--spd,4s) linear infinite;opacity:.4}
@keyframes march{to{stroke-dashoffset:-160}}
.bay{fill:#0d1420;stroke:var(--line);stroke-width:1.5}
.baylabel{fill:var(--dim);font-size:10px;text-transform:uppercase}
.baycount{fill:var(--txt);font-size:22px;font-weight:700}
.wgate{fill:#0d1420;stroke:var(--wren);stroke-width:2}
.wgate.act{animation:wpulse 1.1s ease-out}
@keyframes wpulse{0%{stroke-width:2}45%{stroke-width:6;filter:drop-shadow(0 0 16px var(--wren))}100%{stroke-width:2}}
.pulse{filter:drop-shadow(0 0 6px currentColor)}
.lanedot.act{animation:blink .9s ease-out}
@keyframes blink{0%{r:5}50%{r:11;opacity:1}100%{r:5;opacity:.5}}
.cols2{display:grid;grid-template-columns:1fr 340px;gap:12px}@media(max-width:900px){.cols2{grid-template-columns:1fr}}
.tickrow{border-bottom:1px solid var(--line);padding:3px 4px;font-size:11px;display:flex;gap:7px}
.tickrow.new{animation:flashin 1.5s ease-out}
@keyframes flashin{from{background:rgba(138,92,246,.22)}to{background:transparent}}
.av{border-bottom:1px solid var(--line);padding:5px 0;font-size:11px}
.mono{font-family:ui-monospace,monospace}.pill{color:var(--dim);font-size:11px}.dim{color:var(--dim)}
.badge{font-size:9px;padding:1px 6px;border-radius:999px;border:1px solid var(--line)}
</style></head><body><div class=wrap>
<h1>Task Council <span class=n>· Live Flow · :8864</span></h1>
<div class=sub>Every pulse is a real event from qsb_council_tasks.jsonl. No demo motion.</div>
<div class=kpis>
  <div class=kpi><div class=v id=kTotal>—</div><div class=l>tasks</div></div>
  <div class=kpi><div class=v id=kOpen>—</div><div class=l>open</div></div>
  <div class=kpi><div class=v id=kVerify>—</div><div class=l>awaiting verify</div></div>
  <div class=kpi><div class=v id=kBlocked>—</div><div class=l>blocked</div></div>
  <div class=kpi><div class=v id=kDone>—</div><div class=l>done</div></div>
</div>
<div class=auto id=auto>—</div>
<div class=card><h2>Live pipeline — Open → Claimed → Sandbox → Quorum → Wren Gate → Done</h2><svg id=flow></svg></div>
<div class=card><h2>✅ Awaiting YOUR sign-off — tick to keep the council moving</h2><div id=signoff></div></div>
<div class=card><h2>Worker ratings /10 — real, from corrections &amp; rework</h2><div id=wstats></div></div>
<div class=card><h2>🟣 What Wren's doing — live gatekeeper decisions</h2><div id=wren></div></div>
<div class=cols2>
  <div class=card><h2>Live event ticker (real council actions)</h2><div id=ticker></div></div>
  <div>
    <div class=card><h2>Awaiting verification (Wren + quorum)</h2><div id=await></div></div>
    <div class=card><h2>Who's active now</h2><div id=actors></div></div>
  </div>
</div>
</div><script>
const NS="http://www.w3.org/2000/svg";
const COLS=["open","claimed","working","sandbox","quorum","wren_gate","done"];
const LABEL={open:"Open",claimed:"Claimed",working:"Working",sandbox:"Sandbox",quorum:"Quorum Verify",wren_gate:"Wren Gate",done:"Done"};
const ACTORC={wren:"#8a5cf6",tp_pip:"#5aa9ff",acer_cass:"#39d98a",bill:"#f5c451",codex:"#ff9d5c",sandbox_gate:"#ff6b6b",ross:"#cfd6e2"};
function el(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e}
function esc(s){return (''+(s==null?'':s)).replace(/</g,'&lt;')}
const svg=document.getElementById("flow");let bayX={},seen=new Set(),first=true;
function carriage(x,y,col,title){
  const g=el("g",{});
  g.appendChild(el("rect",{x:x-17,y:y,width:34,height:11,rx:3,fill:col,opacity:.92}));
  g.appendChild(el("rect",{x:x-13,y:y+2,width:8,height:4,rx:1,fill:"#0b0f17",opacity:.45}));
  g.appendChild(el("circle",{cx:x-9,cy:y+13,r:2,fill:"#1a2740"}));
  g.appendChild(el("circle",{cx:x+9,cy:y+13,r:2,fill:"#1a2740"}));
  if(title){const t=el("title");t.textContent=title;g.appendChild(t);}
  return g;
}
function draw(d){
  svg.innerHTML="";const W=svg.clientWidth||1200,H=400;svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  const pad=66,tY=142,rg=8;
  const gap=(W-2*pad)/(COLS.length-1);
  COLS.forEach((c,i)=>bayX[c]=pad+i*gap);
  const x0=pad-30,x1=W-pad+30;
  // sleepers + two rails = the train track
  for(let x=x0;x<=x1;x+=15)svg.appendChild(el("line",{x1:x,y1:tY-rg,x2:x,y2:tY+rg,stroke:"#2a3a52","stroke-width":3}));
  [tY-rg,tY+rg].forEach(ry=>svg.appendChild(el("line",{x1:x0,y1:ry,x2:x1,y2:ry,stroke:"#5a7aa0","stroke-width":2.5})));
  // return loop — the track curves back = full circle
  svg.appendChild(el("path",{class:"beam",fill:"none",stroke:"#5a7aa0","stroke-width":2.5,d:`M ${x1} ${tY} C ${W-14} ${tY}, ${W-14} ${tY+158}, ${W/2} ${tY+158} C ${14} ${tY+158}, ${14} ${tY}, ${x0} ${tY}`}));
  {const rl=el("text",{x:W/2,y:tY+174,"text-anchor":"middle",fill:"#7d8da6","font-size":11});rl.textContent="↺ recycle / rework — the track loops full circle";svg.appendChild(rl);}
  // Codex feeder engine onto the track at Open
  {const cx=bayX.open;
   const fb=el("path",{d:`M ${cx} 42 L ${cx} ${tY-rg-2}`,class:"beam"});fb.style.stroke="#ff9d5c";svg.appendChild(fb);
   svg.appendChild(el("circle",{cx:cx,cy:30,r:13,fill:"#0d1420",stroke:"#ff9d5c","stroke-width":2}));
   const ct=el("text",{x:cx,y:33,"text-anchor":"middle",fill:"#ff9d5c","font-size":8,"font-weight":700});ct.textContent="CODEX";svg.appendChild(ct);
   const cl=el("text",{x:cx,y:12,"text-anchor":"middle",fill:"#7d8da6","font-size":9});cl.textContent=(d.codex_feed||0)+" in";svg.appendChild(cl);}
  // stations + carriages (tasks) parked on the track
  COLS.forEach(c=>{
    const x=bayX[c],S=d.stages[c]||{count:0,tokens:[]};
    svg.appendChild(el("circle",{cx:x,cy:tY,r:6,fill:"#0d1420",stroke:"#5aa9ff","stroke-width":2}));
    const lb=el("text",{x:x,y:tY-24,"text-anchor":"middle",class:"baylabel"});lb.textContent=LABEL[c];svg.appendChild(lb);
    const cn=el("text",{x:x,y:tY-38,"text-anchor":"middle",fill:"#dce6f5","font-size":17,"font-weight":700});cn.textContent=S.count;svg.appendChild(cn);
    (S.tokens||[]).slice(0,6).forEach((t,i)=>svg.appendChild(carriage(x,tY+20+i*14,ACTORC[t.owner]||"#5aa9ff",t.id+" · "+t.title+(t.rework?` (rework ${t.rework})`:""))));
    if(S.count>6){const m=el("text",{x:x,y:tY+20+6*14+7,"text-anchor":"middle",fill:"#7d8da6","font-size":9});m.textContent="+"+(S.count-6)+" more";svg.appendChild(m);}
  });
  // Wren gate arch straddling the track
  {const wx=bayX.wren_gate;
   svg.appendChild(el("path",{class:"wgate",id:"wgate",fill:"none",stroke:"#8a5cf6","stroke-width":3,d:`M ${wx-17} ${tY-4} L ${wx-17} ${tY-20} Q ${wx} ${tY-34}, ${wx+17} ${tY-20} L ${wx+17} ${tY-4}`}));
   const wt=el("text",{x:wx,y:tY-42,"text-anchor":"middle",fill:"#8a5cf6","font-size":9,"font-weight":700});wt.textContent="WREN GATE";svg.appendChild(wt);}
  pulse(d);
}
function pulse(d){
  const tY=142;
  (d.pulses||[]).forEach(p=>{
    const key=p.ts+"|"+p.task+"|"+p.event;if(seen.has(key))return;seen.add(key);
    const tx=bayX[p.to];if(tx==null)return;
    const from=bayX[COLS[Math.max(0,COLS.indexOf(p.to)-1)]]||tx-90,col=ACTORC[p.actor]||"#5aa9ff";
    const g=carriage(from,tY-6,col,"");g.setAttribute("class","pulse");g.style.color=col;svg.appendChild(g);
    g.animate([{transform:"translateX(0)"},{transform:`translateX(${tx-from}px)`}],{duration:1150,easing:"cubic-bezier(.4,0,.2,1)"}).onfinish=()=>g.remove();
    if(p.actor==="wren"||p.to==="wren_gate"){const gt=document.getElementById("wgate");if(gt){gt.classList.remove("act");void gt.offsetWidth;gt.classList.add("act");}}
  });
  if(seen.size>3000)seen=new Set([...seen].slice(-1500));
}
async function tick(){
  let d;try{d=await(await fetch("/api/data")).json()}catch(e){return}
  if(window.__ver&&window.__ver!==d.ver){location.reload();return}window.__ver=d.ver;
  const k=d.kpis;kTotal.textContent=k.total;kOpen.textContent=k.open;kVerify.textContent=k.awaiting_verify;kBlocked.textContent=k.blocked;kDone.textContent=k.done;
  const a=d.autorunner,ae=document.getElementById("auto");
  ae.className="auto "+(a.stalled?"stall":"ok");
  ae.innerHTML=a.stalled?`⚠ <b>AUTONOMOUS VERIFY STALLED</b> — last tick <b>${esc(a.tick)}</b>: ${esc(a.reason)} <span class=pill>${esc((a.ts||'').slice(11,19))}</span> · gate enabled=${a.enabled}`
    :`✓ autorunner ${esc(a.tick||'')} · gate enabled=${a.enabled} <span class=pill>${esc((a.ts||'').slice(11,19))}</span>`;
  draw(d);
  document.getElementById("ticker").innerHTML=(d.ticker||[]).map((r,i)=>{
    const col=ACTORC[r.actor]||"#7d8da6";
    const vd=r.verdict?` <b style="color:${r.verdict==='approve'?'#39d98a':'#ff6b6b'}">${esc(r.verdict)}</b>`:"";
    return `<div class="tickrow${(!first&&i===0)?' new':''}"><span class=dim>${esc((r.ts||'').slice(11,19))}</span><span style="color:${col};font-weight:700">${esc(r.actor)}</span><span>${esc(r.event)}${vd}</span><span class=dim>${esc(r.task||'')} → ${esc(r.to)}</span></div>`;
  }).join("");
  document.getElementById("await").innerHTML=(d.awaiting||[]).map(t=>`<div class=av><b class=mono>${esc(t.id)}</b> ${esc(t.title)}<br><span class=pill>owner ${esc(t.owner||'—')} · sandbox ${esc(t.sandbox_by||'—')} · signoff ${esc(t.signoff_by||'—')} ${t.verdict?('· '+esc(t.verdict)):''}${t.rework?(' · rework '+t.rework):''}</span></div>`).join('')||'<span class=pill>none awaiting</span>';
  document.getElementById("actors").innerHTML=Object.entries(d.actors||{}).map(([a,n])=>`<span class=badge style="color:${ACTORC[a]||'#7d8da6'};border-color:${ACTORC[a]||'#233146'};margin:2px;display:inline-block">${esc(a)} ${n}</span>`).join('');
  const rc=r=>r>=8?'var(--ok)':r>=5?'var(--warn)':'var(--bad)';
  document.getElementById("signoff").innerHTML=(d.awaiting_signoff||[]).map(t=>`<div style="border:1px solid var(--line);border-radius:8px;padding:8px;margin-bottom:6px;font-size:12px"><b class=mono>${esc(t.id)}</b> ${esc(t.title)}<br><span class=pill>${esc(t.state)} · owner ${esc(t.owner||t.created_by||'—')} · rework ${t.rework} · rating <b style="color:${rc(t.rating)}">${t.rating}/10</b></span><div style="margin-top:5px"><button onclick="act('${esc(t.id)}','accept')" style="background:var(--ok);color:#04120d;border:0;border-radius:6px;padding:5px 12px;font-weight:700;cursor:pointer">✓ Accept</button> <button onclick="act('${esc(t.id)}','reject')" style="background:transparent;border:1px solid var(--bad);color:var(--bad);border-radius:6px;padding:5px 12px;cursor:pointer">✕ Reject</button></div></div>`).join('')||'<span class=pill>nothing awaiting your sign-off</span>';
  document.getElementById("wstats").innerHTML=(d.worker_stats||[]).map(w=>`<div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:12px"><span style="color:${ACTORC[w.actor]||'#7d8da6'};font-weight:700;width:96px">${esc(w.actor)}</span><div style="flex:1;height:8px;background:#0d1420;border-radius:6px;overflow:hidden"><div style="height:100%;width:${w.avg_rating*10}%;background:${rc(w.avg_rating)}"></div></div><span class=pill>${w.avg_rating}/10 · ${w.tasks} tasks · ${w.done} done · avg rework ${w.avg_rework}</span></div>`).join('')||'<span class=pill>—</span>';
  document.getElementById("wren").innerHTML=(d.wren_actions||[]).map(a=>`<div style="padding:3px 4px;border-bottom:1px solid var(--line);font-size:11px;display:flex;gap:8px"><span class=dim>${esc((a.ts||'').slice(11,19))}</span><span style="color:var(--wren);font-weight:700">${esc(a.label)}</span><span class=dim>${esc(a.task||'')}</span></div>`).join('')||'<span class=pill>no recent Wren actions in window</span>';
  first=false;
}
async function act(id,action){
  const note=action==='reject'?(prompt('Reject '+id+' — reason (optional):')||''):'';
  if(action==='reject'&&note===null)return;
  const r=await(await fetch('/api/act',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({task_id:id,action,note})})).json();
  if(r.ok){tick()}else{alert('failed: '+(r.error||'?'))}
}
tick();setInterval(tick,2000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/data") or self.path.startswith("/api/council"):
            b = json.dumps(build()).encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store, must-revalidate"); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            b = PAGE.encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store, must-revalidate"); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)

    def do_POST(self):
        if self.path.startswith("/api/act"):
            try:
                n = int(self.headers.get("Content-Length", 0) or 0)
                payload = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                payload = {}
            b = json.dumps(act(payload)).encode()
            self.send_response(200); self.send_header("Cache-Control", "no-store, must-revalidate"); self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
        else:
            self.send_response(404); self.end_headers()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(); ap.add_argument("--port", type=int, default=8864)
    a = ap.parse_args()
    print(f"council live flow dash on http://0.0.0.0:{a.port}")
    ThreadingHTTPServer(("0.0.0.0", a.port), H).serve_forever()
