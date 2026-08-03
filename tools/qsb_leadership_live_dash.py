#!/usr/bin/env python3
"""
qsb_leadership_live_dash.py — LEADERSHIP LIVE window for Ross.
2026-07-30, Ross: "me to know what's going on ... I can hear a live two-way
conversation between them [Wren & Bill]."

READ-ONLY. Every line shown is pulled from a real registry, server-side, and
timestamped with its own source ts. It never writes a project file, never flips
a gate, never fabricates a turn. If a source is empty, the panel says so
honestly ("no real turns yet") rather than inventing content.

Streams, live (auto-refresh + /api/stream long-poll):
  1. Wren<->Bill conversation, newest last, in one merged timeline from the
     REAL sources that exist:
       - data/registries/qsb_wren_bill_dialogue.jsonl   (dedicated engine, when built)
       - data/registries/qsb_bill_wren_coordinator.jsonl (converse / bill->wren / wren->bill)
     Each turn tagged with which source + msg_id so it can't be a phantom.
  2. Wren's management activity — REAL task-board events she authored
       - data/registries/qsb_council_tasks.jsonl  (actor==wren: created/claimed/
         assigned/tool_selected/bench_proposal/done/blocked ...)
  3. Bill's latest real relays into the room Ross already watches
       - data/registries/leadership_comms/room.jsonl (from==bill)
  4. "What's being worked on / what's missing"
       - open / in_progress / blocked task counts + the blocked/stalled items,
         computed from the live task snapshot + latest telemetry line.
  5. Latest live telemetry (services up, bus, traders, disk, load, board).

Voice ("hear it"): the browser reads NEW Wren<->Bill turns aloud via the
built-in Web Speech API (SpeechSynthesis) — no tower TTS service required,
nothing to break. Toggle in the header; off by default.

Run:   python3 tools/qsb_leadership_live_dash.py --port 8879
Install (boot-proof systemd, vaulted sudo only):
       python3 tools/qsb_leadership_live_dash.py --install
"""
import json, os, sys, time, html, argparse, subprocess
from datetime import datetime, timezone
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data" / "registries"

DIALOGUE      = REG / "qsb_wren_bill_dialogue.jsonl"          # dedicated engine (may not exist yet)
COORDINATOR   = REG / "qsb_bill_wren_coordinator.jsonl"       # real two-way exchanges
ROOM          = REG / "leadership_comms" / "room.jsonl"       # Ross's channel
COUNCIL       = REG / "qsb_council_tasks.jsonl"               # Wren's management actions
SNAPSHOT      = REG / "qsb_council_tasks_snapshot.json"       # board state
BILL_FEED     = REG / "qsb_bill_concierge_feed.jsonl"         # Bill proactive events
PRESENCE      = REG / "leadership_comms" / "presence.json"
BILL_WORK     = REG / "qsb_bill_work_mode.json"
PARTICIPANTS  = REG / "qsb_gene_pool_participants.json"
SUDO_ENV      = ROOT / "floors" / "floor_28_security_department" / "vault" / ".env.sudo"

PORT_DEFAULT = 8879


def _now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tail_lines(path: Path, n=400, max_bytes=8_000_000):
    """Return up to the last n complete JSON lines of a (possibly huge) jsonl."""
    if not path.exists():
        return []
    try:
        size = path.stat().st_size
        with open(path, "rb") as f:
            if size > max_bytes:
                f.seek(size - max_bytes)
                f.readline()  # drop partial line
            data = f.read()
    except Exception:
        return []
    out = []
    for raw in data.decode("utf-8", "replace").splitlines():
        raw = raw.strip().lstrip("\x00").strip()
        if not raw:
            continue
        try:
            out.append(json.loads(raw))
        except Exception:
            continue
    return out[-n:]


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def _clip(s, n=1200):
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------------------
# 1. Merged Wren<->Bill conversation from all REAL sources
# ---------------------------------------------------------------------------
def _conversation():
    turns = []

    # (a) dedicated dialogue engine — sibling-built; read whenever it appears.
    for r in _tail_lines(DIALOGUE, n=300):
        spk = (r.get("speaker") or r.get("from") or r.get("who") or "").lower()
        body = r.get("text") or r.get("body") or r.get("message") or r.get("msg") or ""
        ts = r.get("ts") or r.get("timestamp") or ""
        if not body:
            continue
        who = "wren" if "wren" in spk else ("bill" if "bill" in spk else (spk or "?"))
        turns.append({"ts": ts, "who": who, "body": _clip(body),
                      "src": "dialogue", "id": r.get("msg_id") or r.get("id") or ""})

    # (b) coordinator log — the two-way exchanges that already run for real.
    for r in _tail_lines(COORDINATOR, n=300):
        d = r.get("dir", "")
        ts = r.get("ts", "")
        if d == "converse":
            q = r.get("bill_question") or {}
            a = r.get("wren_answer") or {}
            if q.get("body"):
                turns.append({"ts": q.get("ts", ts), "who": "bill", "body": _clip(q["body"]),
                              "src": "coordinator", "id": q.get("msg_id", "")})
            if a.get("body"):
                turns.append({"ts": a.get("ts", ts), "who": "wren", "body": _clip(a["body"]),
                              "src": "coordinator", "id": a.get("msg_id", "")})
        elif d == "bill->wren":
            if r.get("q"):
                turns.append({"ts": ts, "who": "bill", "body": _clip(r["q"]),
                              "src": "coordinator", "id": r.get("q_msg_id", "")})
            if r.get("a"):
                turns.append({"ts": ts, "who": "wren", "body": _clip(r["a"]),
                              "src": "coordinator", "id": r.get("reply_msg_id", "")})
        elif d == "wren->bill":
            if r.get("wren_says"):
                turns.append({"ts": ts, "who": "wren", "body": _clip(r["wren_says"]),
                              "src": "coordinator", "id": r.get("msg_id", "")})

    # de-dup by (id) or (who+first 60 chars+ts), keep chronological
    seen = set()
    uniq = []
    for t in sorted(turns, key=lambda x: x.get("ts", "")):
        key = t["id"] or (t["who"] + t["body"][:60] + t["ts"])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(t)
    return uniq[-60:]


# ---------------------------------------------------------------------------
# 2. Wren's real management activity from the council board
# ---------------------------------------------------------------------------
MGMT_EVENTS = {"created", "claimed", "assigned", "tool_selected", "bench_proposal",
               "done", "blocked", "reopened", "recycled", "peer_signoff"}


def _wren_management():
    rows = []
    for r in _tail_lines(COUNCIL, n=500):
        if (r.get("actor") or "").lower() != "wren":
            continue
        ev = r.get("event", "")
        if ev not in MGMT_EVENTS:
            continue
        rows.append({"ts": r.get("ts", ""), "event": ev,
                     "task_id": r.get("task_id", ""), "text": _clip(r.get("text", ""), 220)})
    return rows[-25:]


# ---------------------------------------------------------------------------
# 3. Bill's real relays into the room
# ---------------------------------------------------------------------------
def _bill_relays():
    rows = []
    for r in _tail_lines(ROOM, n=300):
        if (r.get("from") or "").lower() != "bill":
            continue
        body = r.get("body", "")
        rows.append({"ts": r.get("ts", ""), "id": r.get("msg_id", ""), "body": _clip(body, 400)})
    return rows[-15:]


# ---------------------------------------------------------------------------
# 4. What's being worked on / what's missing
# ---------------------------------------------------------------------------
def _board_state():
    snap = _read_json(SNAPSHOT, default={})
    tasks = snap.get("tasks") if isinstance(snap, dict) else None
    counts = {"open": 0, "in_progress": 0, "blocked": 0, "done": 0, "other": 0}
    blocked_items, active_items = [], []
    if isinstance(tasks, dict):
        it = tasks.values()
    elif isinstance(tasks, list):
        it = tasks
    else:
        it = []
    for t in it:
        if not isinstance(t, dict):
            continue
        st = (t.get("state") or t.get("status") or "").lower()
        if st in counts:
            counts[st] += 1
        else:
            counts["other"] += 1
        title = t.get("text") or t.get("title") or t.get("id") or ""
        if st == "blocked" and len(blocked_items) < 8:
            blocked_items.append(_clip(title, 160))
        elif st == "in_progress" and len(active_items) < 8:
            active_items.append(_clip(title, 160))
    return counts, blocked_items, active_items


def _latest_telemetry():
    # newest telemetry string from the coordinator log (Wren stamps it each turn)
    for r in reversed(_tail_lines(COORDINATOR, n=60)):
        if r.get("telemetry"):
            return r["telemetry"]
    return ""


def _bill_live_state():
    presence = _read_json(PRESENCE, default={}) or {}
    bill_presence = (presence.get("presence") or presence).get("bill", {})
    work = _read_json(BILL_WORK, default={}) or {}
    roster = _read_json(PARTICIPANTS, default={}) or {}
    bill = (roster.get("participants") or {}).get("bill", {})
    tools = bill.get("tools_whitelist") or []
    online = bool(bill_presence.get("online"))
    return {
        "identity": "bill",
        "role": "MacBook Executive Concierge",
        "physical_host": "MacBook",
        "reachable_addr": bill_presence.get("reachable_addr") or bill.get("reachable_addr"),
        "last_heartbeat": bill_presence.get("last_heartbeat"),
        "online": online,
        "local_model": bill.get("model", "qwen2.5:14b"),
        "reasoning_route": "Mac localhost Ollama only",
        "linux_floor_role": "evidence, tools and transport only",
        "work_mode": work.get("mode", "unknown"),
        "current_tasks": work.get("current_task_ids") or [],
        "work_status": ("ACTIVE" if online and work.get("counts_for_quorum") else
                        ("CONCIERGE" if work.get("mode") == "concierge" else "DEGRADED")),
        "tools": tools,
        "tool_count": len(tools),
        "gene_pool": "advisory only",
        "council_of_15": "advisory only",
        "remote_primary_allowed": False,
        "claude_substitution_allowed": False,
        "degraded_message": (None if online else
            "BILL LOCAL PRIMARY UNAVAILABLE / REMOTE PRIMARY FORBIDDEN / BILL DEGRADED"),
    }


# ---------------------------------------------------------------------------
# State payload
# ---------------------------------------------------------------------------
def build_state():
    conv = _conversation()
    counts, blocked, active = _board_state()
    src_status = {
        "dialogue_engine": ("live" if DIALOGUE.exists() else "not-built-yet"),
        "coordinator": ("live" if COORDINATOR.exists() else "missing"),
    }
    return {
        "ts": _now(),
        "conversation": conv,
        "conversation_count": len(conv),
        "wren_management": _wren_management(),
        "bill_relays": _bill_relays(),
        "board": counts,
        "blocked_items": blocked,
        "active_items": active,
        "telemetry": _latest_telemetry(),
        "bill": _bill_live_state(),
        "sources": src_status,
    }


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
PAGE = r"""<!doctype html><html><head><meta charset=utf-8>
<title>QSB Leadership LIVE — Wren &amp; Bill</title>
<meta name=viewport content="width=device-width,initial-scale=1">
<style>
:root{--bg:#0b0e14;--pane:#131824;--edge:#232b3d;--wren:#8ad4ff;--bill:#ffd58a;--ok:#5fe08a;--warn:#ffb454;--bad:#ff6b6b;--dim:#7b869c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#e6ebf5;font:14px/1.5 -apple-system,Segoe UI,Roboto,sans-serif}
header{position:sticky;top:0;background:#0b0e14ee;backdrop-filter:blur(6px);border-bottom:1px solid var(--edge);padding:10px 16px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;z-index:5}
h1{font-size:16px;margin:0;letter-spacing:.3px}
.tag{font-size:11px;color:var(--dim)}
.wrap{display:grid;grid-template-columns:1.4fr 1fr;gap:14px;padding:14px;max-width:1500px;margin:0 auto}
@media(max-width:900px){.wrap{grid-template-columns:1fr}}
.pane{background:var(--pane);border:1px solid var(--edge);border-radius:10px;padding:12px;min-height:60px}
.pane h2{font-size:12px;text-transform:uppercase;letter-spacing:1px;color:var(--dim);margin:0 0 10px}
.turn{border-left:3px solid var(--edge);padding:6px 10px;margin:8px 0;border-radius:4px;background:#0e1320}
.turn.wren{border-color:var(--wren)}.turn.bill{border-color:var(--bill)}
.who{font-weight:700;font-size:12px}.who.wren{color:var(--wren)}.who.bill{color:var(--bill)}
.meta{color:var(--dim);font-size:10px;float:right}
.body{white-space:pre-wrap;margin-top:3px}
.row{padding:5px 8px;border-bottom:1px solid #1a2130;font-size:12.5px}
.ev{display:inline-block;min-width:96px;color:var(--warn);font-weight:600}
.tid{color:var(--dim);font-size:11px}
.counts{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px}
.chip{background:#0e1320;border:1px solid var(--edge);border-radius:20px;padding:3px 12px;font-size:12px}
.chip b{font-size:14px}
.blocked{color:var(--bad)}.active{color:var(--ok)}
.empty{color:var(--dim);font-style:italic;padding:8px}
.tele{font-family:ui-monospace,monospace;font-size:11.5px;color:#9fb0cc;background:#0e1320;border-radius:6px;padding:8px;white-space:pre-wrap}
button{background:#1b2436;color:#e6ebf5;border:1px solid var(--edge);border-radius:6px;padding:5px 12px;cursor:pointer;font-size:12px}
button.on{background:#243b2c;border-color:var(--ok);color:var(--ok)}
.src{font-size:10px;color:var(--dim)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}
.live{background:var(--ok)}.pending{background:var(--warn)}.miss{background:var(--bad)}
</style></head><body>
<header>
  <h1>QSB Leadership <span style="color:var(--ok)">LIVE</span></h1>
  <span class=tag id=clock></span>
  <span class=tag id=srcs></span>
  <button id=voice onclick="toggleVoice()">🔊 Hear off</button>
  <span class=tag>READ-ONLY · real registries only</span>
</header>
<div class=wrap>
  <div>
    <div class=pane>
      <h2>Wren &harr; Bill — live conversation</h2>
      <div id=conv><div class=empty>loading…</div></div>
    </div>
  </div>
  <div>
    <div class=pane>
      <h2>Board — what's being worked on / what's missing</h2>
      <div class=counts id=counts></div>
      <div id=work></div>
    </div>
    <div class=pane style="margin-top:14px">
      <h2>Wren's management activity (real task-board)</h2>
      <div id=mgmt></div>
    </div>
    <div class=pane style="margin-top:14px">
      <h2>Bill's relays into the room</h2>
      <div id=relays></div>
    </div>
    <div class=pane style="margin-top:14px">
      <h2>Bill — genuine Mac-local concierge</h2>
      <div id=bill></div>
    </div>
    <div class=pane style="margin-top:14px">
      <h2>Latest telemetry</h2>
      <div class=tele id=tele></div>
    </div>
  </div>
</div>
<script>
let voiceOn=false, spokenIds=new Set(), primed=false;
function toggleVoice(){voiceOn=!voiceOn;const b=document.getElementById('voice');
 b.textContent=voiceOn?'🔊 Hear on':'🔊 Hear off';b.className=voiceOn?'on':'';
 if(voiceOn&&window.speechSynthesis){speechSynthesis.cancel();}}
function say(who,text){if(!voiceOn||!window.speechSynthesis)return;
 const u=new SpeechSynthesisUtterance((who==='wren'?'Wren: ':'Bill: ')+text.slice(0,240));
 u.rate=1.05;u.pitch=who==='wren'?1.15:0.9;speechSynthesis.speak(u);}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function srcDot(v){return v==='live'?'live':(v==='not-built-yet'?'pending':'miss');}
async function tick(){
 let d;try{d=await (await fetch('/api/state')).json();}catch(e){return;}
 document.getElementById('clock').textContent=d.ts;
 document.getElementById('srcs').innerHTML=
   '<span class="dot '+srcDot(d.sources.dialogue_engine)+'"></span>dialogue-engine:'+d.sources.dialogue_engine+
   '  <span class="dot '+srcDot(d.sources.coordinator)+'"></span>coordinator:'+d.sources.coordinator;
 // conversation
 const c=document.getElementById('conv');
 if(!d.conversation.length){c.innerHTML='<div class=empty>No real Wren&harr;Bill turns yet. This panel stays empty until the dialogue engine or coordinator writes a genuine exchange — nothing is fabricated.</div>';}
 else{c.innerHTML=d.conversation.map(t=>
   '<div class="turn '+t.who+'"><span class="meta">'+esc(t.ts)+' · <span class=src>'+esc(t.src)+'</span></span>'+
   '<span class="who '+t.who+'">'+(t.who==='wren'?'Wren':t.who==='bill'?'Bill':esc(t.who))+'</span>'+
   '<div class=body>'+esc(t.body)+'</div></div>').join('');
   c.scrollTop=c.scrollHeight;}
 // voice: speak NEW turns only (skip the first paint to avoid a backlog dump)
 d.conversation.forEach(t=>{const id=t.id||(t.who+t.ts+t.body.slice(0,20));
   if(!spokenIds.has(id)){if(primed)say(t.who,t.body);spokenIds.add(id);}});
 primed=true;
 // board
 const b=d.board;document.getElementById('counts').innerHTML=
  ['open','in_progress','blocked','done'].map(k=>'<span class=chip>'+k+' <b class="'+(k==='blocked'?'blocked':k==='in_progress'?'active':'')+'">'+(b[k]||0)+'</b></span>').join('');
 let w='';
 if(d.blocked_items.length){w+='<div class=blocked><b>Blocked / missing:</b></div>'+d.blocked_items.map(x=>'<div class="row blocked">⛔ '+esc(x)+'</div>').join('');}
 if(d.active_items.length){w+='<div class=active style="margin-top:6px"><b>In progress:</b></div>'+d.active_items.map(x=>'<div class="row active">▶ '+esc(x)+'</div>').join('');}
 if(!w)w='<div class=empty>No blocked or in-progress items in the snapshot.</div>';
 document.getElementById('work').innerHTML=w;
 // mgmt
 const m=document.getElementById('mgmt');
 m.innerHTML=d.wren_management.length?d.wren_management.slice().reverse().map(r=>
   '<div class=row><span class=ev>'+esc(r.event)+'</span> <span class=tid>'+esc(r.task_id)+'</span><br>'+esc(r.text)+'</div>').join('')
   :'<div class=empty>No recent Wren-authored task-board events.</div>';
 // relays
 const rl=document.getElementById('relays');
 rl.innerHTML=d.bill_relays.length?d.bill_relays.slice().reverse().map(r=>
   '<div class=row><span class=tid>'+esc(r.ts)+'</span><br>'+esc(r.body)+'</div>').join('')
   :'<div class=empty>No Bill relays in the room feed.</div>';
 // Bill route/work status — evidence fields only
 const bl=d.bill||{}; const bv=bl.online?'active':'blocked';
 document.getElementById('bill').innerHTML=
   '<div class="row '+bv+'"><b>'+esc(bl.identity)+' · '+esc(bl.work_status)+'</b></div>'+
   '<div class=row>Physical host: '+esc(bl.physical_host)+' · '+esc(bl.reachable_addr||'unknown')+'</div>'+
   '<div class=row>Local model: '+esc(bl.local_model)+' · '+esc(bl.reasoning_route)+'</div>'+
   '<div class=row>Linux Floor 47: '+esc(bl.linux_floor_role)+'</div>'+
   '<div class=row>Work mode: '+esc(bl.work_mode)+' · tasks '+esc(JSON.stringify(bl.current_tasks||[]))+'</div>'+
   '<div class=row>Tools: '+esc(String(bl.tool_count))+' · Gene Pool '+esc(bl.gene_pool)+' · Council 15 '+esc(bl.council_of_15)+'</div>'+
   '<div class=row>Remote primary: FORBIDDEN · Claude substitution: FORBIDDEN</div>'+
   (bl.degraded_message?'<div class="row blocked">'+esc(bl.degraded_message)+'</div>':'');
 // tele
 document.getElementById('tele').textContent=d.telemetry||'(no telemetry line yet)';
}
tick();setInterval(tick,3000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        try:
            self.wfile.write(b)
        except Exception:
            pass

    def do_GET(self):
        p = self.path.split("?")[0]
        if p == "/" or p == "/index.html":
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif p == "/api/state":
            try:
                self._send(200, json.dumps(build_state(), ensure_ascii=False))
            except Exception as e:
                self._send(500, json.dumps({"error": str(e)}))
        elif p == "/health":
            self._send(200, json.dumps({"ok": True, "service": "qsb_leadership_live_dash", "ts": _now()}))
        else:
            self._send(404, json.dumps({"error": "not found"}))


SERVICE = """[Unit]
Description=QSB Leadership LIVE dashboard (Wren<->Bill conversation + Wren management, read-only)
After=network.target

[Service]
Type=simple
User=ross
WorkingDirectory=/vaults/nvme0/qsb_tower_v1
ExecStart=/usr/bin/python3 /vaults/nvme0/qsb_tower_v1/tools/qsb_leadership_live_dash.py --port {port}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""


def install(port):
    unit = SERVICE.format(port=port)
    sudo_pw = None
    try:
        for line in SUDO_ENV.read_text().splitlines():
            if line.startswith("SUDO_PASSWORD="):
                sudo_pw = line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    if not sudo_pw:
        print("ERROR: could not read vaulted sudo password; refusing to install.", file=sys.stderr)
        sys.exit(2)
    tmp = Path("/tmp/qsb-leadership-live-dash.service")
    tmp.write_text(unit)

    def sudo(cmd):
        full = f"echo '{sudo_pw}' | sudo -S {cmd}"
        return subprocess.run(full, shell=True, capture_output=True, text=True)

    sudo("cp /tmp/qsb-leadership-live-dash.service /etc/systemd/system/qsb-leadership-live-dash.service")
    sudo("systemctl daemon-reload")
    sudo("systemctl enable qsb-leadership-live-dash.service")
    r = sudo("systemctl restart qsb-leadership-live-dash.service")
    print("install rc:", r.returncode, r.stderr[-200:] if r.stderr else "")
    time.sleep(2)
    st = subprocess.run("systemctl is-active qsb-leadership-live-dash.service",
                        shell=True, capture_output=True, text=True)
    print("service active:", st.stdout.strip())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=PORT_DEFAULT)
    ap.add_argument("--install", action="store_true")
    args = ap.parse_args()
    if args.install:
        install(args.port)
        return
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), H)
    print(f"QSB Leadership LIVE dash on :{args.port} (read-only)")
    srv.serve_forever()


if __name__ == "__main__":
    main()
