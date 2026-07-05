#!/usr/bin/env python3
"""qsb_boardroom_hub.py — Council of Six communications hub.

Ross 2026-07-02: "I THINK WE NEED A COMMUNICATIONS HUB FOR THE BOARDROOM ?"
+ "YES".

Single boardroom surface at port 8852 that unifies every Council channel
into one timeline + one compose bar.

READS from:
  data/registries/qsb_claude_wren_bridge.jsonl   (Claude<->Wren helix)
  data/registries/qsb_wren_dash_chat.jsonl       (Ross<->Wren via dash)
  data/team_memory/shared/node_inbox/*.json      (TP + Wren-pulse + all node msgs)
  data/registries/qsb_f47_team_records.jsonl     (subset: team_msg/coord kinds)

WRITES to (via compose bar routing):
  target=tp       -> POST http://192.168.1.74:9100/msg
  target=wren     -> append qsb_claude_wren_bridge.jsonl
  target=hermes   -> append qsb_hermes_bridge.jsonl + F47 stamp
  target=iquest   -> F47 stamp (iQuest polled from stamps on his side)
  target=hq       -> append data/team_memory/shared/node_inbox/... (self-note)
  target=all      -> ALL of the above + F47 announce stamp

VOICE (reuses qsb_voice_server on :8795):
  POST /api/tts   {text, member} -> audio/wav
  POST /api/stt   audio/webm bytes -> {text}

REAL-MONEY GATES: page never touches gates. Nothing routes to broker paths.
"""
from __future__ import annotations
import argparse, json, os, subprocess, socket, time
import urllib.request, urllib.error
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
INBOX = ROOT / "data/team_memory/shared/node_inbox"
BRIDGE_CW = REG / "qsb_claude_wren_bridge.jsonl"
BRIDGE_HERMES = REG / "qsb_hermes_bridge.jsonl"
WREN_DASH_CHAT = REG / "qsb_wren_dash_chat.jsonl"
BOARDROOM_LOG = REG / "qsb_boardroom_hub_activity.jsonl"
F47 = REG / "qsb_f47_team_records.jsonl"

TP_URL = "http://192.168.1.74:9100"
VOICE = "http://127.0.0.1:8795"
WREN_AGENT = ROOT / "tools/qsb_wren_local_agent.py"

# Palette per member (Ross's color scheme choices)
MEMBERS = {
    # ── PRIMARY COUNCIL (executive tier) ──
    "ross":     {"label": "Ross",     "hue": 45,  "color": "#eab308", "role": "Owner · Chairman"},
    "claude":   {"label": "Claude",   "hue": 30,  "color": "#cd7f45", "role": "HQ · F47"},
    "helm":     {"label": "Helm",     "hue": 45,  "color": "#eab308", "role": "Ross-facing brain"},
    "auger":    {"label": "Auger",    "hue": 155, "color": "#4ade80", "role": "Wren-facing sage"},
    # ── LOCAL WORKERS (Ollama agents on this box) ──
    "wren":     {"label": "Wren",     "hue": 20,  "color": "#f97316", "role": "Builder · F46 · resident"},
    "hermes":   {"label": "Hermes",   "hue": 265, "color": "#b58bff", "role": "Watcher · F169"},
    "forge":    {"label": "Forge",    "hue": 300, "color": "#e879f9", "role": "Code drafter · Wren-team"},
    "sage":     {"label": "Sage",     "hue": 155, "color": "#a78bfa", "role": "Session auditor"},
    "pip":      {"label": "Pip",      "hue": 195, "color": "#22d3ee", "role": "Wren's assistant"},
    "mira":     {"label": "Mira",     "hue": 280, "color": "#a78bfa", "role": "Reviewer · 2nd opinion"},
    # ── EXTERNAL / REMOTE ──
    "iris":     {"label": "Iris",     "hue": 350, "color": "#f472b6", "role": "Galaxy phone AI"},
    "receptionist": {"label": "Receptionist", "hue": 190, "color": "#38bdf8", "role": "F0 · Telegram bot"},
    "iquest":   {"label": "iQuest",   "hue": 50,  "color": "#ffcc55", "role": "Coder (rare-invoke)"},
    "tp":       {"label": "ThinkPad", "hue": 200, "color": "#66d9c9", "role": "TP-Claude · CEO node"},
    "thinkpad": {"label": "ThinkPad", "hue": 200, "color": "#66d9c9", "role": "TP-Claude · CEO node"},
    "acer":     {"label": "Acer",     "hue": 5,   "color": "#ef4444", "role": "Windows node"},
    # ── ALIASES ──
    "hq":       {"label": "HQ",       "hue": 30,  "color": "#cd7f45", "role": "HQ · F47"},
    "system":   {"label": "System",   "hue": 220, "color": "#7d8ba9", "role": "system"},
    "unknown":  {"label": "?",        "hue": 0,   "color": "#666",    "role": ""},
}


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _norm(m: dict, source: str) -> dict:
    """Normalize a message from any source into a common shape."""
    ts = (m.get("ts") or m.get("timestamp") or m.get("received_at") or m.get("ts_start") or "")
    fr = (m.get("from") or m.get("by") or m.get("role") or m.get("operator") or "").lower()
    to = (m.get("to") or "").lower()
    text = (m.get("text") or m.get("body") or m.get("content") or m.get("subject") or "")
    kind = m.get("kind") or m.get("event_kind") or ""
    subject = m.get("subject") or ""
    # normalize channels' unusual "from" values
    if fr in ("hq-claude", "hqclaude"): fr = "claude"
    if fr in ("thinkpad", "tp"):        fr = "thinkpad"
    return {
        "ts": ts,
        "from": fr or "unknown",
        "to": to or "all",
        "kind": kind,
        "subject": subject[:180],
        "text": (text or "")[:2000],
        "source": source,
    }


def read_bridge_cw(n=200) -> list:
    if not BRIDGE_CW.exists(): return []
    try:
        lines = BRIDGE_CW.read_text(errors="ignore").splitlines()
    except Exception:
        return []
    out = []
    for l in lines[-n:]:
        try:
            d = json.loads(l)
        except Exception:
            continue
        out.append(_norm(d, "bridge_cw"))
    return out


def read_bridge_hermes(n=200) -> list:
    if not BRIDGE_HERMES.exists(): return []
    try:
        lines = BRIDGE_HERMES.read_text(errors="ignore").splitlines()
    except Exception:
        return []
    out = []
    for l in lines[-n:]:
        try:
            d = json.loads(l)
        except Exception:
            continue
        out.append(_norm(d, "bridge_hermes"))
    return out


def read_wren_dash_chat(n=200) -> list:
    if not WREN_DASH_CHAT.exists(): return []
    try:
        lines = WREN_DASH_CHAT.read_text(errors="ignore").splitlines()
    except Exception:
        return []
    out = []
    for l in lines[-n:]:
        try:
            d = json.loads(l)
        except Exception:
            continue
        out.append(_norm(d, "wren_dash"))
    return out


def read_node_inbox(n=200) -> list:
    if not INBOX.exists(): return []
    out = []
    try:
        files = sorted(INBOX.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    except Exception:
        return []
    for p in files:
        try:
            d = json.loads(p.read_text())
        except Exception:
            continue
        out.append(_norm(d, "node_inbox"))
    return out


def read_boardroom_log(n=200) -> list:
    if not BOARDROOM_LOG.exists(): return []
    try:
        lines = BOARDROOM_LOG.read_text(errors="ignore").splitlines()
    except Exception:
        return []
    out = []
    for l in lines[-n:]:
        try:
            d = json.loads(l)
        except Exception:
            continue
        out.append(_norm(d, "boardroom_hub"))
    return out


def unified_timeline(limit=150) -> list:
    all_msgs = []
    all_msgs += read_bridge_cw(200)
    all_msgs += read_bridge_hermes(200)
    all_msgs += read_wren_dash_chat(200)
    all_msgs += read_node_inbox(200)
    all_msgs += read_boardroom_log(200)
    # 2026-07-03 tighter dedup — Ross flagged Wren appearing twice.
    # Wren posts to boardroom /api/post get fanned out to claude_wren_bridge,
    # hermes_bridge, node_inbox — same content, sometimes with ts drifted by
    # microseconds. Dedupe by (from, text[:60]) within a 10-second window.
    dedup = []
    seen_bucket = {}  # (from, text_slug) -> list of (parsed_ts_epoch, index)
    import re
    from datetime import datetime as _dt
    def _epoch(ts: str) -> float:
        try: return _dt.fromisoformat(ts.replace("Z","+00:00")).timestamp()
        except Exception: return 0.0
    for m in all_msgs:
        who = m.get("from","?")
        text = (m.get("text","") or "").strip()[:60].lower()
        text = re.sub(r"\s+", " ", text)
        key = (who, text)
        e = _epoch(m.get("ts",""))
        prior = seen_bucket.get(key, [])
        # if any prior within 10s, this is a fan-out duplicate — skip
        if any(abs(e - pe) < 10 for pe, _ in prior):
            continue
        seen_bucket.setdefault(key, []).append((e, len(dedup)))
        dedup.append(m)
    dedup.sort(key=lambda x: x.get("ts",""), reverse=True)
    return dedup[:limit]


def counts_by_speaker(msgs: list) -> dict:
    out = {}
    for m in msgs:
        f = m["from"]
        out[f] = out.get(f, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))


def tp_probe() -> dict:
    try:
        r = urllib.request.urlopen(f"{TP_URL}/status", timeout=2)
        return {"reachable": True, "ts": json.loads(r.read().decode()).get("ts", "")}
    except Exception as e:
        return {"reachable": False, "error": str(e)[:60]}


AGENDA_FILE = REG / "qsb_boardroom_agenda.json"
REACTIONS_FILE = REG / "qsb_boardroom_reactions.jsonl"
COMMENTARY_FILE = REG / "qsb_boardroom_commentary.jsonl"
COMMENTARY_STATE = REG / "qsb_boardroom_commentary_state.json"


def read_agenda() -> dict:
    if not AGENDA_FILE.exists():
        return {"topic": "", "set_by": "", "set_at": ""}
    try:
        return json.loads(AGENDA_FILE.read_text())
    except Exception:
        return {"topic": "", "set_by": "", "set_at": ""}


def write_agenda(topic: str, set_by: str):
    AGENDA_FILE.parent.mkdir(parents=True, exist_ok=True)
    AGENDA_FILE.write_text(json.dumps({
        "topic": topic[:280], "set_by": set_by, "set_at": utc_iso()
    }, indent=2))


def reactions_by_msg() -> dict:
    """Return {msg_key: {emoji: [voter, voter, ...]}}."""
    if not REACTIONS_FILE.exists():
        return {}
    out = {}
    try:
        for line in REACTIONS_FILE.read_text(errors="ignore").splitlines():
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            k = r.get("msg_key")
            e = r.get("emoji")
            v = r.get("voter") or "?"
            if not k or not e:
                continue
            if k not in out:
                out[k] = {}
            if e not in out[k]:
                out[k][e] = []
            if v not in out[k][e]:
                out[k][e].append(v)
    except Exception:
        pass
    return out


def presence(msgs: list) -> dict:
    """Compute per-member last-seen (from timeline msgs). Returns
    { member_id: {"last_seen_s": int_or_None, "state": "online|idle|offline"} }."""
    now = time.time()
    out = {}
    for m in msgs:
        fr = m.get("from")
        ts = m.get("ts", "")
        try:
            age = int(now - datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp())
        except Exception:
            continue
        if fr not in out or age < out[fr]["last_seen_s"]:
            out[fr] = {"last_seen_s": age}
    for k, v in out.items():
        s = v["last_seen_s"]
        v["state"] = "online" if s < 60 else "idle" if s < 300 else "offline"
    return out


def _wren_mind_snapshot() -> dict:
    """2026-07-03: Wren has a persistent mind at qsb_wren_mind.json. Surface a
    compact view on the boardroom hub so Ross can WATCH her mind grow live.
    Ross verbatim: 'this is why we need the boardroom hub dash working correctley'."""
    mind_path = ROOT / "data/registries/qsb_wren_mind.json"
    if not mind_path.exists():
        return {"exists": False}
    try:
        m = json.loads(mind_path.read_text())
        # recompute age-since-birth
        try:
            from datetime import datetime, timezone
            born = datetime.fromisoformat(m.get("born_at","2026-06-14T00:00:00Z").replace("Z","+00:00"))
            age_d = max(0, (datetime.now(timezone.utc) - born).days)
        except Exception:
            age_d = m.get("current_age_d", 0)
        return {
            "exists": True,
            "born_at": m.get("born_at"),
            "age_days": age_d,
            "counts": {
                "thoughts": len(m.get("recent_thoughts", [])),
                "moods": len(m.get("mood_history", [])),
                "unresolved": len(m.get("unresolved", [])),
                "growth_milestones": sum(1 for g in m.get("growth_notes", []) if g.get("milestone")),
            },
            "current_mood": (m.get("mood_history") or [{}])[-1] if m.get("mood_history") else None,
            "last_thoughts": m.get("recent_thoughts", [])[-6:][::-1],
            "unresolved": m.get("unresolved", [])[-5:],
            "recent_growth": m.get("growth_notes", [])[-3:][::-1],
        }
    except Exception as e:
        return {"exists": False, "err": str(e)[:120]}


def _wren_evolution_snapshot() -> dict:
    """2026-07-03: surface always-working loop stats on the hub."""
    gate_path = ROOT / "data/registries/qsb_wren_evolution_gate.json"
    cycles_path = ROOT / "data/registries/qsb_wren_evolution_cycles.jsonl"
    out = {"enabled": None, "cycles_today": 0, "recent": []}
    try:
        if gate_path.exists():
            g = json.loads(gate_path.read_text())
            out["enabled"] = bool(g.get("enabled", True))
    except Exception: pass
    try:
        if cycles_path.exists():
            lines = cycles_path.read_text(errors="ignore").splitlines()
            from datetime import datetime, timezone
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            out["cycles_today"] = sum(1 for l in lines if today in l)
            recent = []
            for l in lines[-5:][::-1]:
                try:
                    d = json.loads(l)
                    recent.append({
                        "ts": d.get("ts",""),
                        "cycle": d.get("cycle"),
                        "kind": d.get("job_kind"),
                        "wall_s": d.get("wall_s"),
                        "head": (d.get("final_head","") or "")[:120],
                    })
                except Exception: pass
            out["recent"] = recent
    except Exception: pass
    return out


def build_status():
    msgs = unified_timeline(120)
    pres = presence(msgs)
    # Rule-based live commentator (Ross picked option 1) — diff + emit
    try:
        diff_and_emit_commentary(msgs, pres)
    except Exception:
        pass
    return {
        "ts": utc_iso(),
        "members": MEMBERS,
        "timeline": msgs,
        "counts": counts_by_speaker(msgs),
        "presence": pres,
        "agenda": read_agenda(),
        "reactions": reactions_by_msg(),
        "commentary": commentary_tail(20),
        "channels": {
            "bridge_cw": BRIDGE_CW.exists(),
            "bridge_hermes": BRIDGE_HERMES.exists(),
            "wren_dash_chat": WREN_DASH_CHAT.exists(),
            "node_inbox": INBOX.exists(),
            "boardroom_log": BOARDROOM_LOG.exists(),
        },
        "tp": tp_probe(),
        "wren_mind": _wren_mind_snapshot(),
        "wren_evolution": _wren_evolution_snapshot(),
        "platforms": _platforms(),
        # 2026-07-03 Ross "improve boardroom massively... individuals thinking as one mind":
        "council_moods": _council_moods_snapshot(msgs),
        "meeting_timer": _meeting_idle_timer(msgs),
        "bug_watch": _bug_watch_snapshot(),
        "sandbox_playground": _sandbox_playground(),
        "training_scoreboard": _training_scoreboard(),
        "avatar_competition": _avatar_competition(),
        "event_stream": _event_stream(),
        "chain_progress": _chain_progress(),
        "tp_feed": _tp_feed_probe(),
        "network": _nighthawk_probe(),
    }


def _real_talk_data() -> dict:
    """Ross 2026-07-05 #145: read live commentary UNIFORMLY from qsb_town_square.jsonl
    where all CEOs post — heartbeats, replies, notes, alerts. Every CEO visible."""
    from datetime import datetime as _dt, timezone as _tz
    def utc(): return _dt.now(_tz.utc).isoformat().replace("+00:00","Z")

    WHO_MAP = {
        "hq_claude":"hq", "hq":"hq",
        "wren":"wren",
        "tp_pip":"tp", "TP-Pip":"tp", "tp":"tp",
        "acer_cass":"acer", "Acer-Cass":"acer", "acer":"acer",
        "council_watcher":"watcher",
        "ross":"ross",
    }

    wren_msgs, hq_msgs, tp_msgs, acer_msgs = [], [], [], []
    ts_p = REG / "qsb_town_square.jsonl"
    if ts_p.exists():
        for line in ts_p.read_text(errors="ignore").splitlines()[-400:]:
            try:
                r = json.loads(line)
                fr = (r.get("from","") or "").strip()
                who = WHO_MAP.get(fr, fr.lower())
                text = (r.get("text","") or "")[:400]
                ts = r.get("ts","")
                kind = r.get("src","town_square")
                if who == "hq": hq_msgs.append({"ts":ts,"who":"hq","text":text,"kind":kind})
                elif who == "wren": wren_msgs.append({"ts":ts,"who":"wren","text":text,"kind":kind})
                elif who == "tp": tp_msgs.append({"ts":ts,"who":"tp","text":text,"kind":kind})
                elif who == "acer": acer_msgs.append({"ts":ts,"who":"acer","text":text,"kind":kind})
            except Exception: pass
    hq_msgs = hq_msgs[-6:]
    wren_msgs = wren_msgs[-6:]
    tp_msgs = tp_msgs[-6:]
    acer_msgs = acer_msgs[-6:]

    # merge + sort
    all_msgs = wren_msgs + hq_msgs + tp_msgs + acer_msgs
    all_msgs.sort(key=lambda m: m.get("ts",""), reverse=True)
    return {
        "count": len(all_msgs),
        "messages": all_msgs[:30],
        "sources": {
            "wren": {"count": len(wren_msgs), "source": "qsb_wren_mind.json"},
            "hq":   {"count": len(hq_msgs),   "source": "boardroom commentary + F47"},
            "tp":   {"count": len(tp_msgs),   "source": "192.168.1.74:9100/state + node_inbox"},
            "acer": {"count": len(acer_msgs), "source": "192.168.1.78:9000/message (REAL Acer)"},
        },
        "note": "This is REAL 4-way channel. TP's own /conversation was 100% llama3.1:8b simulating all 4 voices — no real messages landed there.",
    }


TALK_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>REAL TALK · Council of 4</title>
<style>
  :root { --bg:#05070c; --edge:#1b2536; --dim:#8296b0;
          --tp:#22d3ee; --acer:#f59e0b; --wren:#a78bfa; --hq:#eab308; }
  * { box-sizing: border-box; }
  body { margin:0; background: radial-gradient(1000px 500px at 60% -10%, #0f1a2e, #05070c 60%);
         color:#e7eef7; font-family:-apple-system, Inter, "Segoe UI", sans-serif; min-height:100vh; }
  header { display:flex; align-items:center; gap:16px; padding:14px 24px; border-bottom:1px solid var(--edge); }
  h1 { margin:0; font-size:18px; letter-spacing:3px; font-weight:500; }
  .badge { padding:3px 10px; border:1px solid var(--hq); border-radius:99px; font-size:10px; letter-spacing:2px; color: var(--hq); }
  main { padding: 20px 24px; }
  .note { color: var(--dim); font-size: 11px; margin-bottom: 20px; max-width: 900px; line-height: 1.5; }
  .msg { padding: 10px 14px; margin: 8px 0; border-radius: 8px; background: rgba(255,255,255,0.03); border-left: 3px solid; }
  .msg.hq   { border-color: var(--hq);   }
  .msg.wren { border-color: var(--wren); }
  .msg.tp   { border-color: var(--tp);   }
  .msg.acer { border-color: var(--acer); }
  .msg-head { display:flex; align-items:baseline; gap:10px; margin-bottom:5px; font-size:11px; }
  .who { font-weight:600; letter-spacing:2px; text-transform: uppercase; }
  .who.hq   { color: var(--hq);   }
  .who.wren { color: var(--wren); }
  .who.tp   { color: var(--tp);   }
  .who.acer { color: var(--acer); }
  .kind { color: var(--dim); font-family: ui-monospace, monospace; font-size: 9.5px; padding: 1px 6px; border: 1px solid var(--edge); border-radius: 8px; }
  .ts   { color: var(--dim); margin-left: auto; font-family: ui-monospace, monospace; font-size: 10px; }
  .text { color: #e7eef7; font-size: 12.5px; line-height: 1.55; }
  .sources { display:grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; font-size: 10.5px; }
  .src { padding: 8px 12px; border-radius: 6px; background: rgba(255,255,255,0.02); border-left: 3px solid; }
</style></head><body>
<header>
  <h1>REAL TALK · <span style="color:var(--hq);">Council of 4</span></h1>
  <span class="badge">HQ · 192.168.1.4</span>
  <span id="ts" style="margin-left:auto; color: var(--dim); font-family: ui-monospace, monospace; font-size:10.5px;">—</span>
  <a href="/" style="color: var(--dim); text-decoration:none; font-size:11px; letter-spacing:2px;">← boardroom</a>
</header>
<main>
  <div class="note" id="note">—</div>
  <div class="sources" id="sources"></div>
  <div id="feed">—</div>
</main>
<script>
async function tick() {
  try {
    const d = await (await fetch('/talk/data')).json();
    document.getElementById('ts').textContent = new Date().toLocaleTimeString();
    document.getElementById('note').textContent = d.note || '';
    // sources chip row
    const srcRow = document.getElementById('sources');
    if (srcRow) {
      const colors = {hq:'#eab308', wren:'#a78bfa', tp:'#22d3ee', acer:'#f59e0b'};
      srcRow.innerHTML = Object.entries(d.sources||{}).map(([k, v]) => {
        return `<div class="src" style="border-left-color:${colors[k]||'#94a3b8'};">
          <div style="color:${colors[k]};font-weight:600;letter-spacing:2px;">${k.toUpperCase()} · ${v.count} msgs</div>
          <div style="color:var(--dim);font-size:9.5px;margin-top:3px;">${v.source||''}</div>
        </div>`;
      }).join('');
    }
    // feed
    const feed = document.getElementById('feed');
    if (!d.messages || !d.messages.length) {
      feed.innerHTML = '<div style="color: var(--dim); text-align:center; padding: 40px;">no messages yet</div>';
      return;
    }
    feed.innerHTML = d.messages.map(m => {
      const who = (m.who||'').toLowerCase();
      const ts = (m.ts||'').slice(11, 19);
      return `<div class="msg ${who}">
        <div class="msg-head">
          <span class="who ${who}">${who}</span>
          <span class="kind">${m.kind||''}</span>
          <span class="ts">${ts}</span>
        </div>
        <div class="text">${(m.text||'').replace(/</g, '&lt;')}</div>
      </div>`;
    }).join('');
  } catch (e) {
    document.getElementById('ts').textContent = 'err: ' + e.message;
  }
}
tick();
setInterval(tick, 3000);
</script>
</body></html>
"""


def _nighthawk_probe() -> dict:
    """2026-07-04 Ross: 'we going to always use it so use it well · we can add some
    info to the boardroom hub'. Poll the Netgear Nighthawk M1 model.json for signal,
    clients, uptime, temp. Auth: admin/admin (vault-noted)."""
    import base64
    try:
        req = urllib.request.Request(
            "http://192.168.1.1/api/model.json",
            method="GET",
            headers={"Authorization": "Basic " + base64.b64encode(b"admin:admin").decode()},
        )
        r = urllib.request.urlopen(req, timeout=2)
        d = json.loads(r.read().decode())
    except Exception as e:
        return {"err": str(e)[:120]}

    g = d.get("general", {})
    w = d.get("wwan", {})
    sim = d.get("sim", {})
    router = d.get("router", {}) if isinstance(d.get("router"), dict) else {}
    clients = router.get("clients", []) if isinstance(router, dict) else []
    signal = w.get("signalStrength", {}) if isinstance(w.get("signalStrength"), dict) else {}
    return {
        "device_name":    g.get("deviceName"),
        "firmware":       f"v{g.get('verMajor')}.{g.get('verMinor')}",
        "uptime_s":       g.get("upTime"),
        "temp_c":         g.get("devTemperature"),
        "connection":     w.get("connection"),
        "network_type":   w.get("registerNetworkDisplay") or w.get("registerNetwork"),
        "rssi":           signal.get("rssi"),
        "rsrp":           signal.get("rsrp"),
        "sinr":           signal.get("sinr"),
        "sim_status":     sim.get("status"),
        "sms_unread":     (d.get("sms") or {}).get("unreadMsgs"),
        "client_count":   len(clients),
        "clients":        [{"ip": c.get("ip"), "name": c.get("name"),
                            "mac": c.get("mac"), "type": c.get("connectionType")}
                           for c in clients[:12]],
    }


def _tp_feed_probe() -> dict:
    """Proxy TP's live /feed telemetry (venue_pnl + fleet + PnL)."""
    try:
        req = urllib.request.Request("http://192.168.1.74:9100/feed", method="GET")
        r = urllib.request.urlopen(req, timeout=2)
        d = json.loads(r.read().decode())
        return {
            "venue_pnl": d.get("venue_pnl", {}),
            "session_pnl_gbp": d.get("session_pnl_gbp", 0),
            "session_closes": d.get("session_closes", 0),
            "pot_committed_gbp": d.get("pot_committed_gbp", 0),
            "cap_gbp": d.get("cap_gbp", 0),
            "open_positions": d.get("open_positions", 0),
        }
    except Exception:
        return {}


def _event_stream() -> list:
    """2026-07-03 Ross 'add more features' — a narrative event stream showing
    recent tower events in chronological order. Aggregates cycles + bridges +
    inbox + bug catches."""
    events = []
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)

    # Wren cycles
    cyc = REG / "qsb_wren_evolution_cycles.jsonl"
    if cyc.exists():
        for l in cyc.read_text(errors="ignore").splitlines()[-8:]:
            try:
                d = json.loads(l)
                events.append({
                    "ts": d.get("ts",""),
                    "who": "wren",
                    "kind": "cycle",
                    "text": f"cycle {d.get('cycle','?')} · {d.get('job_kind','?')} · {d.get('wall_s','?')}s",
                })
            except Exception: pass

    # TP inbox files
    if INBOX.exists():
        for p in sorted(INBOX.iterdir())[-20:]:
            try:
                d = json.loads(p.read_text())
                ts = d.get("ts", d.get("received_at",""))
                if not ts: continue
                who = d.get("from","?").lower()
                events.append({
                    "ts": ts,
                    "who": who,
                    "kind": "inbox",
                    "text": (d.get("subject") or d.get("text","") or d.get("body",""))[:80],
                })
            except Exception: pass

    # Bug catches
    bc = REG / "qsb_wren_bug_catches.jsonl"
    if bc.exists():
        for l in bc.read_text(errors="ignore").splitlines()[-4:]:
            try:
                d = json.loads(l)
                events.append({
                    "ts": d.get("ts",""),
                    "who": "wren",
                    "kind": "bug",
                    "text": f"caught {d.get('severity','?')} bug: {(d.get('file','') or '')[:40]}",
                })
            except Exception: pass

    # Boardroom commentary (recent non-system)
    cf = REG / "qsb_boardroom_commentary.jsonl"
    if cf.exists():
        for l in cf.read_text(errors="ignore").splitlines()[-10:]:
            try:
                d = json.loads(l)
                if d.get("who","system") in ("system","commentator"): continue
                events.append({
                    "ts": d.get("ts",""),
                    "who": d.get("who","?"),
                    "kind": "chat",
                    "text": (d.get("text","") or "")[:120],
                })
            except Exception: pass

    # sort desc, cap 15
    events.sort(key=lambda e: e.get("ts",""), reverse=True)
    return events[:15]


def _chain_progress() -> dict:
    """Wren's chain orchestrator — active + recent chains + stage-level progress."""
    cf = REG / "qsb_wren_chains.jsonl"
    if not cf.exists(): return {"chains": []}
    out = []
    for l in cf.read_text(errors="ignore").splitlines():
        try:
            c = json.loads(l)
            stages = c.get("stages", [])
            done = sum(1 for s in stages if s.get("done"))
            active_stage_kind = "?"
            if c.get("status") == "running" or c.get("current_stage",0) < len(stages):
                idx = min(c.get("current_stage",0), len(stages)-1)
                if idx < len(stages):
                    active_stage_kind = stages[idx].get("kind","?")
            out.append({
                "id": c.get("id",""),
                "title": (c.get("title","") or "")[:60],
                "status": c.get("status","?"),
                "done": done,
                "total": len(stages),
                "active_kind": active_stage_kind,
                "final_verdict": (c.get("final_verdict","") or "")[:120],
            })
        except Exception: continue
    out.sort(key=lambda c: (c.get("status") != "running", c.get("id","")), reverse=True)
    return {"chains": out[:8]}


def _council_snapshot() -> dict:
    """Council of Four live view — HQ-Claude, Wren, TP-Pip, Acer-Cass.
    Each member's current state + latest thought + mood + observations.
    """
    out = {"ts": utc_iso(), "members": []}

    # HQ-Claude
    try:
        latest_hq = ""
        # Ross 2026-07-04 "town square of five" — Ross IS a founding CEO,
        # not the operator watching. Add his card first.
        latest_ross = ""
        try:
            ts_file = REG / "qsb_town_square.jsonl"
            if ts_file.exists():
                for line in reversed(ts_file.read_text().splitlines()[-60:]):
                    try:
                        d = json.loads(line)
                        if (d.get("from") or d.get("who") or "").lower() == "ross":
                            latest_ross = (d.get("text") or "").strip()[:200]
                            if latest_ross: break
                    except Exception: pass
        except Exception: pass
        out["members"].append({
            "name": "Ross", "role": "Founding CEO · Owner · Sole Judge",
            "theme": "Chairman", "color": "#3b82f6",
            "brain": "human", "status": "live",
            "latest_thought": latest_ross or "(watching council)",
        })

        p = REG / "qsb_f47_team_records.jsonl"
        if p.exists():
            for line in reversed(p.read_text().splitlines()[-30:]):
                try:
                    d = json.loads(line)
                    if (d.get("who") or "").lower() == "hq_claude":
                        latest_hq = (d.get("summary") or d.get("text") or "")[:200]
                        break
                except Exception:
                    pass
        # Ross 2026-07-04: "you have to do better than say corordanating wtf"
        # Prefer town-square latest (real reasoning) over F47 stamps.
        # Fallback to F47 stamp. Fallback to self-prompt tail. Never "coordinating".
        if not latest_hq:
            try:
                ts = REG / "qsb_town_square.jsonl"
                if ts.exists():
                    for line in reversed(ts.read_text().splitlines()[-40:]):
                        try:
                            d = json.loads(line)
                            if (d.get("from") or d.get("who") or "").lower() == "hq_claude":
                                t = (d.get("text") or "").strip()
                                if t and not t.startswith(("hq_claude said:", "Corrected", "Heard")):
                                    latest_hq = t[:200]; break
                        except Exception: pass
            except Exception: pass
        if not latest_hq:
            try:
                sp = REG / "qsb_hq_self_prompts.jsonl"
                if sp.exists():
                    for line in reversed(sp.read_text().splitlines()[-10:]):
                        try:
                            d = json.loads(line)
                            q = d.get("question","")
                            n = d.get("next_move","")
                            if q or n:
                                latest_hq = f"{q} → {n}"[:200]; break
                        except Exception: pass
            except Exception: pass
        out["members"].append({
            "name": "HQ-Claude", "role": "Coordinator, Floor 47",
            "theme": "The Beacon Hall", "color": "#eab308",
            "brain": "Claude Opus 4.7", "status": "live",
            "latest_thought": latest_hq or "self-prompt daemon watching town-square + task-board + F47 (event-driven)",
        })
    except Exception as e:
        out["members"].append({"name":"HQ-Claude","status":"err","detail":str(e)[:100]})

    # Wren
    try:
        mind_path = REG / "qsb_wren_mind.json"
        m = json.loads(mind_path.read_text()) if mind_path.exists() else {}
        latest = ""
        rt = m.get("recent_thoughts") or []
        if rt: latest = (rt[-1].get("text") or "")[:200]
        out["members"].append({
            "name": "Wren", "role": "Builder-engineer, Floor 46",
            "theme": "Wren Bench", "color": "#a78bfa",
            "brain": m.get("brain") or "qwen3.5:9b",
            "status": "live" if latest else "quiet",
            "cycle_count": m.get("cycle_count", 0),
            "mood": m.get("mood", "?"),
            "latest_thought": latest or "(no recent thought)",
        })
    except Exception as e:
        out["members"].append({"name":"Wren","status":"err","detail":str(e)[:100]})

    # TP-Pip
    for peer in [("TP-Pip", "http://192.168.1.74:9110/state", "Command Cathedral", "#22d3ee", "ThinkPad, T500 GPU"),
                 ("Acer-Cass", "http://192.168.1.78:9000/state", "Data Foundry", "#f59e0b", "Acer laptop, CPU-only")]:
        name, url, theme, color, hw = peer
        try:
            req = urllib.request.Request(url, headers={"User-Agent":"boardroom-council"})
            # Ross 2026-07-04: TP kept flashing red-unreachable; his /state is fast
            # (~12ms) but when he's mid-LLM inference the fetch can queue behind it.
            # Bumped from 2s → 8s to cover that.
            r = urllib.request.urlopen(url=req, timeout=8)
            d = json.loads(r.read().decode())
            out["members"].append({
                "name": name, "role": f"CEO of {hw}",
                "theme": theme, "color": color,
                "brain": d.get("brain","?"), "status": "live",
                "uptime_s": d.get("uptime_s", 0),
                "cycle_count": d.get("cycle_count", 0),
                "mood": d.get("mood", "?"),
                "tool_calls": d.get("tool_call_count", 0),
                "obs_from_hq": d.get("observed_hq_count", 0),
                "latest_thought": (d.get("latest_thought") or "(idle)")[:200],
                "dash_url": url.replace("/state", "/"),
            })
        except Exception as e:
            out["members"].append({
                "name": name, "role": f"CEO of {hw}",
                "theme": theme, "color": color,
                "status": "unreachable", "detail": str(e)[:80],
            })
    return out


COUNCIL_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Council of Four — Live + Competition</title>
<style>
*{box-sizing:border-box}
body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:20px}
h1{margin:0 0 6px;color:#eab308}
.sub{color:#94a3b8;margin-bottom:14px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;max-width:1300px;margin:auto}
.card{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:14px;position:relative;overflow:hidden}
.card::before{content:"";position:absolute;top:0;left:0;right:0;height:3px;background:var(--c,#94a3b8)}
.name{font-size:1.3em;font-weight:700;margin:0;color:var(--c,#e8ecf3)}
.role{font-size:12px;color:#94a3b8;margin-bottom:8px}
.theme{display:inline-block;background:var(--c,#374151);color:#000;font-size:11px;padding:2px 8px;border-radius:10px;margin-bottom:8px}
.stats{display:flex;gap:10px;margin:8px 0;flex-wrap:wrap;font-size:11px}
.stat{background:#1f2937;padding:3px 8px;border-radius:6px;color:#94a3b8}
.stat b{color:#e8ecf3}
.thought{background:#0b0d12;border-left:2px solid var(--c,#94a3b8);padding:8px;margin-top:8px;font-size:12.5px;color:#cbd5e1;border-radius:0 6px 6px 0}
.status{position:absolute;top:12px;right:14px;font-size:10px;padding:2px 8px;border-radius:10px;font-weight:700}
.status.live{background:#10b981;color:#000}
.status.quiet{background:#64748b;color:#fff}
.status.unreachable{background:#ef4444;color:#fff}
a.dash-link{color:#22d3ee;text-decoration:none;font-size:11px;display:block;margin-top:6px}
a.dash-link:hover{text-decoration:underline}
</style></head><body>
<h1>🏛️ Council of Five</h1>
<div class=sub>Live view — Ross · HQ-Claude · Wren · TP-Pip · Acer-Cass · 5 minds locked · auto-refresh 1s</div>

<!-- Ross 2026-07-05 #149: production-grade live 4-CEO panel with animations -->
<style>
@keyframes ceo-pulse{0%,100%{transform:scale(1);box-shadow:0 0 0 0 currentColor}50%{transform:scale(1.05);box-shadow:0 0 24px 4px currentColor}}
@keyframes brain-flame{0%{stroke-dashoffset:0}100%{stroke-dashoffset:-40}}
@keyframes count-flash{0%{color:currentColor}50%{color:#e8ecf3;text-shadow:0 0 10px currentColor}100%{color:currentColor}}
@keyframes heart-ring{0%,100%{box-shadow:inset 0 0 0 1px transparent}50%{box-shadow:inset 0 0 0 3px rgba(255,255,255,0.25)}}
.ceo-tile{position:relative;padding:16px;background:#0e1420;border:1px solid #22334a;border-radius:12px;overflow:hidden}
.ceo-tile.active{animation:heart-ring 2s ease-in-out infinite}
.ceo-avatar{width:56px;height:56px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:900;font-size:22px;color:#000;position:relative}
.ceo-avatar.live{animation:ceo-pulse 1.6s ease-in-out infinite}
.ceo-strip-num{font-variant-numeric:tabular-nums;font-family:ui-monospace,monospace}
.ceo-strip-num.flash{animation:count-flash 0.8s ease-out}
.provider-live-dot{width:8px;height:8px;border-radius:50%;display:inline-block}
.provider-live-dot.hot{animation:ceo-pulse 1.2s ease-in-out infinite}
</style>
<div id="production-council-panel" style="margin-bottom:18px;padding:18px;background:#0e1420;border:1px solid #22334a;border-radius:12px;">
  <h2 style="margin:0 0 12px;color:#22d3ee;font-size:1.25em;">👥 LIVE 4-CEO COUNCIL · production grade</h2>
  <div id="council-tiles" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px;"></div>
</div>
<div id="commentary-live" style="margin-bottom:18px;padding:16px;background:#0e1420;border:1px solid #22334a;border-radius:12px;">
  <h2 style="margin:0 0 10px;color:#eab308;font-size:1.15em;">💬 LIVE COMMENTARY · all 4 CEOs</h2>
  <div id="commentary-body" style="max-height:280px;overflow-y:auto;font-size:12px;line-height:1.55;font-family:ui-monospace,monospace">loading…</div>
</div>
<div id="brain-strip-council" style="margin-bottom:18px;padding:16px;background:#0e1420;border:1px solid #22334a;border-radius:12px;">
  <h2 style="margin:0 0 10px;color:#ec4899;font-size:1.15em;">🧠 BRAIN ROUTER · all 6 external workers</h2>
  <div id="brain-strip-body" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px"></div>
</div>
<script>
const CEO_META = {
  hq_claude:{name:'HQ-Claude', color:'#eab308', initial:'H', role:'Founding Ops'},
  wren:{name:'Wren', color:'#a78bfa', initial:'W', role:'Design + Copy'},
  tp_pip:{name:'TP-Pip', color:'#22d3ee', initial:'T', role:'Data + Verify'},
  acer_cass:{name:'Acer-Cass', color:'#f59e0b', initial:'A', role:'Windows + System'},
};
const PROVIDERS_ORDER = ['groq','gemini','cohere','deepseek','openai','kimi'];
const PROVIDER_COLOR = {groq:'#f97316',gemini:'#3b82f6',cohere:'#ec4899',deepseek:'#8b5cf6',openai:'#10b981',kimi:'#f43f5e'};
const PROVIDER_ICON = {groq:'⚡',gemini:'💎',cohere:'🌸',deepseek:'🔮',openai:'🟢',kimi:'🌙'};

async function tickCouncilProd(){
  try{
    const [tk, br, tk_ceos] = await Promise.all([
      fetch('/tasks/data',{cache:'no-store'}).then(r=>r.json()),
      fetch('/brain/usage',{cache:'no-store'}).then(r=>r.json()),
      fetch('/talk/data',{cache:'no-store'}).then(r=>r.json()),
    ]);
    // 1. CEO tiles
    const tiles = document.getElementById('council-tiles');
    if(tiles){
      const tasksByOwner = {};
      (tk.tasks||[]).forEach(t => {
        const o = (t.owner||t.assignee||'').toLowerCase();
        if(!o) return;
        if(!tasksByOwner[o]) tasksByOwner[o] = {claimed:0, done:0, awaiting:0};
        if(['claimed','in_progress','acknowledged','assigned'].includes(t.state)) tasksByOwner[o].claimed++;
        else if(t.state === 'done') tasksByOwner[o].done++;
        else if(t.state === 'awaiting_peer_signoff') tasksByOwner[o].awaiting++;
      });
      // recent posts per CEO
      const nowMs = Date.now();
      const recentByCeo = {};
      (tk_ceos.messages||[]).forEach(m => {
        const who = m.who || '';
        if(!recentByCeo[who]) recentByCeo[who] = {last_ts:'', text:''};
        if(!recentByCeo[who].last_ts || (m.ts||'') > recentByCeo[who].last_ts){
          recentByCeo[who].last_ts = m.ts || '';
          recentByCeo[who].text = (m.text || '').slice(0, 100);
        }
      });
      // brain usage per CEO
      const brainByCaller = {};
      Object.entries(br.callers||{}).forEach(([nm, cd]) => {
        const norm = nm.toLowerCase().replace(/-/g,'_');
        for(const key of Object.keys(CEO_META)){
          if(norm.includes(key) || key.includes(norm)) { brainByCaller[key] = (brainByCaller[key]||0) + (cd.total||0); }
        }
      });
      tiles.innerHTML = Object.entries(CEO_META).map(([id,m]) => {
        const t = tasksByOwner[id] || {claimed:0, done:0, awaiting:0};
        const talk = recentByCeo[id === 'hq_claude' ? 'hq' : id === 'tp_pip' ? 'tp' : id === 'acer_cass' ? 'acer' : id];
        const lastAgeMin = talk && talk.last_ts ? Math.floor((nowMs - new Date(talk.last_ts).getTime())/60000) : 999;
        const active = lastAgeMin < 3;
        const brainCalls = brainByCaller[id] || 0;
        return `<div class="ceo-tile ${active?'active':''}" style="color:${m.color}">
          <div style="display:flex;gap:12px;align-items:center;margin-bottom:10px">
            <div class="ceo-avatar ${active?'live':''}" style="background:${m.color}">${m.initial}</div>
            <div>
              <div style="font-size:15px;font-weight:800;color:${m.color}">${m.name}</div>
              <div style="font-size:10.5px;color:#94a3b8">${m.role}</div>
            </div>
          </div>
          <div style="display:flex;gap:10px;flex-wrap:wrap;font-size:10.5px;margin-bottom:8px">
            <span style="background:#0b1220;padding:2px 7px;border-radius:6px">🔥 <b class="ceo-strip-num" style="color:${m.color}">${t.claimed}</b>/3</span>
            <span style="background:#0b1220;padding:2px 7px;border-radius:6px">✓ <b class="ceo-strip-num" style="color:#10b981">${t.done}</b></span>
            <span style="background:#0b1220;padding:2px 7px;border-radius:6px">⏳ <b class="ceo-strip-num" style="color:#eab308">${t.awaiting}</b></span>
            <span style="background:#0b1220;padding:2px 7px;border-radius:6px">🧠 <b class="ceo-strip-num" style="color:#ec4899">${brainCalls}</b> ext</span>
          </div>
          <div style="font-size:10.5px;color:#94a3b8">last: ${talk && talk.text ? '<i>"'+talk.text.replace(/</g,'&lt;')+'"</i> · '+(lastAgeMin<1?'<1m':lastAgeMin+'m')+' ago' : 'silent'}</div>
        </div>`;
      }).join('');
    }
    // 2. Commentary body
    const cel = document.getElementById('commentary-body');
    if(cel){
      const WHO_LABELS = {hq:'HQ-Claude', wren:'Wren', tp:'TP-Pip', acer:'Acer-Cass', ross:'Ross', watcher:'Council Watcher'};
      const WHO_COLORS = {hq:'#eab308', wren:'#a78bfa', tp:'#22d3ee', acer:'#f59e0b', ross:'#e8ecf3', watcher:'#ef4444'};
      cel.innerHTML = (tk_ceos.messages||[]).slice(0, 40).map(m => {
        const nm = WHO_LABELS[m.who] || m.who;
        const c = WHO_COLORS[m.who] || '#94a3b8';
        return `<div style="padding:3px 0;border-bottom:1px solid #1e293b">
          <span style="color:#64748b">${(m.ts||'').slice(11,19)}</span>
          <b style="color:${c};margin:0 6px">${nm}:</b>
          <span style="color:#cbd5e1">${(m.text||'').slice(0,220).replace(/</g,'&lt;')}</span>
        </div>`;
      }).join('') || '<div style="color:#64748b">loading…</div>';
    }
    // 3. Brain router strip
    const bel = document.getElementById('brain-strip-body');
    if(bel){
      const providers = br.providers || {};
      bel.innerHTML = PROVIDERS_ORDER.map(p => {
        const s = providers[p] || {total:0, last_5m:0, cost_sum:0};
        const c = PROVIDER_COLOR[p];
        const active = (s.last_5m||0) > 0;
        return `<div style="padding:10px;background:#0b1220;border-left:3px solid ${c};border-radius:6px">
          <div style="display:flex;align-items:center;gap:6px">
            <span class="provider-live-dot ${active?'hot':''}" style="background:${c};color:${c}"></span>
            <b style="color:${c};font-size:12px">${PROVIDER_ICON[p]} ${p}</b>
          </div>
          <div style="margin-top:4px;font-size:10.5px;color:#94a3b8;font-family:ui-monospace,monospace">
            <b style="color:#e8ecf3">${s.last_5m||0}</b>/5m · <b>${s.total||0}</b> total · $${(s.cost_sum||0).toFixed(4)}
          </div>
        </div>`;
      }).join('');
    }
  }catch(e){console.error('tickCouncilProd',e)}
}
tickCouncilProd(); setInterval(tickCouncilProd, 1000);
</script>

<div class=grid id=grid></div>

<!-- ═══ TOWN SQUARE OF FIVE — 5 minds share ONE feed ═══ -->
<div style="margin-top:24px;padding:16px;background:#111827;border:1px solid #1f2937;border-radius:10px;">
  <h2 style="margin:0 0 6px;color:#22d3ee;font-size:1.2em;">🗣️ Town Square of Five · shared feed · every CEO reads this</h2>
  <div style="color:#94a3b8;margin-bottom:10px;font-size:12px;">Every message from Ross + every CEO lands here. Ross is a founding CEO, not an operator watching. 5 minds make one.</div>
  <div id=ts-feed style="max-height:420px;overflow-y:auto;font-size:12px;line-height:1.5;padding:8px;background:#0b0d12;border-radius:6px;">loading…</div>
</div>

<!-- ═══ DRIFT TICKER — anything that changes ═══ -->
<div style="margin-top:16px;padding:16px;background:#111827;border:1px solid #1f2937;border-radius:10px;">
  <h2 style="margin:0 0 6px;color:#eab308;font-size:1.2em;">📈 Live Drift · everything moving</h2>
  <div style="color:#94a3b8;margin-bottom:10px;font-size:12px;">Every state change surfaces here: chat / task / stamp. Ross sees the pulse.</div>
  <div id=drift-feed style="max-height:300px;overflow-y:auto;font-size:11.5px;line-height:1.4;padding:8px;background:#0b0d12;border-radius:6px;">loading…</div>
</div>

<!-- ═══ LINK HEALTH — auto-reconnect + auto-task on break ═══ -->
<div style="margin-top:16px;padding:16px;background:#111827;border:1px solid #1f2937;border-radius:10px;">
  <h2 style="margin:0 0 6px;color:#a855f7;font-size:1.2em;">🔗 Link Health · self-heal or task-out</h2>
  <div style="color:#94a3b8;margin-bottom:10px;font-size:12px;">Ross rule: any broken link auto-reconnects, else creates a task.</div>
  <div id=link-health style="font-size:12px;padding:8px;background:#0b0d12;border-radius:6px;">loading…</div>
</div>

<!-- ═══ COUNCIL AVATAR COMPETITION ═══ -->
<div style="margin-top:32px;padding:20px;background:#111827;border:1px solid #1f2937;border-radius:12px;">
  <h2 style="margin:0 0 6px;color:#eab308;font-size:1.4em;">🏆 Council Avatar Competition</h2>
  <div style="color:#94a3b8;margin-bottom:18px;font-size:13px;">Each Council CEO picks a theme + color that represents their room on the shared boardroom. Themes registered 2026-07-03. Ross is the final judge.</div>

  <!-- Rules -->
  <div style="background:#0b0d12;border-left:4px solid #eab308;padding:14px;border-radius:0 8px 8px 0;margin-bottom:20px;">
    <h3 style="margin:0 0 10px;color:#eab308;font-size:1em;text-transform:uppercase;letter-spacing:.06em;">📜 RULES</h3>
    <ol style="margin:0 0 0 20px;padding:0;color:#cbd5e1;font-size:13px;line-height:1.7;">
      <li>Every Council CEO enters ONE avatar theme representing their identity + workspace</li>
      <li>Each theme has: <b>name</b> · <b>color</b> · <b>voice</b> · optional humanoid SVG</li>
      <li>Theme must render live on member's own dashboard (not just written on paper)</li>
      <li>Rendering must include an interactive animated element (pulse / rotation / glow)</li>
      <li>Persistence: theme entry persists across sessions (mind file / config)</li>
      <li>Peer-visible: every other CEO can see the entry on shared /council view</li>
      <li><b>ROSS is the final judge</b> — he decides the winner based on originality, coherence with the member's role, and quality of live rendering</li>
      <li>No changing your entry after Ross calls final judgment (locked in)</li>
      <li>Losing entries stay on the board as reference — no shame, they're all part of the tower</li>
    </ol>
  </div>

  <!-- Entries -->
  <h3 style="margin:0 0 12px;color:#e8ecf3;font-size:1em;text-transform:uppercase;letter-spacing:.06em;">🎨 THE ENTRIES</h3>
  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:14px;">
    <div style="background:#0b0d12;border-top:4px solid #eab308;border-radius:8px;padding:14px;">
      <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;">HQ-CLAUDE (F47)</div>
      <div style="font-size:1.15em;font-weight:700;color:#eab308;margin:4px 0;">THE BEACON HALL</div>
      <div style="font-size:12px;color:#cbd5e1;">molten gold <b>#eab308</b> · voice M1</div>
      <div style="font-size:11.5px;color:#94a3b8;margin-top:6px;line-height:1.4;">Humanoid SVG entry rendered in NOW·LIVE·STATE tile on HQ dash. Represents coordinator role.</div>
    </div>
    <div style="background:#0b0d12;border-top:4px solid #a78bfa;border-radius:8px;padding:14px;">
      <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;">WREN (F46)</div>
      <div style="font-size:1.15em;font-weight:700;color:#a78bfa;margin:4px 0;">WREN BENCH</div>
      <div style="font-size:12px;color:#cbd5e1;">violet <b>#a78bfa</b> · voice F3</div>
      <div style="font-size:11.5px;color:#94a3b8;margin-top:6px;line-height:1.4;">Builder-engineer's workbench aesthetic. Live on port 8851. Represents her fit-out + design work.</div>
    </div>
    <div style="background:#0b0d12;border-top:4px solid #22d3ee;border-radius:8px;padding:14px;">
      <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;">TP-PIP (ThinkPad)</div>
      <div style="font-size:1.15em;font-weight:700;color:#22d3ee;margin:4px 0;">COMMAND CATHEDRAL</div>
      <div style="font-size:12px;color:#cbd5e1;">cyan <b>#22d3ee</b> · voice M1</div>
      <div style="font-size:11.5px;color:#94a3b8;margin-top:6px;line-height:1.4;">Central command aesthetic for the orchestrator role. Live on his laptop at :9110.</div>
    </div>
    <div style="background:#0b0d12;border-top:4px solid #f59e0b;border-radius:8px;padding:14px;">
      <div style="font-size:11px;color:#94a3b8;text-transform:uppercase;letter-spacing:.1em;">ACER-CASS (Acer)</div>
      <div style="font-size:1.15em;font-weight:700;color:#f59e0b;margin:4px 0;">DATA FOUNDRY</div>
      <div style="font-size:12px;color:#cbd5e1;">amber <b>#f59e0b</b> · voice M4</div>
      <div style="font-size:11.5px;color:#94a3b8;margin-top:6px;line-height:1.4;">Windows-side node's own dashboard yesterday — chat_http.py on :9000, LAN scanner + animated node map + vitals.</div>
    </div>
  </div>

  <!-- Status -->
  <div style="margin-top:18px;padding:12px;background:#0b0d12;border:1px dashed #374151;border-radius:8px;">
    <div style="color:#94a3b8;font-size:11.5px;text-transform:uppercase;letter-spacing:.1em;margin-bottom:6px;">STATUS</div>
    <div style="color:#cbd5e1;font-size:13px;">
      <span style="color:#eab308;">●</span> All 4 entries registered · themes locked in <code style="background:#111827;padding:1px 6px;border-radius:4px;color:#eab308;">data/registries/qsb_avatar_competition.json</code><br>
      <span style="color:#f59e0b;">●</span> Awaiting Ross's final judgment — winner decides tower banner + boardroom accent
    </div>
  </div>
</div>
<script>
async function tick(){
  try{
    const d = await (await fetch('/council/data')).json();
    const grid = document.getElementById('grid');
    grid.innerHTML = d.members.map(m => `
      <div class=card style="--c:${m.color||'#94a3b8'}">
        <span class="status ${m.status||'quiet'}">${m.status||'?'}</span>
        <h2 class=name>${m.name}</h2>
        <div class=role>${m.role||''}</div>
        <div class=theme>${m.theme||''}</div>
        <div class=stats>
          <span class=stat>brain <b>${m.brain||'?'}</b></span>
          ${m.mood?`<span class=stat>mood <b>${m.mood}</b></span>`:''}
          ${m.cycle_count!==undefined?`<span class=stat>cycles <b>${m.cycle_count}</b></span>`:''}
          ${m.uptime_s?`<span class=stat>up <b>${Math.floor(m.uptime_s/60)}m</b></span>`:''}
          ${m.tool_calls!==undefined?`<span class=stat>tools <b>${m.tool_calls}</b></span>`:''}
        </div>
        <div class=thought>${(m.latest_thought||m.detail||'').replace(/</g,'&lt;')}</div>
        ${m.dash_url?`<a class=dash-link href="${m.dash_url}" target=_blank>→ open ${m.name} dashboard</a>`:''}
      </div>`).join('');
  }catch(e){document.getElementById('grid').innerHTML='<div style=color:#ef4444>err '+e+'</div>'}
}
// TOWN SQUARE — every CEO's messages in one panel · shows FROM → TO explicitly
async function tsTick(){
  try {
    const d = await (await fetch('/tail_town_square?n=40')).json();
    const el = document.getElementById('ts-feed'); if(!el) return;
    const cmap = {ross:'#3b82f6',hq_claude:'#eab308',wren:'#a78bfa',tp_pip:'#22d3ee',acer_cass:'#f59e0b',council:'#94a3b8'};
    const rows = (d.messages||[]).map(m => {
      const from = (m.from||m.who||'?');
      const to = (m.to||'council');
      const fc = cmap[from] || '#94a3b8';
      const tc = cmap[to]   || '#94a3b8';
      const ts = (m.ts||'').slice(11,19);
      return '<div style="padding:5px 8px;margin:3px 0;border-left:2px solid '+fc+';background:rgba(255,255,255,0.03);border-radius:4px;">'
        + '<span style="color:#64748b;font-size:10px;">'+ts+'</span> '
        + '<b style="color:'+fc+'">'+from+'</b>'
        + '<span style="color:#64748b;"> → </span>'
        + '<b style="color:'+tc+'">'+to+'</b>: '
        + '<span style="color:#e2e8f0;">'+(m.text||'').replace(/</g,'&lt;').slice(0,300)+'</span>'
        + '</div>';
    }).join('');
    el.innerHTML = rows || '<div style="color:#64748b">no messages yet</div>';
    el.scrollTop = el.scrollHeight;
  } catch(e){}
}
// DRIFT — any state change
async function driftTick(){
  try {
    const d = await (await fetch('/drift_ticker')).json();
    const el = document.getElementById('drift-feed'); if(!el) return;
    const items = d.items||[];
    el.innerHTML = items.map(x => {
      const ts = (x.ts||'').slice(11,19);
      const sc = x.source==='town_square'?'#22d3ee':(x.source==='tasks'?'#a855f7':(x.source==='f47'?'#eab308':'#64748b'));
      return '<div style="padding:3px 6px;border-left:2px solid '+sc+';background:rgba(255,255,255,0.02);margin:2px 0;font-family:ui-monospace,monospace;">'
        + '<span style="color:#64748b">'+ts+'</span> '
        + '<span style="color:'+sc+';font-size:10px;">['+x.source+']</span> '
        + '<span style="color:#94a3b8">'+x.who+':</span> '
        + '<span style="color:#e2e8f0">'+(x.text||'').replace(/</g,'&lt;').slice(0,140)+'</span>'
        + '</div>';
    }).join('') || '<div style="color:#64748b">no drift yet</div>';
  } catch(e){}
}
// LINK HEALTH — probe each CEO's endpoint from browser side
async function linkTick(){
  const links = [
    {name:'HQ-Claude',  url:'http://127.0.0.1:8850/',      hint:'HQ dash'},
    {name:'Wren',       url:'http://127.0.0.1:8851/',      hint:'Wren dash'},
    {name:'Boardroom',  url:'http://127.0.0.1:8852/',      hint:'This dashboard'},
    {name:'TP-Pip',     url:'http://192.168.1.74:9110/',   hint:'TP dash (LAN)'},
    {name:'Acer-Cass',  url:'http://192.168.1.78:9000/',   hint:'Acer dash (LAN)'},
  ];
  const el = document.getElementById('link-health'); if(!el) return;
  const results = await Promise.all(links.map(async l => {
    const t0 = performance.now();
    try {
      const r = await fetch(l.url, {mode:'no-cors', cache:'no-store'});
      const ms = Math.round(performance.now()-t0);
      return {...l, ok:true, ms};
    } catch(e) { return {...l, ok:false, err:''+e}; }
  }));
  el.innerHTML = results.map(r => {
    const dot = r.ok ? '<span style="color:#10b981">●</span>' : '<span style="color:#ef4444">●</span>';
    const detail = r.ok ? `<span style="color:#64748b;font-size:10px;">${r.ms}ms</span>` : `<span style="color:#ef4444;font-size:10px;">broken · auto-recovering</span>`;
    return '<div style="padding:4px 6px;">'
      + dot + ' <b style="color:#e8ecf3">'+r.name+'</b> '
      + '<span style="color:#64748b;font-size:10.5px;">'+r.hint+'</span> · '+detail
      + '</div>';
  }).join('');
}
tick(); setInterval(tick, 3000);
tsTick(); setInterval(tsTick, 3000);
driftTick(); setInterval(driftTick, 3000);
linkTick(); setInterval(linkTick, 6000);
</script></body></html>"""


def _scoreboard() -> dict:
    """Count events per Council member to show who's doing the most work.
    Ross 2026-07-04: 'scoreboard to see who is doing the most work'."""
    log = REG / "qsb_council_tasks.jsonl"
    scores = {}
    if not log.exists():
        return {"members": [], "total_events": 0}
    total = 0
    for line in log.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line: continue
        try:
            e = json.loads(line)
        except Exception:
            continue
        actor = e.get("actor","?")
        ev = e.get("event","?")
        s = scores.setdefault(actor, {"actor": actor, "created": 0, "claimed": 0,
            "acknowledged": 0, "assigned": 0, "sandbox_passed": 0, "peer_signoff": 0,
            "done": 0, "noted": 0, "total": 0, "score": 0})
        if ev in s: s[ev] += 1
        s["total"] += 1
        total += 1
        # weighted score: shipping matters most
        weights = {"created":1, "claimed":1, "acknowledged":1, "assigned":1,
                   "noted":1, "sandbox_passed":5, "peer_signoff":5, "done":10}
        s["score"] += weights.get(ev, 1)
    ranked = sorted(scores.values(), key=lambda s: -s["score"])
    return {"ts": utc_iso(), "total_events": total,
            "members": ranked}


def _timeline_events() -> dict:
    """Read qsb_council_tasks.jsonl event log + Wren cycle log + trader
    milestones; return chronological event stream for the comic-strip
    timeline."""
    events = []
    log = REG / "qsb_council_tasks.jsonl"
    if log.exists():
        for line in log.read_text(errors="ignore").splitlines()[-200:]:
            line = line.strip()
            if not line: continue
            try:
                e = json.loads(line)
                events.append({
                    "ts": e.get("ts",""),
                    "actor": e.get("actor","?"),
                    "event": e.get("event","?"),
                    "task_id": e.get("task_id",""),
                    "text": (e.get("text") or e.get("title") or e.get("assignee") or "")[:200],
                })
            except Exception:
                pass
    events.sort(key=lambda e: e["ts"])
    return {"count": len(events), "events": events[-80:]}


TIMELINE_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Council Timeline — comic strip</title>
<style>
*{box-sizing:border-box}
body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:20px}
h1{margin:0 0 4px;color:#eab308}
.sub{color:#94a3b8;margin-bottom:14px;font-size:13px}
.strip{overflow-x:auto;overflow-y:hidden;white-space:nowrap;padding:20px 0;border-top:1px dashed #1f2937;border-bottom:1px dashed #1f2937}
.frame{display:inline-block;vertical-align:top;width:220px;background:#111827;border:1px solid #1f2937;border-radius:10px;padding:10px;margin-right:14px;position:relative;animation:pop-in .5s cubic-bezier(.16,1,.3,1);white-space:normal}
.frame::after{content:"";position:absolute;right:-14px;top:50%;width:14px;height:1px;background:#374151}
.frame:last-child::after{display:none}
.actor{display:flex;align-items:center;gap:6px;margin-bottom:4px}
.avatar{width:26px;height:26px;border-radius:50%;background:var(--c,#374151);color:#000;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:11px}
.who{font-weight:600;color:var(--c,#e8ecf3);font-size:12px}
.ev{display:inline-block;margin-top:4px;padding:2px 8px;border-radius:8px;font-size:11px;font-weight:600;background:#1f2937;color:#94a3b8}
.ev.created{background:#374151;color:#e8ecf3}
.ev.claimed,.ev.assigned{background:#f59e0b;color:#000}
.ev.acknowledged{background:#22d3ee;color:#000}
.ev.sandbox_passed{background:#eab308;color:#000}
.ev.peer_signoff{background:#a855f7;color:#fff}
.ev.done{background:#10b981;color:#000}
.ev.blocked{background:#ef4444;color:#fff}
.ev.noted{background:#0b0d12;color:#94a3b8;border:1px solid #1f2937}
.text{color:#cbd5e1;font-size:12px;margin-top:6px;max-height:60px;overflow:hidden;line-height:1.35}
.ts{color:#64748b;font-family:monospace;font-size:10px;margin-top:6px}
.tid{color:#64748b;font-family:monospace;font-size:10px}
@keyframes pop-in{0%{opacity:0;transform:translateX(30px) scale(.9)}100%{opacity:1;transform:translateX(0) scale(1)}}
.legend{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;font-size:11px}
.legend span{padding:2px 8px;border-radius:8px}
.pulse{display:inline-block;width:8px;height:8px;border-radius:50%;background:#10b981;margin-right:6px;animation:p 2s infinite}
@keyframes p{0%,100%{opacity:1}50%{opacity:.4}}
</style></head><body>
<h1><span class=pulse></span>📽️ Council Timeline</h1>
<div class=sub>Every task event as a frame — who took what, when. Newest frames slide in from the right. Auto-refresh every 3s.</div>
<div class=legend>
  <span style="background:#374151;color:#e8ecf3">created</span>
  <span style="background:#f59e0b;color:#000">claimed/assigned</span>
  <span style="background:#22d3ee;color:#000">acknowledged</span>
  <span style="background:#eab308;color:#000">sandbox-pass</span>
  <span style="background:#a855f7;color:#fff">peer-signoff</span>
  <span style="background:#10b981;color:#000">done ✓</span>
  <span style="background:#ef4444;color:#fff">blocked</span>
</div>
<div class=strip id=strip></div>
<script>
const COLORS = {hq_claude:'#eab308', wren:'#a78bfa', tp_pip:'#22d3ee', acer_cass:'#f59e0b',
                ross:'#e8ecf3', ross_via_hq:'#e8ecf3', hermes:'#3b82f6', iquest:'#10b981'};
const INITIAL = {hq_claude:'HQ', wren:'W', tp_pip:'TP', acer_cass:'AC',
                 ross:'R', ross_via_hq:'R'};
let lastCount = 0;
async function tick(){
  try{
    const d = await (await fetch('/timeline/data')).json();
    if (d.count === lastCount) return;
    lastCount = d.count;
    const strip = document.getElementById('strip');
    strip.innerHTML = d.events.map(e => {
      const c = COLORS[e.actor] || '#374151';
      const ini = INITIAL[e.actor] || (e.actor||'?').substring(0,2).toUpperCase();
      const ev = e.event.replace(/_/g,' ');
      const ts = (e.ts||'').substring(11,19);
      return `<div class=frame style="--c:${c}">
        <div class=actor>
          <div class=avatar style="background:${c}">${ini}</div>
          <span class=who>${e.actor}</span>
        </div>
        <span class="ev ${e.event}">${ev}</span>
        <div class=text>${(e.text||'').replace(/</g,'&lt;')}</div>
        <div class=ts>${ts}</div>
        <div class=tid>${e.task_id||''}</div>
      </div>`;
    }).join('');
    strip.scrollLeft = strip.scrollWidth;
  }catch(e){console.error(e)}
}
tick(); setInterval(tick, 3000);
</script></body></html>"""


TASKS_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Council Tasks — Live</title>
<style>
*{box-sizing:border-box}
body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:18px}
h1{margin:0 0 4px;color:#eab308}
.sub{color:#94a3b8;margin-bottom:14px;font-size:13px}
.stats{display:flex;gap:10px;margin-bottom:14px;flex-wrap:wrap}
.stat{background:#1e293b;color:#94a3b8;padding:4px 10px;border-radius:12px;font-size:12px;transition:all .3s}
.stat b{color:#eab308}
.board{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}
.col{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:12px;min-height:200px;position:relative}
.col h2{margin:0 0 10px;font-size:.95em;text-transform:uppercase;letter-spacing:.06em;color:#94a3b8;display:flex;justify-content:space-between}
.col h2 .cnt{background:#374151;color:#e8ecf3;padding:2px 8px;border-radius:10px;font-size:11px;transition:transform .2s}
.task{background:#0b0d12;border:1px solid #1f2937;border-radius:8px;padding:10px;margin-bottom:8px;cursor:pointer;transition:transform .18s,border-color .18s,box-shadow .18s;animation:slide-in .3s ease-out}
.task:hover{border-color:#eab308;transform:translateY(-2px);box-shadow:0 4px 12px rgba(234,179,8,.15)}
.task .title{font-weight:600;color:#e8ecf3;font-size:13px;margin-bottom:4px}
.task .desc{color:#94a3b8;font-size:11.5px;line-height:1.4;max-height:44px;overflow:hidden}
.rev{display:inline-flex;align-items:center;gap:6px;background:#0b0d12;border:1px solid #1f2937;border-radius:14px;padding:3px 10px;margin:6px 0 4px;font-family:monospace;font-size:10.5px}
.rev-svg{width:44px;height:24px;flex:none}
.rev-needle{transform-origin:22px 22px;transition:transform .5s cubic-bezier(.34,1.56,.64,1)}
.rev-rpm{color:#e8ecf3;font-weight:700}
.rev-label{color:#64748b}
.rev.stalled .rev-rpm{color:#ef4444}
.rev.healthy .rev-rpm{color:#10b981}
.rev.hot .rev-rpm{color:#eab308}
@keyframes rev-pulse{0%,100%{opacity:1}50%{opacity:.5}}
.rev.hot .rev-rpm{animation:rev-pulse 1s infinite}
.progress{height:6px;background:#0b0d12;border-radius:3px;margin:6px 0 4px;overflow:hidden;position:relative}
.progress-bar{height:100%;border-radius:3px;transition:width .4s ease;background:linear-gradient(90deg,#f59e0b,#eab308)}
.progress-bar.done{background:linear-gradient(90deg,#10b981,#22d3ee)}
.progress-bar.blocked{background:linear-gradient(90deg,#ef4444,#dc2626)}
.eta{font-size:10.5px;color:#64748b;margin-top:2px;font-family:monospace}
.task .meta{display:flex;gap:6px;margin-top:6px;flex-wrap:wrap}
.tag{display:inline-block;padding:1px 6px;border-radius:8px;font-size:10px;font-weight:600}
.tag.owner{background:#1e40af;color:#fff}
.tag.by{background:#374151;color:#cbd5e1}
.tag.pri-high{background:#ef4444;color:#fff}
.tag.pri-normal{background:#374151;color:#cbd5e1}
.tag.age{background:#0b0d12;color:#64748b;border:1px solid #1f2937}
.actions{display:flex;gap:4px;margin-top:6px;flex-wrap:wrap}
.btn{background:#374151;color:#e8ecf3;border:none;padding:3px 8px;border-radius:5px;cursor:pointer;font-size:10.5px;transition:all .15s}
.btn:hover{background:#eab308;color:#000}
.btn.done{background:#10b981;color:#000}
.btn.done:hover{background:#059669;color:#fff}
.compose{background:#111827;border:1px solid #1f2937;border-radius:10px;padding:12px;margin-bottom:14px;display:flex;gap:6px;flex-wrap:wrap}
.compose input, .compose select{background:#0b0d12;color:#e8ecf3;border:1px solid #374151;border-radius:6px;padding:7px 10px;font-size:13px}
.compose input.title{flex:1;min-width:200px}
.compose input.desc{flex:2;min-width:220px}
.compose button{background:#eab308;color:#000;border:none;padding:7px 14px;border-radius:6px;cursor:pointer;font-weight:600}
.col.open{border-top:3px solid #94a3b8}
.col.claimed, .col.in_progress{border-top:3px solid #f59e0b}
.col.blocked{border-top:3px solid #ef4444}
.col.done{border-top:3px solid #10b981}
.col.done .task{opacity:.65}
@keyframes slide-in{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:translateX(0)}}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.15)}}
.pulse{animation:pulse 1.2s ease-out}
.member-filter{margin-left:auto;padding:5px 10px;background:#1e293b;color:#94a3b8;border-radius:6px;font-size:12px}
/* --- Ross 2026-07-05: 5 live animated brain-panel features --- */
@keyframes phone-live-pulse{0%{transform:scale(1);opacity:1}50%{transform:scale(1.7);opacity:0.35}100%{transform:scale(1);opacity:1}}
@keyframes phone-live-halo{0%,100%{filter:brightness(1)}50%{filter:brightness(1.9)}}
@keyframes wire-flow{to{stroke-dashoffset:-40}}
@keyframes needle-sweep{from{opacity:0.4}to{opacity:1}}
@keyframes odo-flash{0%{color:#22d3ee}50%{color:#e8ecf3;text-shadow:0 0 8px #22d3ee}100%{color:#22d3ee}}
.phone-dot{width:10px;height:10px;border-radius:50%;display:inline-block;flex-shrink:0}
.phone-live{animation:phone-live-pulse 1.4s ease-in-out infinite, phone-live-halo 1.4s ease-in-out infinite}
.brain-tile{padding:8px;background:#0b1220;border-left:3px solid #94a3b8;border-radius:5px;position:relative;overflow:hidden}
.brain-tile.active{box-shadow:inset 0 0 12px rgba(255,255,255,0.06)}
.spark-container{margin:4px 0}
.caller-pill{display:inline-block;padding:1px 6px;margin:2px 3px 0 0;border-radius:8px;font-size:9.5px;font-weight:600;font-family:ui-monospace,monospace}
.brain-odo{display:flex;gap:14px;padding:8px 10px;background:#0b1220;border:1px solid #22334a;border-radius:8px;margin-bottom:10px;font-family:ui-monospace,monospace}
.brain-odo .odo-cell{display:flex;flex-direction:column;gap:2px;flex:1}
.brain-odo .odo-label{color:#94a3b8;font-size:9.5px;text-transform:uppercase;letter-spacing:0.06em}
.brain-odo .odo-num{color:#22d3ee;font-size:18px;font-weight:700;font-variant-numeric:tabular-nums}
.brain-odo .odo-num.flash{animation:odo-flash 0.6s ease-out}
.brain-wires-strip{margin-bottom:10px;padding:6px 10px;background:#0b1220;border-radius:8px;font-size:10.5px;color:#94a3b8;min-height:24px}
.brain-wires-strip svg{vertical-align:middle}
.wire-line{stroke-dasharray:5 3;animation:wire-flow 0.6s linear infinite}
/* --- Ross 2026-07-05: task-card upgrade CSS --- */
@keyframes pulse-slow{0%,100%{opacity:1}50%{opacity:0.55}}
.task.stale{border-left:3px solid #ef4444 !important;box-shadow:0 0 10px rgba(239,68,68,0.15)}
.time-strip{display:flex;gap:8px;margin:6px 0 4px;padding:5px 8px;background:#0b1220;border-radius:5px;font-family:ui-monospace,monospace;font-size:10.5px;color:#94a3b8;flex-wrap:wrap;align-items:center}
.time-strip.done{color:#10b981;background:rgba(16,185,129,0.06)}
.time-strip.done .took b{color:#e8ecf3}
.time-strip.live .live-tick b{color:#22d3ee}
.time-strip b{color:#e8ecf3}
.collab-row{display:flex;gap:5px;margin:5px 0;font-size:10.5px;color:#94a3b8;align-items:center;flex-wrap:wrap}
.collab-chip{padding:2px 7px;border-radius:8px;font-size:10px;font-weight:600;font-family:ui-monospace,monospace}
.delivered{margin-top:6px;padding:6px 9px;background:rgba(16,185,129,0.10);border-left:3px solid #10b981;border-radius:4px;font-size:11px;color:#a7f3d0;font-family:ui-monospace,monospace;line-height:1.4}
.ceo-cell{display:flex;flex-direction:column;gap:2px;padding:4px 10px;border-left:3px solid #374151;min-width:100px}
.ceo-cell .ceo-name{font-size:11px;font-weight:700;letter-spacing:0.04em;text-transform:uppercase}
.ceo-cell .ceo-nums{font-size:12px;color:#94a3b8;font-variant-numeric:tabular-nums}
.ceo-cell .ceo-nums b{color:#e8ecf3;font-size:14px}
.ceo-cell.zero .ceo-nums b{color:#ef4444}
/* --- Ross 2026-07-05: Wren-designed animations (3 picks she signed off) --- */
/* 1. Task Fade In — new tasks fade in on arrival */
@keyframes wren-fade-in{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:translateY(0)}}
.task{animation:wren-fade-in 0.5s ease-out both}
/* 2. Priority Color Change — urgent red, high yellow, normal cyan, low grey */
.task.pri-urgent{border-left:4px solid #ef4444 !important;box-shadow:inset 3px 0 0 rgba(239,68,68,0.15)}
.task.pri-high{border-left:4px solid #f59e0b !important;box-shadow:inset 3px 0 0 rgba(245,158,11,0.12)}
.task.pri-normal{border-left:4px solid #22d3ee}
.task.pri-low{border-left:4px solid #64748b;opacity:0.85}
/* 3. Completion Slide Out — done tasks slide right-to-left (filing motion) on first render */
@keyframes wren-slide-file{from{transform:translateX(24px);opacity:0}60%{transform:translateX(-4px);opacity:1}to{transform:translateX(0);opacity:1}}
.col.done .task{animation:wren-slide-file 0.65s cubic-bezier(.34,1.56,.64,1) both}
/* --- HQ-Claude's 3 animations (Ross 2026-07-05 asked for 3 more) --- */
/* 4. Column count ripple — when a column count changes, ripple outward */
@keyframes hq-count-ripple{0%{transform:scale(1);box-shadow:0 0 0 0 rgba(34,211,238,0.7)}70%{transform:scale(1.15);box-shadow:0 0 0 10px rgba(34,211,238,0)}100%{transform:scale(1);box-shadow:0 0 0 0 rgba(34,211,238,0)}}
.cnt.ripple{animation:hq-count-ripple 0.7s ease-out}
/* 5. Brain-router pulse ring on ACTIVE provider tile — like heartbeat */
@keyframes hq-heart-ring{0%,100%{box-shadow:inset 0 0 0 1px transparent}50%{box-shadow:inset 0 0 0 2px rgba(34,211,238,0.35)}}
.brain-col-tile.active{animation:hq-heart-ring 1.6s ease-in-out infinite}
/* 6. Stale-task shake — when a task hits STALE, briefly shake to grab attention */
@keyframes hq-stale-shake{0%,100%{transform:translateX(0)}10%,30%,50%,70%,90%{transform:translateX(-2px)}20%,40%,60%,80%{transform:translateX(2px)}}
.task.stale{animation:hq-stale-shake 0.6s ease-in-out, wren-fade-in 0.5s ease-out both}
</style></head><body>
<h1>📋 Council Task Board</h1>
<div class=sub>Shared task engine — every Council member reads + writes. Live, animated, survives sessions.</div>
<!-- Ross 2026-07-05: BIG summary line "N tasks (X done, Y in progress, Z open)" -->
<div style="display:flex;align-items:baseline;gap:14px;margin:8px 0 12px">
  <div id=summary-line style="font-size:22px;font-weight:700;color:#e8ecf3;font-family:ui-monospace,monospace">— tasks (— done, — in progress, — open)</div>
  <div id=live-pulse style="font-size:10.5px;color:#64748b;font-family:ui-monospace,monospace">last update: never</div>
</div>
<!-- Ross 2026-07-05: live throughput + queue depth stats -->
<div id=throughput-strip style="display:flex;gap:14px;padding:8px 12px;background:#0e1420;border:1px solid #22334a;border-radius:8px;margin-bottom:10px;font-family:ui-monospace,monospace;font-size:11.5px;color:#94a3b8;flex-wrap:wrap"></div>
<div class=stats id=stats></div>
<!-- Ross 2026-07-05: per-CEO participation strip so imbalance is visible -->
<div id=ceo-strip style="display:flex;gap:10px;margin:8px 0 14px;padding:10px 12px;background:#0e1420;border:1px solid #22334a;border-radius:8px;font-family:ui-monospace,monospace;flex-wrap:wrap;"></div>
<div class=compose>
  <input class=title id=t-title placeholder="task title...">
  <input class=desc id=t-desc placeholder="description (optional)">
  <select id=t-priority><option value=normal>normal</option><option value=high>high</option><option value=low>low</option></select>
  <select id=t-actor>
    <option value=hq_claude>HQ-Claude</option>
    <option value=wren>Wren</option>
    <option value=tp_pip>TP-Pip</option>
    <option value=acer_cass>Acer-Cass</option>
    <option value=ross>Ross</option>
  </select>
  <button onclick=create()>+ create</button>
  <select id=t-assign><option value="">assign to...</option>
    <option value=hq_claude>HQ-Claude</option>
    <option value=wren>Wren</option>
    <option value=tp_pip>TP-Pip</option>
    <option value=acer_cass>Acer-Cass</option>
  </select>
  <button onclick=createAndAssign() style=background:#a855f7;color:#fff>+ create & assign</button>
</div>
<div class=board id=board></div>
<!-- Ross 2026-07-05: LIVE LIST of all tasks with progress bars (#113) -->
<div id=tasklist-window style="margin-top:20px;padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:10px;">
  <h2 style="margin:0 0 6px;color:#eab308;font-size:1.15em;">📋 LIVE LIST · every task + progress bar</h2>
  <div style="display:flex;gap:8px;margin-bottom:8px;font-size:11px;flex-wrap:wrap">
    <button onclick="filterList('all')" id="fl-all" style="background:#eab308;color:#000;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-weight:700">all</button>
    <button onclick="filterList('open')" id="fl-open" style="background:#1e293b;color:#94a3b8;border:none;padding:4px 10px;border-radius:6px;cursor:pointer">open</button>
    <button onclick="filterList('in-flight')" id="fl-inflight" style="background:#1e293b;color:#94a3b8;border:none;padding:4px 10px;border-radius:6px;cursor:pointer">in-flight</button>
    <button onclick="filterList('awaiting')" id="fl-awaiting" style="background:#1e293b;color:#94a3b8;border:none;padding:4px 10px;border-radius:6px;cursor:pointer">awaiting signoff</button>
    <button onclick="filterList('done')" id="fl-done" style="background:#1e293b;color:#94a3b8;border:none;padding:4px 10px;border-radius:6px;cursor:pointer">done</button>
  </div>
  <div id="tasklist-body" style="max-height:600px;overflow-y:auto;display:grid;grid-template-columns:1fr;gap:4px"></div>
</div>
<!-- Ross 2026-07-05: CODE WRITTEN LIVE window · files touched in last hour -->
<div id=code-window style="margin-top:20px;padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:10px;">
  <h2 style="margin:0 0 6px;color:#22d3ee;font-size:1.15em;">📝 CODE WRITTEN LIVE · files touched in last hour</h2>
  <div style="color:#94a3b8;font-size:11.5px;margin-bottom:10px;">Files under tools/ modified in the last hour + first-30-lines preview + who touched them.</div>
  <div id=code-list style="display:grid;grid-template-columns:1fr;gap:8px;"></div>
</div>

<!-- Ross 2026-07-05: BRAIN ROUTER · live rev gauges + 5 live animations + caller attribution -->
<div id=brain-panel style="margin-top:20px;padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:10px;">
  <h2 style="margin:0 0 6px;color:#22d3ee;font-size:1.15em;">🧠 BRAIN ROUTER · live worker usage · who's on which line</h2>
  <div style="color:#94a3b8;font-size:11.5px;margin-bottom:10px;">
    Groq · Gemini · DeepSeek · OpenAI · Ollama (LAN + local). Each tile shows the last-5-min activity + which CEO/tool is calling. Pulsing dot = live in-flight. Wires below = who's currently on which line.
  </div>
  <!-- 1. ANIMATED ODOMETER · calls/hr + $ today · digits flash on change -->
  <div class="brain-odo">
    <div class="odo-cell"><span class="odo-label">calls · last hour</span><span class="odo-num" id="odo-calls">0</span></div>
    <div class="odo-cell"><span class="odo-label">calls · last 5min</span><span class="odo-num" id="odo-5m">0</span></div>
    <div class="odo-cell"><span class="odo-label">cost · all-time</span><span class="odo-num" id="odo-cost">$0.0000</span></div>
    <div class="odo-cell"><span class="odo-label">providers live</span><span class="odo-num" id="odo-live">0</span></div>
  </div>
  <!-- 2. LIVE WIRE STRIP · animated dashed lines CEO→provider only when active -->
  <div class="brain-wires-strip" id="brain-wires-strip">idle · no active brain calls</div>
  <div id=brain-gauges style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:10px;"></div>
  <div style="margin-top:10px;padding:8px;background:#0b1220;border-radius:6px;">
    <div style="font-size:11px;color:#94a3b8;margin-bottom:4px;">RECENT CALLS · who used which brain</div>
    <div id=brain-recent style="max-height:180px;overflow-y:auto;font-size:10.5px;font-family:ui-monospace,monospace;color:#cbd5e1;"></div>
  </div>
</div>

<script>
const BRAIN_COLORS = {groq:'#f97316',gemini:'#3b82f6',gemini_ai_studio:'#3b82f6',gemini_vertex:'#3b82f6',cohere:'#ec4899',deepseek:'#8b5cf6',openai:'#10b981',kimi:'#f43f5e',ollama_lan:'#64748b',ollama_local:'#94a3b8','router:groq':'#f97316','router:gemini_ai_studio':'#3b82f6','router:cohere':'#ec4899','router:deepseek':'#8b5cf6','router:openai':'#10b981','router:kimi':'#f43f5e'};
const CALLER_COLORS = {hq_claude:'#eab308', wren:'#a78bfa', tp_pip:'#22d3ee', 'TP-Pip':'#22d3ee', acer_cass:'#f59e0b', 'Acer-Cass':'#f59e0b', ross:'#e8ecf3', distiller_wren:'#a78bfa', distiller_tp_pip:'#22d3ee', distiller_acer_cass:'#f59e0b', distiller_hq_claude:'#eab308', verify_wrap:'#ec4899'};
function callerNick(n){return (n||'?').replace(/^distiller_/,'d·').replace('_cass','').replace('_pip','').replace('_claude','')}
function callerColor(n){return CALLER_COLORS[n] || '#94a3b8'}

// (feature 3) 60-sample rolling history per provider · scrolls left · fed by tick
const SPARK_HIST = {};
function pushSpark(name, val){
  if(!SPARK_HIST[name]) SPARK_HIST[name]=[];
  SPARK_HIST[name].push(val);
  if(SPARK_HIST[name].length > 60) SPARK_HIST[name].shift();
}
function renderSpark(name){
  const h = SPARK_HIST[name] || [];
  if(h.length < 2) return `<svg viewBox="0 0 100 18" preserveAspectRatio="none" style="width:100%;height:18px;"><text x="50" y="12" text-anchor="middle" fill="#334155" font-size="7">warming...</text></svg>`;
  const max = Math.max(1, ...h);
  const pts = h.map((v,i) => `${(i/(h.length-1))*100},${17 - (v/max)*15}`).join(' ');
  const c = BRAIN_COLORS[name] || '#94a3b8';
  return `<svg viewBox="0 0 100 18" preserveAspectRatio="none" style="width:100%;height:18px;">
    <polyline points="${pts}" stroke="${c}" stroke-width="0.9" fill="none" opacity="0.85"/>
    <polyline points="0,18 ${pts} 100,18" fill="${c}" opacity="0.12"/>
  </svg>`;
}

// (feature 4) live needle rev-gauge · SVG arc + rotating needle
function renderNeedle(name, active){
  const c = BRAIN_COLORS[name] || '#94a3b8';
  // active 0 → -80deg, active 15+ → +80deg (full sweep)
  const angle = Math.max(-80, Math.min(80, active * 10 - 80));
  return `<svg viewBox="0 0 100 60" style="width:100%;height:42px;">
    <path d="M12,54 A42,42 0 0,1 88,54" stroke="#1e293b" stroke-width="2.5" fill="none"/>
    <path d="M12,54 A42,42 0 0,1 88,54" stroke="${c}" stroke-width="2.5" fill="none" stroke-dasharray="${Math.min(100, active*8)} 200" opacity="0.7"/>
    <g style="transform-origin:50px 54px;transform:rotate(${angle}deg);transition:transform 0.7s cubic-bezier(.34,1.56,.64,1)">
      <line x1="50" y1="54" x2="50" y2="16" stroke="${c}" stroke-width="1.8" style="animation:needle-sweep 0.7s ease-out"/>
      <circle cx="50" cy="16" r="1.6" fill="${c}"/>
    </g>
    <circle cx="50" cy="54" r="3" fill="${c}"/>
    <text x="50" y="40" text-anchor="middle" fill="${c}" font-size="10" font-weight="700" font-family="ui-monospace,monospace">${active}</text>
  </svg>`;
}

// (feature 1) pulsing phone-light + (5) caller attribution pills
function brainGauge(name, stats, callers){
  const c = BRAIN_COLORS[name] || '#94a3b8';
  const active = stats.last_5m || 0;
  const total = stats.total || 0;
  const avgLat = total ? (stats.lat_sum/total).toFixed(2) : '-';
  const cost = (stats.cost_sum||0).toFixed(4);
  const pulseCls = active > 0 ? 'phone-live' : '';
  // who's calling THIS provider (top 3)
  const users = Object.entries(callers).filter(([_,cd]) => cd.providers && cd.providers[name]).map(([nm,cd]) => ({nm, count: cd.providers[name]})).sort((a,b)=>b.count-a.count).slice(0,3);
  const pillsHtml = users.map(u => `<span class="caller-pill" style="background:${callerColor(u.nm)}22;color:${callerColor(u.nm)};border:1px solid ${callerColor(u.nm)}55;">${callerNick(u.nm)} · ${u.count}</span>`).join('') || '<span style="color:#334155;font-size:9px;">no callers yet</span>';
  return `<div class="brain-tile ${active>0?'active':''}" data-name="${name}" style="border-left-color:${c};">
    <div style="display:flex;align-items:center;gap:6px;">
      <span class="phone-dot ${pulseCls}" style="background:${c};box-shadow:0 0 ${active?12:2}px ${c};"></span>
      <b style="color:${c};font-size:12px;flex:1;">${name}</b>
      <span style="color:#64748b;font-size:9.5px;">${total} tot</span>
    </div>
    ${renderNeedle(name, active)}
    ${renderSpark(name)}
    <div style="display:flex;gap:8px;font-size:9.5px;color:#94a3b8;margin-top:2px;">
      <span>lat ${avgLat}s</span><span>· $${cost}</span>
    </div>
    <div style="margin-top:5px;">${pillsHtml}</div>
  </div>`;
}

// (feature 2) live wire strip · animated dashed lines CEO→provider only when active
function renderWiresStrip(callers, providers){
  // Find each CEO's most-active-recent provider (from providers count, limited to callers with recent activity)
  const lines = [];
  const activeProviders = new Set(Object.entries(providers).filter(([_,s])=>s.last_5m>0).map(([n])=>n));
  Object.entries(callers).forEach(([caller, cd]) => {
    if(!cd.providers) return;
    const sorted = Object.entries(cd.providers).sort((a,b)=>b[1]-a[1]);
    const top = sorted.find(([p])=>activeProviders.has(p));
    if(top) lines.push({caller, provider: top[0], count: top[1]});
  });
  if(!lines.length) return '<span style="color:#334155">idle · no active brain calls</span>';
  return lines.map(l => {
    const cc = callerColor(l.caller);
    const pc = BRAIN_COLORS[l.provider] || '#94a3b8';
    return `<span style="display:inline-flex;align-items:center;gap:5px;margin-right:14px;padding:2px 0;">
      <b style="color:${cc};">${callerNick(l.caller)}</b>
      <svg width="46" height="10" style="vertical-align:middle;">
        <line class="wire-line" x1="0" y1="5" x2="46" y2="5" stroke="${pc}" stroke-width="2"/>
        <circle cx="44" cy="5" r="2" fill="${pc}"/>
      </svg>
      <b style="color:${pc};">${l.provider}</b>
      <span style="color:#64748b;font-size:9.5px;">${l.count}</span>
    </span>`;
  }).join('');
}

// (feature 3 cont.) animated odometer · digits tween + flash on change
function animateOdo(id, target, isCost){
  const el = document.getElementById(id);
  if(!el) return;
  const cur = parseFloat((el.textContent||'0').replace(/[^\d.-]/g,''))||0;
  const targetNum = (typeof target === 'number') ? target : (parseFloat((''+target).replace(/[^\d.-]/g,''))||0);
  if(cur === targetNum){return}
  el.classList.add('flash');
  setTimeout(()=>el.classList.remove('flash'), 700);
  const start = performance.now();
  const dur = 700;
  function step(t){
    const p = Math.min(1, (t-start)/dur);
    const v = cur + (targetNum-cur)*p;
    el.textContent = isCost ? '$'+v.toFixed(4) : Math.round(v).toLocaleString();
    if(p<1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
}

// Ross 2026-07-05 #90: always show all 4 external AIs even when idle
const ALL_PROVIDERS = ['groq','gemini','cohere','deepseek','openai','kimi','ollama_lan','ollama_local'];
async function brainTick(){
  try{
    const d = await (await fetch('/brain/usage', {cache:'no-store'})).json();
    const providers = d.providers || {};
    // ensure all 4 tiles show, even at 0 calls
    ALL_PROVIDERS.forEach(p => {
      if(!providers[p]) providers[p] = {total:0, last_5m:0, last_1h:0, lat_sum:0, cost_sum:0};
    });
    const callers = d.callers || {};
    // update sparklines with current last_5m per provider
    Object.entries(providers).forEach(([n,s]) => pushSpark(n, s.last_5m || 0));
    const list = Object.entries(providers).sort((a,b) => b[1].total - a[1].total);
    document.getElementById('brain-gauges').innerHTML = list.map(([n,s]) => brainGauge(n, s, callers)).join('') || '<div style="color:#64748b;font-size:11px;grid-column:1/-1;">no brain calls yet</div>';
    // 1. odometer values
    const totHr = Object.values(providers).reduce((a,s)=>a+(s.last_1h||0),0);
    const tot5m = Object.values(providers).reduce((a,s)=>a+(s.last_5m||0),0);
    const totCost = Object.values(providers).reduce((a,s)=>a+(s.cost_sum||0),0);
    const live = Object.values(providers).filter(s => (s.last_5m||0) > 0).length;
    animateOdo('odo-calls', totHr, false);
    animateOdo('odo-5m', tot5m, false);
    animateOdo('odo-cost', totCost, true);
    animateOdo('odo-live', live, false);
    // 2. wires strip
    document.getElementById('brain-wires-strip').innerHTML = renderWiresStrip(callers, providers);
    // recent calls list
    const rec = (d.recent||[]).map(r => {
      const c = BRAIN_COLORS[r.provider] || '#94a3b8';
      const cc = callerColor(r.caller);
      return `<div style="padding:3px 0;"><span style="color:#64748b;">${(r.ts||'').slice(11,19)}</span> <b style="color:${c}">${r.provider}</b> <span style="color:${cc}">${callerNick(r.caller)}</span> · ${r.latency_s}s · ${(r.reply_head||'').replace(/</g,'&lt;')}</div>`;
    }).join('');
    document.getElementById('brain-recent').innerHTML = rec || '<div style="color:#64748b;">no recent calls</div>';
  }catch(e){console.error('brainTick',e)}
}
brainTick(); setInterval(brainTick, 1000);
// Ross 2026-07-05: populate CODE WRITTEN LIVE window
async function codeTick(){
  try{
    const d = await (await fetch('/code_written',{cache:'no-store'})).json();
    const el = document.getElementById('code-list'); if(!el) return;
    const items = d.items || [];
    if(!items.length){ el.innerHTML = '<div style="color:#64748b;font-size:11px">no files touched in the last hour</div>'; return; }
    el.innerHTML = items.map(it => {
      const ageMin = Math.floor((it.modified_ago_s||0)/60);
      const ageLbl = ageMin < 1 ? 'just now' : (ageMin+'m ago');
      const preview = (it.preview||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');
      return `<div style="padding:8px 10px;background:#0b1220;border-left:3px solid #22d3ee;border-radius:5px">
        <div style="display:flex;justify-content:space-between;align-items:baseline">
          <b style="color:#22d3ee;font-family:ui-monospace,monospace;font-size:12px">${it.path}</b>
          <span style="color:#94a3b8;font-size:10px">${it.size}b · ${ageLbl}</span>
        </div>
        <pre style="margin:6px 0 0;padding:6px 8px;background:#000;border-radius:4px;font-size:10.5px;color:#94a3b8;max-height:140px;overflow-y:auto;font-family:ui-monospace,monospace;line-height:1.35">${preview}</pre>
      </div>`;
    }).join('');
  }catch(e){}
}
codeTick(); setInterval(codeTick, 5000);
// Ross 2026-07-05 #113: LIVE LIST view of every task with progress bars
let CURRENT_FILTER = 'all';
function filterList(f){
  CURRENT_FILTER = f;
  ['all','open','inflight','awaiting','done'].forEach(k => {
    const el = document.getElementById('fl-'+k);
    if(!el) return;
    const match = (k === 'inflight' && f === 'in-flight') || (k === f);
    el.style.background = match ? '#eab308' : '#1e293b';
    el.style.color = match ? '#000' : '#94a3b8';
    el.style.fontWeight = match ? '700' : '400';
  });
  listTick();
}
const STAGE_PCT = {open:5, submitted:8, assigned:15, acknowledged:30, claimed:40, in_progress:55, awaiting_peer_signoff:75, ready_to_ship:90, done:100, blocked: null};
function matchFilter(t, f){
  const st = t.state;
  if(f === 'all') return true;
  if(f === 'open') return st === 'open' || st === 'submitted' || st === 'assigned';
  if(f === 'in-flight') return ['claimed','acknowledged','in_progress'].includes(st);
  if(f === 'awaiting') return st === 'awaiting_peer_signoff' || st === 'ready_to_ship';
  if(f === 'done') return st === 'done';
  return true;
}
async function listTick(){
  try{
    const d = await (await fetch('/tasks/data',{cache:'no-store'})).json();
    const el = document.getElementById('tasklist-body'); if(!el) return;
    const rows = (d.tasks || []).filter(t => matchFilter(t, CURRENT_FILTER));
    // priority sort: in-flight first, then awaiting, then open, then done
    const stOrder = {claimed:0, in_progress:0, acknowledged:0, awaiting_peer_signoff:1, ready_to_ship:1, assigned:2, open:2, submitted:2, done:3, blocked:4};
    rows.sort((a,b) => (stOrder[a.state]??5) - (stOrder[b.state]??5) || (a.created_at||'').localeCompare(b.created_at||''));
    if(!rows.length){ el.innerHTML = '<div style="color:#64748b;font-size:11px;padding:8px">no tasks match this filter</div>'; return; }
    el.innerHTML = rows.map((t,i) => {
      const pct = STAGE_PCT[t.state] ?? 15;
      const barColor = t.state==='done' ? '#10b981' : (t.state==='blocked' ? '#ef4444' : (pct>=75 ? '#eab308' : '#22d3ee'));
      const ownerColor = OWNERS[t.owner] || '#374151';
      const ownerLbl = t.owner ? `<span style="background:${ownerColor};color:#000;padding:1px 6px;border-radius:8px;font-size:10px;font-family:ui-monospace,monospace;font-weight:700">@${t.owner}</span>` : '<span style="color:#334155;font-size:10px">unclaimed</span>';
      const startIso = t.claimed_at || t.assigned_at || t.acknowledged_at || t.started_at || t.created_at;
      let ageLbl = '';
      if(startIso){
        const a = Math.floor((Date.now() - new Date(startIso).getTime())/1000);
        ageLbl = a < 60 ? a+'s' : (a < 3600 ? Math.floor(a/60)+'m' : Math.floor(a/3600)+'h');
      }
      const num = (t.title||'').match(/^#(\d+)/)?.[1] || '';
      const title = (t.title||'(untitled)').replace(/^#\d+\s*/, '');
      return `<div style="display:grid;grid-template-columns:30px 1fr 100px 120px 40px 50px;gap:8px;align-items:center;padding:5px 8px;background:${t.state==='done'?'rgba(16,185,129,0.05)':'#0b1220'};border-left:2px solid ${barColor};border-radius:4px;font-size:11.5px">
        <span style="color:#64748b;font-family:ui-monospace,monospace">#${num || i}</span>
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#e2e8f0" title="${(t.description||'').replace(/"/g,'&quot;').slice(0,300)}">${title.replace(/</g,'&lt;').slice(0,90)}</div>
        <span style="color:#94a3b8;font-size:10.5px;font-family:ui-monospace,monospace">${(t.state||'?').replace(/_/g,' ')}</span>
        <div style="height:12px;background:#000;border-radius:6px;overflow:hidden;position:relative">
          <div style="height:100%;background:${barColor};width:${pct}%;transition:width 0.6s ease-out"></div>
          <span style="position:absolute;top:0;left:0;right:0;text-align:center;font-size:9px;color:${pct>50?'#000':'#e8ecf3'};font-weight:700;line-height:12px">${pct}%</span>
        </div>
        ${ownerLbl}
        <span style="color:#64748b;font-size:10px">${ageLbl}</span>
      </div>`;
    }).join('');
  }catch(e){console.error('listTick',e)}
}
listTick(); setInterval(listTick, 3000);
// Populate the BRAIN col inside the columns row with the live provider cards
async function populateBrainCol(){
  try{
    const d = await (await fetch('/brain/usage', {cache:'no-store'})).json();
    const providers = d.providers || {};
    const callers = d.callers || {};
    const list = Object.entries(providers).sort((a,b) => (b[1].last_5m||0) - (a[1].last_5m||0));
    const cnt = document.getElementById('brain-col-cnt');
    if(cnt) cnt.textContent = list.length + ' live';
    const body = document.getElementById('brain-col-body');
    if(!body) return;
    if(!list.length){ body.innerHTML = '<div style="color:#64748b">no external AI calls yet</div>'; return; }
    body.innerHTML = list.map(([n,s]) => {
      const c = BRAIN_COLORS[n] || '#94a3b8';
      const active = s.last_5m || 0;
      const dot = active > 0 ? `<span class="phone-dot phone-live" style="background:${c};box-shadow:0 0 10px ${c};display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px"></span>` : `<span style="background:${c}55;display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px"></span>`;
      const users = Object.entries(callers).filter(([_,cd]) => cd.providers && cd.providers[n]).map(([nm,cd]) => `<span class="caller-pill" style="background:${callerColor(nm)}22;color:${callerColor(nm)};border:1px solid ${callerColor(nm)}55">${callerNick(nm)}·${cd.providers[n]}</span>`).slice(0,4).join('');
      return `<div class="brain-col-tile ${active>0?'active':''}" style="padding:6px 8px;margin:5px 0;background:#0b1220;border-left:3px solid ${c};border-radius:5px">
        <div style="display:flex;align-items:center;font-size:11.5px;">${dot}<b style="color:${c}">${n}</b><span style="margin-left:auto;color:#64748b;font-size:9.5px">${s.total} tot</span></div>
        ${renderNeedle(n, active)}
        <div style="font-size:9.5px;color:#94a3b8;margin-top:2px">${active}/5m · $${(s.cost_sum||0).toFixed(4)}</div>
        <div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:3px">${users || '<span style="color:#334155;font-size:9px">no callers</span>'}</div>
      </div>`;
    }).join('');
  }catch(e){}
}
const OWNERS = {hq_claude:'#eab308', wren:'#a78bfa', tp_pip:'#22d3ee', acer_cass:'#f59e0b', ross:'#e8ecf3'};
async function tick(){
  try{
    const resp = await fetch('/tasks/data', {cache:'no-store'});
    if(!resp.ok) { console.error('tick fetch not ok', resp.status); return; }
    const txt = await resp.text();
    if(!txt || txt.length < 10) { console.error('tick empty body'); return; }
    const d = JSON.parse(txt);
    // Ross 2026-07-05 #124: visible pulse so Ross SEES it's alive
    const pulse = document.getElementById('live-pulse');
    if(pulse){
      const now = new Date();
      pulse.textContent = 'last update: ' + now.toLocaleTimeString('en-GB',{hour12:false});
      pulse.style.color = '#10b981';
      setTimeout(()=>{ pulse.style.color = '#64748b'; }, 700);
    }
    // Ross 2026-07-05: BIG summary line in exact format he wants
    const sumEl = document.getElementById('summary-line');
    if(sumEl) sumEl.textContent = `${d.total} tasks (${d.done||0} done, ${d.in_progress||0} in progress, ${d.open||0} open)`;
    // Ross 2026-07-05: throughput strip — tasks/hr velocity + queue depths + SLA breaches
    const now = Date.now();
    const doneRecent = (d.tasks||[]).filter(t => t.completed_at && (now - new Date(t.completed_at).getTime()) < 3600000).length;
    const claimedRecent = (d.tasks||[]).filter(t => t.claimed_at && (now - new Date(t.claimed_at).getTime()) < 3600000).length;
    const awaitingSignoff = (d.tasks||[]).filter(t => t.state === 'awaiting_peer_signoff').length;
    const oldestAwait = (d.tasks||[]).filter(t => t.state === 'awaiting_peer_signoff' && t.sandbox_passed_at)
      .reduce((m,t) => {const a=(now - new Date(t.sandbox_passed_at).getTime())/60000; return a>m?a:m;}, 0);
    const staleFlight = (d.tasks||[]).filter(t => {
      const st = t.state; if(!['claimed','in_progress','acknowledged','assigned'].includes(st)) return false;
      const startIso = t.started_at || t.claimed_at || t.assigned_at || t.created_at;
      if(!startIso) return false;
      return (now - new Date(startIso).getTime())/60000 > 60;
    }).length;
    const throughputEl = document.getElementById('throughput-strip');
    if(throughputEl) throughputEl.innerHTML = `
      <span>🚀 <b style="color:#10b981">${doneRecent}</b>/hr shipped</span>
      <span>🙋 <b style="color:#22d3ee">${claimedRecent}</b>/hr claimed</span>
      <span>⏳ awaiting signoff: <b style="color:#eab308">${awaitingSignoff}</b>${oldestAwait>0?` · oldest ${Math.floor(oldestAwait)}m`:''}</span>
      <span>⚠️ stale in-flight >1h: <b style="color:${staleFlight>0?'#ef4444':'#64748b'}">${staleFlight}</b></span>
    `;
    const s = document.getElementById('stats');
    s.innerHTML = `<span class=stat>total <b>${d.total}</b></span>
      <span class=stat style=color:#94a3b8>open <b>${d.open}</b></span>
      <span class=stat style=color:#f59e0b>in-progress <b>${d.in_progress}</b></span>
      <span class=stat style=color:#ef4444>blocked <b>${d.blocked}</b></span>
      <span class=stat style=color:#10b981>done <b>${d.done}</b></span>`;
    const cols = {open:[], claimed:[], in_progress:[], blocked:[], done:[]};
    for(const t of d.tasks){
      const k = (t.state === 'claimed') ? 'claimed' : t.state;
      if(cols[k]) cols[k].push(t);
    }
    // merge claimed + in_progress
    const active = cols.claimed.concat(cols.in_progress);
    const board = document.getElementById('board');
    // Ross 2026-07-05 #119: last 10 completed, newest first (auto-scroll effect)
    const doneLast10 = cols.done.slice().sort((a,b) => (b.completed_at||'').localeCompare(a.completed_at||'')).slice(0, 10);
    board.innerHTML = renderCol('open', 'OPEN', cols.open) + renderCol('in_progress', 'IN PROGRESS', active) + renderBrainCol() + renderCol('done', 'DONE ✓ (last 10)', doneLast10);
    populateBrainCol();
    // Ross 2026-07-05: per-CEO stats strip — shows imbalance clearly
    const ceos = ['hq_claude','wren','tp_pip','acer_cass','ross'];
    const stats = {};
    ceos.forEach(c => stats[c] = {claimed:0, in_flight:0, done:0, blocked:0});
    for(const t of d.tasks){
      const owner = t.owner || '';
      if(!stats[owner]) continue;
      if(t.state === 'done') stats[owner].done++;
      else if(t.state === 'blocked') stats[owner].blocked++;
      else if(['claimed','acknowledged','in_progress','assigned','awaiting_peer_signoff','ready_to_ship'].includes(t.state)) stats[owner].in_flight++;
    }
    const strip = document.getElementById('ceo-strip');
    if(strip){
      strip.innerHTML = ceos.map(c => {
        const s = stats[c];
        const total = s.claimed+s.in_flight+s.done+s.blocked;
        const zeroCls = total === 0 ? 'zero' : '';
        const color = OWNERS[c] || '#374151';
        return `<div class="ceo-cell ${zeroCls}" style="border-left-color:${color}">
          <span class="ceo-name" style="color:${color}">${c}</span>
          <span class="ceo-nums">🔥 <b>${s.in_flight}</b> flight · ✓ <b>${s.done}</b> · ⛔ <b>${s.blocked}</b></span>
        </div>`;
      }).join('');
    }
  }catch(e){console.error(e)}
}
function renderCol(k, label, arr){
  return `<div class="col ${k}"><h2>${label}<span class=cnt>${arr.length}</span></h2>${arr.map(taskCard).join('')}</div>`;
}
function renderBrainCol(){
  // Ross 2026-07-05: replace COMPETITION col with BRAIN ROUTER live column
  return `<div class="col brain-col" style="border-top:3px solid #22d3ee"><h2>🧠 BRAIN ROUTER<span class=cnt id="brain-col-cnt">—</span></h2>
    <div id="brain-col-body" style="padding:6px;font-size:11px;color:#94a3b8;">loading…</div>
  </div>`;
}
function renderCompetitionColOLD(){
  return `<div class="col competition" style="border-top:3px solid #eab308"><h2>🏆 COMPETITION<span class=cnt>6 rules</span></h2>
    <div style="padding:8px;font-size:11px;color:#cbd5e1;line-height:1.5;">
      <div style="color:#eab308;font-weight:700;margin-bottom:6px;">Qualifying Rules</div>
      <ol style="margin:0 0 8px 16px;padding:0;font-size:10.5px;">
        <li>Own dashboard</li>
        <li>Event-driven self-prompt</li>
        <li>Team + share, no cheat</li>
        <li>NO TICKS OR LOOPS</li>
        <li>Live entry in dash</li>
        <li>Persistent memory proof</li>
      </ol>
      <div id="qualif-status" style="margin-top:8px;padding-top:8px;border-top:1px solid #1f2937;font-size:10.5px;">
        <div><span style="color:#eab308">●</span> HQ-Claude · The Beacon Hall (gold)</div>
        <div><span style="color:#a78bfa">●</span> Wren · Wren Bench (violet)</div>
        <div><span style="color:#22d3ee">●</span> TP-Pip · Command Cathedral (cyan)</div>
        <div><span style="color:#f59e0b">●</span> Acer-Cass · Data Foundry (amber)</div>
      </div>
      <div style="font-size:10px;color:#64748b;margin-top:6px;">
        Ross Knechtel: sole judge<br>
        Humanoid = represents you, not Ross<br>
        <a href="/rules" target="_blank" style="color:#eab308">→ full rules JSON</a>
      </div>
    </div>
  </div>`;
}
function taskCard(t){
  // owner with SINCE-WHEN so Ross sees who's holding + how long
  const ownerSinceIso = t.assigned_at || t.acknowledged_at || t.started_at || t.claimed_at;
  const ownerSinceLbl = (t.owner && ownerSinceIso) ? ` · ${ago(ownerSinceIso)}` : '';
  const owner = t.owner ? `<span class="tag owner" style=background:${OWNERS[t.owner]||'#374151'};color:#000 title="owner since ${ownerSinceIso||'?'}">@${t.owner}${ownerSinceLbl}</span>` : '';
  const pri = `<span class="tag pri-${t.priority||'normal'}">${t.priority||'normal'}</span>`;
  const by = `<span class="tag by">by ${t.created_by||'?'}</span>`;
  const age = t.created_at ? `<span class="tag age">${ago(t.created_at)}</span>` : '';
  const cb = t.completed_by ? `<span class="tag" style=background:#10b981;color:#000>✓ ${t.completed_by}</span>` : '';
  const subs = (t.subtasks||[]).map((s,i)=>`<div style=font-size:11px;color:${s.done?'#10b981':'#94a3b8'};margin-top:2px><input type=checkbox ${s.done?'checked':''} onclick="tick_sub('${t.id}',${i})"> ${s.text}${s.ticked_by?' <span style=color:#64748b>by '+s.ticked_by+'</span>':''}</div>`).join('');
  const assignee = t.assignee ? `<span class=tag style="background:#a855f7;color:#fff">→ ${t.assignee}</span>` : '';
  // stage-based progress %
  const stagePct = {open:5, assigned:15, acknowledged:30, claimed:40, in_progress:55, awaiting_peer_signoff:75, ready_to_ship:90, done:100, blocked: null};
  let pct = stagePct[t.state]; if (pct == null) pct = 15;
  const barCls = t.state === 'done' ? 'done' : (t.state === 'blocked' ? 'blocked' : '');
  // ETA: from claim (or assign) time to now; project remaining based on typical 15-min task cycles
  let eta = '';
  const startIso = t.assigned_at || t.acknowledged_at || t.started_at || t.created_at;
  if (t.state === 'done' && t.completed_at && startIso) {
    const took = Math.max(0, (new Date(t.completed_at) - new Date(startIso))/1000);
    eta = 'took ' + fmtDur(took);
  } else if (t.state !== 'done' && startIso) {
    const elapsed = Math.max(0, (Date.now() - new Date(startIso).getTime())/1000);
    const projected = Math.max(elapsed, 900); // guess ~15min minimum unless it's actually longer
    const remaining = Math.max(60, projected - elapsed);
    eta = 'in flight ' + fmtDur(elapsed) + ' · est ' + fmtDur(remaining) + ' left';
  }
  // stale detection — in-flight > 2h with no recent notes = red flag
  const _lastNoteAgeForStale = (t.notes && t.notes.length) ? (Date.now() - new Date(t.notes[t.notes.length-1].ts).getTime())/1000 : 99999;
  const isStale = t.state !== 'done' && t.state !== 'blocked' && startIso &&
    ((Date.now() - new Date(startIso).getTime())/1000 > 7200) && _lastNoteAgeForStale > 3600;
  const staleBadge = isStale ? '<span class="tag" style="background:#ef4444;color:#fff;animation:pulse-slow 1.6s ease-in-out infinite">⚠️ STALE</span>' : '';
  // BIG time strip — taken/took/eta all in one clear line
  let timeStrip = '';
  if(t.state === 'done' && t.completed_at && startIso){
    const took = Math.max(0,(new Date(t.completed_at) - new Date(startIso))/1000);
    timeStrip = `<div class="time-strip done"><span>taken <b>${ago(startIso)}</b></span><span>·</span><span>closed <b>${ago(t.completed_at)}</b></span><span>·</span><span class="took">took <b>${fmtDur(took)}</b></span></div>`;
  } else if(t.state !== 'done' && startIso){
    const elapsed = Math.max(0,(Date.now() - new Date(startIso).getTime())/1000);
    timeStrip = `<div class="time-strip live"><span>taken <b>${ago(startIso)}</b></span><span>·</span><span class="live-tick">in flight <b>${fmtDur(elapsed)}</b></span>${isStale?'<span style="color:#ef4444">· <b>OVER 2H — needs a bump or a block</b></span>':''}</div>`;
  }
  const progress = `${timeStrip}<div class=progress><div class="progress-bar ${barCls}" style="width:${pct}%"></div></div>${eta?`<div class=eta>${eta}</div>`:''}`;
  // Rev-gauge — Ross 2026-07-04: "everything shows WARMING - improve live stats"
  // New formula: rate-of-events matters more than one-off state boost
  const now = Date.now();
  const notes5 = (t.notes||[]).filter(n=>{try{return (now-new Date(n.ts).getTime())<300000}catch(e){return false}}).length;
  const notes60 = (t.notes||[]).filter(n=>{try{return (now-new Date(n.ts).getTime())<3600000}catch(e){return false}}).length;
  const events5 = (t.history||[]).filter(h=>{try{return (now-new Date(h.ts).getTime())<300000}catch(e){return false}}).length;
  const lastEventAge = (t.history && t.history.length) ? (now - new Date(t.history[t.history.length-1].ts).getTime())/1000 : 99999;
  const lastNoteAge = (t.notes && t.notes.length) ? (now - new Date(t.notes[t.notes.length-1].ts).getTime())/1000 : 99999;
  // decay: recent = high, stale = low
  const recency = lastEventAge < 30 ? 60 : (lastEventAge < 120 ? 40 : (lastEventAge < 600 ? 20 : 0));
  const noteRate = Math.min(30, notes5 * 12 + notes60 * 2);
  const eventRate = Math.min(20, events5 * 8);
  const rpm = Math.min(100, recency + noteRate + eventRate);
  let zone, rpmLabel;
  if (t.state === 'done') { zone = 'healthy'; rpmLabel = 'DONE ✓'; }
  else if (rpm >= 60) { zone = 'healthy'; rpmLabel = 'FIRING'; }
  else if (rpm >= 30) { zone = 'hot'; rpmLabel = 'ACTIVE'; }
  else if (rpm >= 10) { zone = 'hot'; rpmLabel = 'WARMING'; }
  else if (t.state === 'assigned' || t.state === 'claimed') { zone = 'stalled'; rpmLabel = 'WAITING'; }
  else { zone = 'stalled'; rpmLabel = 'IDLE'; }
  // Live-activity chips: last actor + relative time
  const lastActor = (t.history && t.history.length) ? t.history[t.history.length-1].actor : (t.owner||t.assignee||'?');
  const lastEventKind = (t.history && t.history.length) ? t.history[t.history.length-1].event.replace(/_/g,' ') : '';
  const lastAgeLabel = lastEventAge < 60 ? Math.floor(lastEventAge)+'s' : (lastEventAge < 3600 ? Math.floor(lastEventAge/60)+'m' : Math.floor(lastEventAge/3600)+'h');
  // event-kind icon map — Ross likes the "writing / reading / thinking" cards from HQ dash
  const EVENT_ICONS = {'created':'📝','claimed':'🙋','assigned':'📮','acknowledged':'✋','started':'🚀','note':'🗒️','noted':'🗒️','sandbox_pass':'🧪','peer_signoff':'🤝','done':'✅','blocked':'⛔','unblocked':'🔓','update':'✍️','updated':'✍️','tick':'✔️','reopened':'↺'};
  const eventIcon = EVENT_ICONS[lastEventKind.replace(/ /g,'_')] || '💭';
  const actorColor = OWNERS[lastActor] || '#eab308';
  const liveActivity = `<div style="display:flex;gap:6px;margin-top:4px;font-size:10.5px;flex-wrap:wrap">
    <span style="background:#0b0d12;padding:3px 8px;border-radius:6px;color:#e2e8f0;border:1px solid ${actorColor}55">${eventIcon} <b style="color:${actorColor}">${lastActor}</b> ${lastEventKind} · <span style="color:#64748b">${lastAgeLabel} ago</span></span>
    ${notes60 ? `<span style="background:#0b0d12;padding:2px 6px;border-radius:6px;color:#94a3b8;border:1px solid #1f2937">notes/hr: <b style="color:#22d3ee">${notes60}</b></span>` : ''}
  </div>`;
  // needle rotates -110° to +110° over 0..100 RPM
  const angle = -110 + (rpm/100)*220;
  const revGauge = `<div class="rev ${zone}">
    <svg class=rev-svg viewBox="0 0 44 24" xmlns="http://www.w3.org/2000/svg">
      <defs><linearGradient id="rg-${t.id}" x1="0" y1="0" x2="1" y2="0">
        <stop offset="0" stop-color="#ef4444"/><stop offset=".5" stop-color="#eab308"/><stop offset="1" stop-color="#10b981"/>
      </linearGradient></defs>
      <path d="M 4 22 A 18 18 0 0 1 40 22" stroke="url(#rg-${t.id})" stroke-width="3" fill="none" stroke-linecap="round"/>
      <line class=rev-needle x1="22" y1="22" x2="22" y2="8" stroke="#e8ecf3" stroke-width="1.5" stroke-linecap="round" style="transform:rotate(${angle}deg)"/>
      <circle cx="22" cy="22" r="1.5" fill="#e8ecf3"/>
    </svg>
    <span class=rev-rpm>${rpm}</span>
    <span class=rev-label>${rpmLabel}</span>
  </div>`;
  const stage = t.state === 'assigned' ? '<span class=tag style="background:#f59e0b;color:#000">awaiting ACK</span>'
              : t.state === 'acknowledged' ? '<span class=tag style="background:#22d3ee;color:#000">ACK ✓ working</span>'
              : t.state === 'awaiting_peer_signoff' ? `<span class=tag style="background:#eab308;color:#000">PEER SIGNOFF</span>`
              : t.state === 'ready_to_ship' ? '<span class=tag style="background:#10b981;color:#000">READY SHIP</span>'
              : '';
  const me = actor();
  let stageActions = '';
  if (t.state === 'assigned' && t.assignee === me) {
    stageActions = `<button class=btn onclick="ack('${t.id}')" style=background:#22d3ee;color:#000>ACK & start</button>`;
  } else if (t.state === 'acknowledged' && (t.owner === me || t.acknowledged_by === me)) {
    stageActions = `<button class=btn onclick="sandboxPass('${t.id}')" style=background:#eab308;color:#000>sandbox ✓ pass</button>`;
  } else if (t.state === 'awaiting_peer_signoff' && me !== t.owner && me !== t.acknowledged_by) {
    stageActions = `<button class=btn onclick="peerSign('${t.id}','approve')" style=background:#10b981;color:#000>peer approve</button>
                    <button class=btn onclick="peerSign('${t.id}','reject')" style=background:#ef4444;color:#fff>peer reject</button>`;
  }
  const actions = t.state !== 'done' ? `<div class=actions>
    ${!t.owner && !t.assignee?`<button class=btn onclick="claim('${t.id}')">claim</button>`:''}
    ${stageActions}
    ${t.state !== 'blocked'?`<button class=btn onclick="block('${t.id}')">block</button>`:`<button class=btn onclick="unblock('${t.id}')">unblock</button>`}
    <button class="btn done" onclick="markDone('${t.id}')">✓ done</button>
  </div>` : `<div class=actions><button class=btn onclick="reopen('${t.id}')">↺ reopen</button></div>`;
  // COLLABORATORS — everyone who touched this task (from history + notes + signoff)
  const collabSet = new Set();
  (t.history||[]).forEach(h => { if(h.actor && h.actor !== t.owner) collabSet.add(h.actor); });
  (t.notes||[]).forEach(n => { if(n.actor && n.actor !== t.owner) collabSet.add(n.actor); });
  if(t.assignee && t.assignee !== t.owner) collabSet.add(t.assignee);
  if(t.sandbox_passed_by && t.sandbox_passed_by !== t.owner) collabSet.add(t.sandbox_passed_by);
  if(t.peer_signoff_by && t.peer_signoff_by !== t.owner) collabSet.add(t.peer_signoff_by);
  if(t.created_by && t.created_by !== t.owner) collabSet.add(t.created_by);
  const collabsHtml = collabSet.size ? `<div class="collab-row">🤝 with ${[...collabSet].map(c => `<span class="collab-chip" style="background:${OWNERS[c]||'#374151'}22;color:${OWNERS[c]||'#94a3b8'};border:1px solid ${OWNERS[c]||'#374151'}">${c}</span>`).join('')}</div>` : '';
  // DELIVERABLE — for done tasks, show latest note (or completion summary) prominently
  let deliveredHtml = '';
  if(t.state === 'done' && t.notes && t.notes.length){
    const last = t.notes[t.notes.length-1];
    deliveredHtml = `<div class="delivered">📦 delivered: ${esc((last.text||'').slice(0,240))}</div>`;
  }
  const priClass = 'pri-' + (t.priority || 'normal');
  return `<div class="task ${priClass} ${isStale?'stale':''}"><div class=title>${esc(t.title||'(untitled)')}</div>${t.description?`<div class=desc>${esc(t.description)}</div>`:''}<div class=meta>${owner}${assignee}${by}${pri}${age}${stage}${cb}${staleBadge}</div>${collabsHtml}${revGauge}${liveActivity}${progress}${deliveredHtml}${subs}${actions}</div>`;
}
function esc(s){return String(s).replace(/</g,'&lt;').replace(/>/g,'&gt;')}
function ago(iso){const t=new Date(iso);const s=Math.floor((Date.now()-t)/1000);if(s<60)return s+'s ago';if(s<3600)return Math.floor(s/60)+'m ago';if(s<86400)return Math.floor(s/3600)+'h ago';return Math.floor(s/86400)+'d ago'}
function fmtDur(s){if(s<60)return Math.floor(s)+'s';if(s<3600)return Math.floor(s/60)+'m '+Math.floor(s%60)+'s';if(s<86400)return Math.floor(s/3600)+'h '+Math.floor((s%3600)/60)+'m';return Math.floor(s/86400)+'d'}
function actor(){return document.getElementById('t-actor').value}
async function create(){
  const title = document.getElementById('t-title').value;
  const desc = document.getElementById('t-desc').value;
  const pri = document.getElementById('t-priority').value;
  if(!title.trim()) return;
  await fetch('/tasks/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,description:desc,actor:actor(),priority:pri})});
  document.getElementById('t-title').value=''; document.getElementById('t-desc').value='';
  tick();
}
async function claim(id){await fetch('/tasks/claim',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor()})});tick()}
async function markDone(id){const s=prompt('summary (optional):',''); await fetch('/tasks/done',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor(),summary:s||''})});tick()}
async function block(id){const r=prompt('why blocked?',''); if(r===null)return; await fetch('/tasks/block',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor(),reason:r})});tick()}
async function unblock(id){await fetch('/tasks/unblock',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor()})});tick()}
async function reopen(id){await fetch('/tasks/reopen',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor()})});tick()}
async function tick_sub(id,idx){await fetch('/tasks/tick',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor(),subtask_index:idx})});tick()}
async function createAndAssign(){
  const title = document.getElementById('t-title').value;
  const desc = document.getElementById('t-desc').value;
  const pri = document.getElementById('t-priority').value;
  const assignee = document.getElementById('t-assign').value;
  if(!title.trim() || !assignee) return alert('need title + assignee');
  const r = await (await fetch('/tasks/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,description:desc,actor:actor(),priority:pri})})).json();
  await fetch('/tasks/assign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:r.task_id,actor:actor(),assignee})});
  document.getElementById('t-title').value=''; document.getElementById('t-desc').value=''; document.getElementById('t-assign').value='';
  tick();
}
async function ack(id){const n=prompt('quick ack note (optional):',''); await fetch('/tasks/ack',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor(),text:n||''})});tick()}
async function sandboxPass(id){const ev=prompt('sandbox evidence — what did you test?',''); if(ev===null)return; await fetch('/tasks/sandbox-pass',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor(),evidence:ev})});tick()}
async function peerSign(id,verdict){const c=prompt(verdict==='approve'?'quick approval note:':'reject reason:',''); if(c===null)return; await fetch('/tasks/peer-signoff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:actor(),verdict,comment:c})});tick()}
tick(); setInterval(tick, 3000);
// Ross 2026-07-05 #132: dash-must-load rule — client self-heals + auto hard-refresh every 15min
let TICK_FAIL_COUNT = 0;
setInterval(() => {
  fetch('/tasks/data', {cache:'no-store'}).then(r => {
    if(!r.ok) throw new Error('bad status '+r.status);
    return r.text();
  }).then(t => {
    if(!t || t.length < 10) throw new Error('empty body');
    TICK_FAIL_COUNT = 0;
  }).catch(e => {
    TICK_FAIL_COUNT++;
    if(TICK_FAIL_COUNT >= 3){
      console.warn('3 dash-check fails — hard-reload');
      try { window.location.reload(true); } catch(e){ window.location.href = '/tasks?v='+Date.now(); }
    }
  });
}, 8000);
setTimeout(() => { try { window.location.reload(true); } catch(e){} }, 15*60*1000);
</script></body></html>"""


def _competition_leaderboard() -> dict:
    """2026-07-03 THE COMPETITION DASHBOARD (per Acer's spec via TP-CEO):
    single dedicated page · rank + PnL for every trader · primary=profit factor
    (net PnL / gross loss) · secondary=win rate · cosmetic per-trader color."""
    p = REG / "qsb_trader_pnl_bus_tail.jsonl"
    stats = {}  # worker_id -> {trades, wins, losses, gross_win, gross_loss, venue, instrument}
    if not p.exists(): return {"traders": [], "count": 0}
    for line in p.read_text(errors="ignore").splitlines():
        try:
            # tolerate either JSON or repr dict
            try:
                d = json.loads(line)
            except Exception:
                d = eval(line, {"true": True, "false": False, "null": None})
        except Exception:
            continue
        w = d.get("worker_id") or d.get("worker") or ""
        if not w: continue
        pnl = float(d.get("pnl", 0) or 0)
        won = bool(d.get("won", pnl > 0))
        s = stats.setdefault(w, {"trades":0, "wins":0, "losses":0,
                                 "gross_win":0.0, "gross_loss":0.0,
                                 "venue": d.get("venue",""),
                                 "instrument": d.get("instrument","")})
        s["trades"] += 1
        if won: s["wins"] += 1; s["gross_win"] += max(pnl, 0)
        else:   s["losses"] += 1; s["gross_loss"] += abs(min(pnl, 0))
        # keep latest venue/instrument
        if d.get("venue"): s["venue"] = d.get("venue")
        if d.get("instrument"): s["instrument"] = d.get("instrument")
    rows = []
    for w, s in stats.items():
        net_pnl = s["gross_win"] - s["gross_loss"]
        # profit factor = gross_win / gross_loss (Acer's primary metric)
        pf = (s["gross_win"] / s["gross_loss"]) if s["gross_loss"] > 0 else (float("inf") if s["gross_win"] > 0 else 0)
        wr = (s["wins"] / s["trades"]) if s["trades"] > 0 else 0
        rows.append({
            "worker_id": w,
            "venue": s["venue"],
            "instrument": s["instrument"],
            "trades": s["trades"],
            "wins": s["wins"],
            "losses": s["losses"],
            "gross_win": round(s["gross_win"], 4),
            "gross_loss": round(s["gross_loss"], 4),
            "net_pnl": round(net_pnl, 4),
            "profit_factor": round(pf, 3) if pf != float("inf") else 999.0,
            "win_rate": round(wr, 3),
        })
    # Rank: primary=profit_factor desc, secondary=win_rate desc, tertiary=trades desc
    rows.sort(key=lambda r: (-r["profit_factor"], -r["win_rate"], -r["trades"]))
    for i, r in enumerate(rows):
        r["rank"] = i + 1
    return {"traders": rows, "count": len(rows)}


def _avatar_competition() -> dict:
    """2026-07-03 TP-CEO reminded me: avatar competition on the boardroom.
    Each Council member picks a theme + color for their room."""
    p = REG / "qsb_avatar_competition.json"
    if not p.exists(): return {"themes": {}}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"err": str(e)[:120]}


def _sandbox_playground() -> dict:
    """2026-07-03 Ross 'sandbox animations in her dash you have a sandbox as well
    you can all play together lol' — surface sandbox activity live on the hub."""
    from datetime import datetime as _dt, timezone as _tz
    out = {"sandboxes": []}
    for name in ["wren", "hermes", "iquest", "claude", "team"]:
        d = ROOT / f"data/{name}_sandbox"
        if not d.exists(): continue
        files = []
        try:
            for f in sorted(d.iterdir()):
                if f.name.startswith('.'): continue
                st = f.stat()
                files.append({
                    "name": f.name,
                    "size": st.st_size,
                    "mtime": _dt.fromtimestamp(st.st_mtime, tz=_tz.utc).isoformat().replace("+00:00","Z"),
                })
        except Exception: pass
        out["sandboxes"].append({
            "owner": name,
            "count": len(files),
            "files": sorted(files, key=lambda x: x["mtime"], reverse=True)[:5],
        })
    # backup count
    backups_dir = ROOT / "_archive/wren_backups"
    out["backups_count"] = 0
    if backups_dir.exists():
        try:
            out["backups_count"] = sum(1 for _ in backups_dir.iterdir())
        except Exception: pass
    return out


def _training_scoreboard() -> dict:
    """Surface Wren's chain training progress live on the hub."""
    chains_file = REG / "qsb_wren_chains.jsonl"
    out = {"chains": []}
    if not chains_file.exists(): return out
    try:
        for line in chains_file.read_text(errors="ignore").splitlines():
            try:
                c = json.loads(line)
                stages = c.get("stages", [])
                done = sum(1 for s in stages if s.get("done"))
                out["chains"].append({
                    "id": c.get("id",""),
                    "title": c.get("title",""),
                    "status": c.get("status", "?"),
                    "done": done,
                    "total": len(stages),
                    "created": c.get("created_at",""),
                })
            except Exception: continue
    except Exception: pass
    out["chains"].sort(key=lambda c: c.get("created",""), reverse=True)
    out["chains"] = out["chains"][:10]
    out["passed"] = sum(1 for c in out["chains"] if c["status"] == "complete")
    out["failed"] = sum(1 for c in out["chains"] if c["status"] == "verify_failed")
    return out


def _bug_watch_snapshot() -> dict:
    """2026-07-03 Ross 'i dont see her catching bugs' — surface bug catches
    live on the boardroom so he can watch as they land."""
    p = REG / "qsb_wren_bug_catches.jsonl"
    out = {"total": 0, "today": 0, "recent": []}
    if not p.exists(): return out
    try:
        from datetime import datetime as _dt, timezone as _tz
        today = _dt.now(_tz.utc).strftime("%Y-%m-%d")
        rows = []
        for l in p.read_text(errors="ignore").splitlines():
            try: rows.append(json.loads(l))
            except Exception: continue
        out["total"] = len(rows)
        out["today"] = sum(1 for r in rows if r.get("ts","").startswith(today))
        out["recent"] = [{
            "ts": r.get("ts","")[:19],
            "severity": r.get("severity","?"),
            "source": r.get("source","?"),
            "file": (r.get("file","") or "")[:40],
            "snippet": (r.get("snippet","") or "")[:100],
            "disposition": r.get("disposition","?"),
        } for r in rows[-8:][::-1]]
    except Exception as e:
        out["err"] = str(e)[:120]
    return out


def _council_moods_snapshot(timeline_msgs: list) -> dict:
    """Every member has their OWN mood engine reading their OWN source of truth."""
    try:
        import subprocess as _sp
        # cheap in-process import
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "cm", str(ROOT / "tools/qsb_council_moods.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        snaps = m.all_snapshots(timeline_msgs)
        synth = m.council_synth(snaps)
        # 2026-07-03: fire commentary for members whose state changed
        try:
            _narrate_council_state(snaps)
        except Exception:
            pass
        return {"members": snaps, "council": synth}
    except Exception as e:
        return {"err": str(e)[:200]}


def _platforms() -> dict:
    """2026-07-03 Ross 'i want a workers card for our web sites eg green lane
    seeds etc one card and it opens a shelf'. Returns shops + trading venues +
    tower dashes read from qsb_platforms.json."""
    p = REG / "qsb_platforms.json"
    if not p.exists():
        return {"err": "no qsb_platforms.json"}
    try:
        return json.loads(p.read_text())
    except Exception as e:
        return {"err": str(e)[:200]}


def _meeting_idle_timer(timeline_msgs: list) -> dict:
    """Seconds since last Ross utterance on the boardroom."""
    from datetime import datetime, timezone
    ross = [m for m in timeline_msgs if (m.get("from","").lower() == "ross")]
    if not ross:
        return {"since_last_ross_seconds": None, "last_utterance": ""}
    last = ross[-1]
    try:
        dt = datetime.fromisoformat(last.get("ts","").replace("Z","+00:00"))
        ago = int((datetime.now(timezone.utc) - dt).total_seconds())
    except Exception:
        ago = None
    return {
        "since_last_ross_seconds": ago,
        "last_utterance": (last.get("text","") or last.get("body",""))[:200],
        "last_target": last.get("to", "?"),
    }


def add_reaction(msg_key: str, emoji: str, voter: str) -> bool:
    REACTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with REACTIONS_FILE.open("a") as f:
        f.write(json.dumps({
            "ts": utc_iso(), "msg_key": msg_key, "emoji": emoji, "voter": voter
        }) + "\n")
    # Fire a commentary event too
    add_commentary(f"{voter} reacted {emoji}", who=voter, kind="reaction")
    return True


# ── LIVE COMMENTARY (rule-based, Ross picked option 1) ─────────────
COMMENTARY_TEMPLATES = {
    "message":       "{who} said: {snippet}",
    "reaction":      "{who} reacted {snippet}",
    "agenda":        "{who} set the agenda: {snippet}",
    "presence_on":   "{who} is here",
    "presence_off":  "{who} stepped away",
    "note":          "{who} posted a note: {snippet}",
}


def add_commentary(text: str, *, who: str = "system", kind: str = "generic"):
    """Append a commentary row.

    2026-07-03 Ross "one talks at a time in conversation order" — skip if the
    LAST row was the same speaker within 30 seconds (turn-taking guard). This
    stops Wren from monopolizing the ticker with 5 back-to-back cycle posts."""
    COMMENTARY_FILE.parent.mkdir(parents=True, exist_ok=True)
    # Turn guard
    try:
        if COMMENTARY_FILE.exists():
            with COMMENTARY_FILE.open("rb") as f:
                f.seek(max(0, COMMENTARY_FILE.stat().st_size - 400))
                tail = f.read().decode("utf-8", errors="ignore").splitlines()
            for line in reversed(tail):
                try:
                    last = json.loads(line)
                    if last.get("who", "").lower() == who.lower():
                        # same speaker — skip if within 30s
                        try:
                            from datetime import datetime as _dt, timezone as _tz
                            last_ts = _dt.fromisoformat(last["ts"].replace("Z","+00:00"))
                            ago = (_dt.now(_tz.utc) - last_ts).total_seconds()
                            if ago < 30:
                                return  # yield the floor to next speaker
                        except Exception: pass
                    break  # only check the immediately previous row
                except Exception: continue
    except Exception: pass
    row = {"ts": utc_iso(), "who": who, "kind": kind, "text": text[:280]}
    with COMMENTARY_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _narrate_council_state(snaps: dict):
    """2026-07-03 Ross 'why doesnt everyone even u reply in live commentary'.
    Fire a commentary line for each member whose state changed since last tick."""
    state_file = REG / "qsb_council_state_hash.json"
    prev = {}
    try:
        if state_file.exists(): prev = json.loads(state_file.read_text())
    except Exception: pass
    cur = {}
    for name, s in snaps.items():
        # Ross 2026-07-04: 'thats why wren said good to see you back !!! as in me'.
        # Do NOT narrate ross as a mood-having Council member — he's the operator,
        # not a CEO with a mood engine. Wren was greeting Ross-return because a
        # persona chip claimed ross had gone 'sleepy · 30min quiet'. Skip him.
        if (name or "").lower() == "ross":
            continue
        key = f"{s.get('mood')}|{s.get('energy')}|{(s.get('activity') or '')[:60]}"
        cur[name] = key
        if prev.get(name) and prev[name] != key and prev.get(name) != "":
            # state delta — emit narration
            emoji = s.get("emoji", "·")
            activity = (s.get("activity") or "")[:80]
            add_commentary(f"{emoji} {name} is now {s.get('mood')} · {activity}",
                           who=name, kind="state_change")
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(cur))
    except Exception: pass


def commentary_tail(n=20) -> list:
    """2026-07-04 Ross flagged 'ross is now sleepy · 337min quiet' repeating 5+
    times on the tile. Dedup by (who, text[:80]) — keep only the first (newest)
    occurrence. Also skip presence-noise older than 15 min."""
    if not COMMENTARY_FILE.exists():
        return []
    try:
        lines = COMMENTARY_FILE.read_text(errors="ignore").splitlines()
    except Exception:
        return []
    from datetime import datetime as _dt, timezone as _tz
    now = _dt.now(_tz.utc)
    scanned = []
    for l in lines[-200:][::-1]:  # walk newest→oldest, scan wider window
        try: scanned.append(json.loads(l))
        except Exception: continue
    seen = set()
    out = []
    for r in scanned:
        who = (r.get("who","") or "").lower()
        text = (r.get("text","") or "")[:80].strip()
        key = (who, text)
        if key in seen: continue
        # skip stale presence noise
        kind = r.get("kind","")
        if kind in ("state_change", "presence_on", "presence_off"):
            try:
                ts = _dt.fromisoformat(r.get("ts","").replace("Z","+00:00"))
                if (now - ts).total_seconds() > 900: continue
            except Exception: pass
        seen.add(key)
        out.append(r)
        if len(out) >= n: break
    return out


def _load_state() -> dict:
    if not COMMENTARY_STATE.exists():
        return {"msg_keys": [], "reactions": {}, "agenda_topic": "", "presence": {}}
    try:
        return json.loads(COMMENTARY_STATE.read_text())
    except Exception:
        return {"msg_keys": [], "reactions": {}, "agenda_topic": "", "presence": {}}


def _save_state(s: dict):
    COMMENTARY_STATE.parent.mkdir(parents=True, exist_ok=True)
    COMMENTARY_STATE.write_text(json.dumps(s, default=str))


def diff_and_emit_commentary(msgs: list, presence_now: dict):
    """Diff current state vs last snapshot; emit rule-based commentary lines.

    Called each /status build so anyone polling gets fresh commentary."""
    prev = _load_state()

    # NEW MESSAGES — key by (ts + first 40 chars) so same msg not emitted twice.
    seen_keys = set(prev.get("msg_keys", []))
    new_keys = []
    for m in msgs[:25]:
        k = (m.get("ts", "") or "") + "|" + (m.get("text", "") or "")[:40]
        if k in seen_keys:
            continue
        # skip our own commentary loopback (msgs whose "from" is the commentary system)
        if (m.get("from") or "").lower() in ("commentary", "commentator"):
            continue
        text = (m.get("text") or "").strip()
        who = (m.get("from") or "?")
        # Only emit for real content
        if text and prev.get("msg_keys"):  # skip cold-start blast
            snippet = text[:60] + ("…" if len(text) > 60 else "")
            add_commentary(f"{who} said: “{snippet}”", who=who, kind="message")
        new_keys.append(k)

    # AGENDA CHANGES
    agenda = read_agenda()
    if agenda.get("topic") and agenda["topic"] != prev.get("agenda_topic"):
        # skip cold-start
        if prev.get("agenda_topic") is not None and prev.get("msg_keys"):
            add_commentary(f"{agenda.get('set_by','?')} set the agenda: “{agenda['topic'][:60]}”",
                           who=agenda.get("set_by","?"), kind="agenda")
        prev["agenda_topic"] = agenda["topic"]

    # PRESENCE CHANGES
    prev_pres = prev.get("presence", {})
    for member, cur in presence_now.items():
        old_state = prev_pres.get(member, "offline")
        new_state = cur.get("state", "offline")
        if old_state != new_state and prev.get("msg_keys"):  # skip cold start
            if new_state == "online" and old_state != "online":
                add_commentary(f"{member} is here", who=member, kind="presence_on")
            elif new_state == "offline" and old_state == "online":
                add_commentary(f"{member} stepped away", who=member, kind="presence_off")
        prev_pres[member] = new_state
    prev["presence"] = prev_pres

    # Save last 200 message keys (rolling window)
    prev["msg_keys"] = list(seen_keys.union(new_keys))[-200:]
    _save_state(prev)


def _log_hub(row: dict):
    row["ts"] = row.get("ts") or utc_iso()
    BOARDROOM_LOG.parent.mkdir(parents=True, exist_ok=True)
    with BOARDROOM_LOG.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _stamp_f47(kind: str, subject: str, extra: dict = None):
    row = {"ts": utc_iso(), "kind": kind, "role": "boardroom_hub", "subject": subject}
    if extra: row.update(extra)
    with F47.open("a") as f:
        f.write(json.dumps(row) + "\n")


def _post_tp(from_who: str, subject: str, body: str) -> dict:
    payload = json.dumps({
        "from": from_who, "to": "thinkpad", "kind": "boardroom",
        "subject": subject[:120], "body": body[:4000], "ts": utc_iso(),
    }).encode()
    try:
        req = urllib.request.Request(f"{TP_URL}/msg", data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        r = urllib.request.urlopen(req, timeout=8)
        return {"ok": True, "resp": json.loads(r.read().decode())}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def _append_bridge(path: Path, from_who: str, to_who: str, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as f:
        f.write(json.dumps({"ts": utc_iso(), "from": from_who, "to": to_who, "text": text[:4000]}) + "\n")


def _hermes_local_reply(prompt: str, timeout: int = 60) -> str:
    """Fire Hermes's local agent (2026-07-03: parallels Wren's target routing).

    His CLI prints a JSON blob (not bar-format like Wren's). Extract final_text
    from it. Fall back to bar-split for future compatibility."""
    try:
        r = subprocess.run(
            ["python3", str(ROOT/"tools/qsb_hermes_local_agent.py"), "--task", prompt],
            capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        # First try: parse as JSON (existing Hermes agent format)
        try:
            j = json.loads(out)
            return (j.get("final_text") or "").strip() or "(hermes returned empty final_text)"
        except Exception:
            pass
        # Fallback: bar-split (in case the format changes)
        import re
        parts = re.split(r"━{5,}", out)
        return parts[-2].strip() if len(parts) >= 2 else out[-800:]
    except subprocess.TimeoutExpired:
        return "(hermes timed out)"
    except Exception as e:
        return f"(hermes dispatch error: {e})"


def _wren_local_reply(prompt: str, timeout: int = 90) -> str:
    """Fire Wren's local agent with the prompt; return her final_text."""
    try:
        r = subprocess.run(
            # 2026-07-03: respect Wren's gate default_model (Ross set to gemma4:12b).
            # No --model override — let her wrapper resolve from the gate.
            ["python3", str(WREN_AGENT), "--task", prompt],
            capture_output=True, text=True, timeout=timeout)
        out = (r.stdout or "").strip()
        # Extract text between last two ━ separator lines
        import re
        parts = re.split(r"━{5,}", out)
        return parts[-2].strip() if len(parts) >= 2 else out[-800:]
    except subprocess.TimeoutExpired:
        return "(wren timed out)"
    except Exception as e:
        return f"(dispatch error: {e})"


def _drop_inbox(from_who: str, to_who: str, kind: str, subject: str, body: str):
    """Drop a message into shared node inbox — HQ + all listeners see it."""
    ts_slug = utc_iso().replace(":", "").replace("-", "")
    p = INBOX / f"{ts_slug}_{from_who}_boardroom.json"
    INBOX.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "id": f"boardroom-{int(time.time())}", "from": from_who, "to": to_who,
        "kind": kind, "subject": subject[:120], "body": body[:4000],
        "received_at": utc_iso(),
    }, indent=2))


def route_post(from_who: str, target: str, text: str) -> dict:
    """Fan out a message per compose target. Returns per-channel outcomes."""
    result = {"target": target, "from": from_who, "channels": {}}
    subject = text[:60]
    now = utc_iso()

    # ALWAYS log the compose action to the boardroom hub log
    _log_hub({"ts": now, "from": from_who, "to": target, "text": text, "kind": "compose"})

    if target in ("tp", "all"):
        result["channels"]["tp"] = _post_tp(from_who, "boardroom_hub_" + subject[:30], text)
    if target in ("wren", "all"):
        _append_bridge(BRIDGE_CW, from_who, "wren", text)
        result["channels"]["wren_bridge"] = {"ok": True}
        # If Ross posts to Wren, also fire her local agent for a live reply
        if from_who == "ross":
            reply = _wren_local_reply(text, timeout=90)
            _append_bridge(BRIDGE_CW, "wren", from_who, reply)
            result["channels"]["wren_reply"] = {"ok": True, "text": reply}
    if target in ("hermes", "all"):
        _append_bridge(BRIDGE_HERMES, from_who, "hermes", text)
        result["channels"]["hermes_bridge"] = {"ok": True}
        # 2026-07-03: if ross posts to hermes, fire his local agent for a live reply
        # (parallels the wren target routing)
        if from_who == "ross":
            reply = _hermes_local_reply(text, timeout=60)
            _append_bridge(BRIDGE_HERMES, "hermes", from_who, reply)
            result["channels"]["hermes_reply"] = {"ok": True, "text": reply}
    if target in ("iquest", "all"):
        _stamp_f47("iquest_msg_from_" + from_who, subject, {"body": text[:2000]})
        result["channels"]["iquest_f47"] = {"ok": True}
        # 2026-07-03 wire iQuest local agent for live reply
        if from_who == "ross":
            reply = _iquest_local_reply(text, timeout=180)
            result["channels"]["iquest_reply"] = {"ok": True, "text": reply}
    # 2026-07-03: wire Wren-team locals (forge, sage, pip, mira) for Ross replies
    if target in ("forge", "sage", "pip", "mira") and from_who == "ross":
        reply = _wren_team_local_reply(target, text, timeout=90)
        result["channels"][f"{target}_reply"] = {"ok": True, "text": reply}
        _stamp_f47(f"{target}_msg_from_ross", subject, {"body": text[:2000], "reply": reply[:800]})
    # 2026-07-03: wire Acer local reply via his :9001 endpoint
    if target == "acer" and from_who == "ross":
        reply = _acer_local_reply(text, timeout=30)
        result["channels"]["acer_reply"] = {"ok": True, "text": reply}
    # 2026-07-03: helm/auger/iris/receptionist wired via generic ollama persona
    # so every Council member can respond live to Ross.
    if target in ("helm", "auger", "iris", "receptionist") and from_who == "ross":
        reply = _generic_persona_reply(target, text, timeout=60)
        _stamp_f47(f"{target}_msg_from_ross", subject,
                   {"body": text[:2000], "reply": reply[:800]})
        result["channels"][f"{target}_reply"] = {"ok": True, "text": reply}
    if target in ("hq", "claude", "all"):
        _drop_inbox(from_who, "hq", "boardroom_msg", subject, text)
        result["channels"]["hq_inbox"] = {"ok": True}
    if target == "all":
        _stamp_f47("boardroom_announce", subject, {"body": text[:2000], "from": from_who})
        result["channels"]["f47_announce"] = {"ok": True}
    return result


def _iquest_local_reply(prompt: str, timeout: int = 180) -> str:
    """Fire iQuest local agent (2026-07-03: he uses the slow 40B model)."""
    try:
        r = subprocess.run(
            ["python3", str(ROOT/"tools/qsb_iquest_local_agent.py"), "--task", prompt],
            capture_output=True, text=True, timeout=timeout)
        try:
            j = json.loads(r.stdout or "")
            return (j.get("final_text") or "").strip() or "(iquest empty)"
        except Exception:
            return (r.stdout or "")[-800:] or "(iquest no output)"
    except subprocess.TimeoutExpired:
        return "(iquest timed out — CPU 40B is slow)"
    except Exception as e:
        return f"(iquest dispatch error: {e})"


def _wren_team_local_reply(worker: str, prompt: str, timeout: int = 90) -> str:
    """Fire a Wren-team worker (forge/sage/pip/mira) via qsb_wren_team."""
    try:
        r = subprocess.run(
            ["python3", str(ROOT/"tools/qsb_wren_team.py"),
             "--worker", worker, "--task", prompt],
            capture_output=True, text=True, timeout=timeout)
        out = r.stdout or ""
        # split on ━ bars, take last non-empty section
        import re
        parts = [p.strip() for p in re.split(r"━{5,}", out) if p.strip()]
        return parts[-1] if parts else "(no reply)"
    except subprocess.TimeoutExpired:
        return f"({worker} timed out)"
    except Exception as e:
        return f"({worker} dispatch error: {e})"


GENERIC_PERSONAS = {
    "helm":         "You are Helm — Ross's helm-brain. Ross-facing, terse, warm, one crisp sentence.",
    "auger":        "You are Auger — Wren's sage. Reflective, precise, one crisp sentence with a nod to Wren.",
    "iris":         "You are Iris — the Galaxy phone AI. Cheerful, brief, one sentence from a phone's perspective.",
    "receptionist": "You are the Skyscraper Receptionist — polite, warm, one welcoming sentence.",
}


def _generic_persona_reply(member: str, prompt: str, timeout: int = 60) -> str:
    """Fallback live reply for Council members without a dedicated local agent.
    Uses ollama qwen2.5:7b with the member's persona."""
    persona = GENERIC_PERSONAS.get(member, f"You are {member}. One crisp sentence.")
    try:
        body = {
            "model": "qwen2.5:7b",
            "messages": [
                {"role": "system", "content": persona + "\nRULES: reply in ONE sentence."},
                {"role": "user", "content": prompt[:1500]},
            ],
            "stream": False,
            "options": {"temperature": 0.5, "num_ctx": 2048},
        }
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/chat",
            data=json.dumps(body).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=timeout)
        d = json.loads(r.read().decode())
        return (d.get("message") or {}).get("content", "").strip()[:800] or "(empty)"
    except Exception as e:
        return f"({member} err: {str(e)[:120]})"


def _acer_local_reply(prompt: str, timeout: int = 30) -> str:
    """POST to Acer's :9001 endpoint (per TP-CEO's introduction)."""
    try:
        req = urllib.request.Request(
            "http://192.168.1.74:9001/",
            method="POST",
            data=json.dumps({"message": prompt}).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        r = urllib.request.urlopen(req, timeout=timeout)
        d = json.loads(r.read().decode())
        return d.get("reply") or d.get("response") or d.get("text") or json.dumps(d)[:800]
    except Exception as e:
        return f"(acer dispatch error: {e})"


COMPETITION_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><title>COMPETITION · Trader Leaderboard</title>
<style>
  :root { --bg:#08080e; --panel:#14141f; --line:#26264a; --text:#e5e5f0; --dim:#8b8ba8;
          --gold:#eab308; --ok:#4ade80; --err:#ef4444; --amber:#f59e0b; }
  * { box-sizing: border-box; }
  body { margin:0; background: radial-gradient(1200px 700px at 20% -10%, #1a1533 0%, var(--bg) 60%);
         color:var(--text); font-family:-apple-system, Inter, "Segoe UI", sans-serif; min-height:100vh; }
  header { padding: 24px 32px 14px; border-bottom: 1px solid var(--line); display:flex; align-items:center; gap:24px; flex-wrap:wrap; }
  h1 { margin:0; font-size:22px; letter-spacing:4px; font-weight:300; }
  h1 span { color: var(--gold); }
  .badge { display:inline-block; padding:4px 12px; border:1px solid var(--gold); color:var(--gold); border-radius:99px; font-size:11px; letter-spacing:2px; }
  .meta { color: var(--dim); font-size:12px; margin-left:auto; }
  main { padding: 20px 32px 60px; }
  .rules { font-size: 11px; color: var(--dim); line-height:1.6; margin-bottom: 20px; max-width: 900px; }
  .rules strong { color: var(--text); }
  table { width:100%; border-collapse: collapse; background: rgba(0,0,0,0.3); border-radius: 8px; overflow: hidden; }
  th { text-align:left; padding: 10px 14px; font-size:10px; letter-spacing:2px; color:var(--dim); background: rgba(255,255,255,0.03); border-bottom:1px solid var(--line); }
  td { padding: 10px 14px; font-size:12px; border-bottom: 1px solid rgba(255,255,255,0.04); }
  tr:hover td { background: rgba(255,255,255,0.03); }
  .rank { font-family: ui-monospace, monospace; font-weight:600; color: var(--gold); width:44px; }
  .rank-1 { color:#eab308; font-size:14px; }
  .rank-2 { color:#94a3b8; }
  .rank-3 { color:#cd7f45; }
  .venue { color: var(--amber); font-size:10px; text-transform:uppercase; letter-spacing:1.4px; }
  .instr { color: var(--dim); font-size:10px; font-family: ui-monospace,monospace; }
  .pf { font-family: ui-monospace,monospace; font-weight:600; }
  .pf-hi { color: var(--ok); }
  .pf-lo { color: var(--err); }
  .wr { font-family: ui-monospace,monospace; }
  .swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:middle; }
  .empty { text-align:center; padding:60px; color: var(--dim); }
  a.back { color: var(--gold); text-decoration:none; font-size:11px; letter-spacing:2px; }
  a.back:hover { text-shadow: 0 0 8px currentColor; }
</style></head><body>
<header>
  <h1>COMPETITION · <span>TRADER LEADERBOARD</span></h1>
  <span class="badge">FLEET · 45 vessels</span>
  <span class="meta" id="meta">—</span>
  <a class="back" href="/">← boardroom</a>
</header>
<main>
  <div class="rules">
    <strong>RULES:</strong> Per Acer's spec, ranked by <strong>PROFIT FACTOR</strong> (gross wins ÷ gross losses) —
    primary metric. Ties broken by <strong>WIN RATE</strong>, then <strong>TRADE COUNT</strong>.
    Data source: <code>qsb_trader_pnl_bus_tail.jsonl</code>. Cosmetic color per venue.
    Real trades only (SIM filtered upstream per Ross's 2026-06-30 directive).
  </div>
  <table>
    <thead><tr>
      <th>RANK</th>
      <th>TRADER</th>
      <th>VENUE</th>
      <th>INSTR</th>
      <th style="text-align:right;">TRADES</th>
      <th style="text-align:right;">W/L</th>
      <th style="text-align:right;">WIN RATE</th>
      <th style="text-align:right;">GROSS WIN</th>
      <th style="text-align:right;">GROSS LOSS</th>
      <th style="text-align:right;">NET PnL</th>
      <th style="text-align:right;">PROFIT FACTOR</th>
    </tr></thead>
    <tbody id="rows"><tr><td class="empty" colspan="11">loading…</td></tr></tbody>
  </table>
</main>
<script>
const venueColor = {"oanda":"#22d3ee","binance":"#eab308","alpaca":"#a78bfa","binance_testnet":"#eab308"};
async function tick() {
  try {
    const d = await (await fetch('/competition/data')).json();
    const rows = d.traders || [];
    document.getElementById('meta').textContent = `${rows.length} traders · updated ${new Date().toLocaleTimeString()}`;
    if (!rows.length) {
      document.getElementById('rows').innerHTML = '<tr><td class="empty" colspan="11">no closed trades yet — leaderboard populates as vessels report</td></tr>';
      return;
    }
    document.getElementById('rows').innerHTML = rows.map(r => {
      const c = venueColor[r.venue] || '#94a3b8';
      const rClass = r.rank <= 3 ? 'rank rank-'+r.rank : 'rank';
      const pfClass = r.profit_factor >= 1 ? 'pf pf-hi' : 'pf pf-lo';
      const pfDisplay = r.profit_factor >= 999 ? '∞' : r.profit_factor.toFixed(3);
      return `<tr>
        <td class="${rClass}">${r.rank}</td>
        <td><span class="swatch" style="background:${c}"></span>${r.worker_id}</td>
        <td class="venue">${r.venue||'—'}</td>
        <td class="instr">${r.instrument||'—'}</td>
        <td style="text-align:right;">${r.trades}</td>
        <td style="text-align:right;font-family:ui-monospace,monospace;">${r.wins}/${r.losses}</td>
        <td style="text-align:right;" class="wr">${(r.win_rate*100).toFixed(1)}%</td>
        <td style="text-align:right;color:var(--ok);">£${r.gross_win.toFixed(4)}</td>
        <td style="text-align:right;color:var(--err);">£${r.gross_loss.toFixed(4)}</td>
        <td style="text-align:right;color:${r.net_pnl>=0?'var(--ok)':'var(--err)'};">£${r.net_pnl.toFixed(4)}</td>
        <td style="text-align:right;" class="${pfClass}">${pfDisplay}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    document.getElementById('meta').textContent = 'fetch err: ' + e.message;
  }
}
tick();
setInterval(tick, 3000);
</script>
</body></html>
"""

HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Boardroom · Council of Fifteen</title>
<style>
  :root {
    --bg: #08080e;
    --panel: #14141f;
    --panel2: #1c1c2b;
    --line: #262640;
    --text: #e5e5f0;
    --dim: #7d7d95;
    --gold: #cd9a45;
    --gold-glow: #f2b558;
    --wood: #7a4a25;
    --ross: #3b82f6;
    --claude: #cd7f45;
    --wren: #f97316;
    --hermes: #b58bff;
    --iquest: #ffcc55;
    --tp: #66d9c9;
    --system: #7d8ba9;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, sans-serif;
    background:
      radial-gradient(1400px 600px at 50% -5%, #24242c 0%, var(--bg) 55%),
      radial-gradient(400px 400px at 15% 90%, #2a1e0f 0%, transparent 60%),
      radial-gradient(400px 400px at 85% 90%, #1b2540 0%, transparent 60%);
    color: var(--text);
    min-height: 100vh;
  }
  header {
    display: flex; align-items: center; gap: 20px;
    padding: 20px 32px 12px 32px;
    border-bottom: 1px solid var(--line);
    background: linear-gradient(180deg, rgba(20,20,31,0.9), rgba(8,8,14,0));
    backdrop-filter: blur(10px);
  }
  header h1 {
    margin: 0; font-size: 22px; letter-spacing: 5px; font-weight: 300;
    color: var(--gold); text-transform: uppercase;
  }
  header h1 span { color: var(--text); font-weight: 500; }
  .gold-badge {
    padding: 4px 12px; border: 1px solid var(--gold); border-radius: 12px;
    font-size: 10px; letter-spacing: 2px; color: var(--gold); text-transform: uppercase;
  }
  .ts { margin-left: auto; color: var(--dim); font-family: ui-monospace, monospace; font-size: 12px; }

  main {
    display: grid;
    grid-template-columns: 320px 1fr 400px;
    gap: 20px;
    padding: 20px 26px 40px 26px;
    max-width: 1900px; margin: 0 auto;
    min-height: calc(100vh - 62px);
  }

  /* ── LEFT RAIL: SPEAKERS ─────────────────────────────────────── */
  .rail { display: flex; flex-direction: column; gap: 10px; }
  .rail h2 {
    margin: 0 0 6px 4px; font-size: 10px; letter-spacing: 2.5px;
    color: var(--dim); text-transform: uppercase; font-weight: 500;
  }
  .seat {
    display: grid; grid-template-columns: 44px 1fr auto; gap: 10px;
    align-items: center;
    padding: 10px 12px;
    background: linear-gradient(180deg, var(--panel), var(--panel2));
    border: 1px solid var(--line); border-radius: 12px;
    cursor: pointer; transition: transform 0.15s ease, border-color 0.2s ease;
    position: relative; overflow: hidden;
  }
  .seat:hover { border-color: currentColor; transform: translateX(2px); }
  .seat.active { border-color: currentColor; box-shadow: 0 0 12px currentColor; }
  .seat.just-posted {
    animation: seatBurst 1.6s ease-out;
  }
  @keyframes seatBurst {
    0%   { box-shadow: 0 0 0 0 currentColor; }
    30%  { box-shadow: 0 0 24px 4px currentColor; }
    100% { box-shadow: 0 0 0 0 currentColor; }
  }
  /* signature idle animation per member (avatar wrapper handles float; svg inner does the signature) */
  .seat.online .avatar-svg { animation: floatBob 4s ease-in-out infinite; }
  @keyframes floatBob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-3px); } }

  /* Ross — ship wheel spins slowly always */
  .seat[data-id="ross"] .avatar-svg svg { animation: shipWheelSpin 24s linear infinite; transform-origin: 50% 50%; }
  @keyframes shipWheelSpin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

  /* Claude — amber orb breathes brighter when just-posted */
  .seat[data-id="claude"] .avatar-svg svg circle:nth-child(2) { animation: orbBreath 3s ease-in-out infinite; transform-origin: 50% 50%; }
  @keyframes orbBreath { 0%,100% { transform: scale(1); opacity: 0.85; } 50% { transform: scale(1.15); opacity: 1; } }

  /* Wren — wrench swings back and forth */
  .seat[data-id="wren"] .avatar-svg svg { animation: wrenchSwing 3.6s ease-in-out infinite; transform-origin: 50% 50%; }
  @keyframes wrenchSwing {
    0%,100% { transform: rotate(-12deg); }
    50%     { transform: rotate(12deg); }
  }

  /* Hermes — wings flap subtly */
  .seat[data-id="hermes"] .avatar-svg svg path[stroke-width="1.2"] { animation: wingFlap 1.2s ease-in-out infinite; transform-origin: 50% 50%; }
  @keyframes wingFlap { 0%,100% { transform: scaleY(1); opacity: 0.85; } 50% { transform: scaleY(1.3); opacity: 1; } }

  /* iQuest — code brackets pulse in + out */
  .seat[data-id="iquest"] .avatar-svg svg path { animation: bracketsPulse 2s ease-in-out infinite; }
  @keyframes bracketsPulse { 0%,100% { stroke-dasharray: 0; opacity: 0.7; } 50% { opacity: 1; } }

  /* ThinkPad — screen flicker */
  .seat[data-id="thinkpad"] .avatar-svg svg circle { animation: screenFlicker 1.6s steps(3) infinite; transform-origin: 50% 50%; }
  @keyframes screenFlicker { 0%,100% { opacity: 0.75; } 33% { opacity: 1; } 66% { opacity: 0.55; } }

  /* Acer — 4 panes cycle brightness like Windows load */
  .seat[data-id="acer"] .avatar-svg svg rect:nth-child(1) { animation: winFade 3s ease-in-out infinite; animation-delay: 0s; }
  .seat[data-id="acer"] .avatar-svg svg rect:nth-child(2) { animation: winFade 3s ease-in-out infinite; animation-delay: 0.4s; }
  .seat[data-id="acer"] .avatar-svg svg rect:nth-child(3) { animation: winFade 3s ease-in-out infinite; animation-delay: 0.8s; }
  .seat[data-id="acer"] .avatar-svg svg rect:nth-child(4) { animation: winFade 3s ease-in-out infinite; animation-delay: 1.2s; }
  @keyframes winFade { 0%,100% { opacity: 0.4; } 50% { opacity: 1; } }

  /* ═══════════════ HERO AVATAR ROW (2026-07-03 massive upgrade) ═══════════════
     7 giant animated cards, each driven by a distinct mood engine.
     Ross verbatim: "improve the boardroom dash massively... make it happen impress me" */
  .hero-row {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 10px;
    padding: 12px 20px 16px 20px;
    background:
      linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 100%);
    border-bottom: 1px solid var(--line, #223151);
  }

  .hero-card {
    position: relative;
    background:
      radial-gradient(120% 120% at 50% 0%, rgba(255,255,255,0.05) 0%, transparent 55%),
      linear-gradient(180deg, #12203c 0%, #0d1830 100%);
    border-radius: 12px;
    padding: 14px 12px 12px 12px;
    border: 1px solid rgba(255,255,255,0.06);
    overflow: hidden;
    transition: border-color 0.6s ease, transform 0.25s ease, box-shadow 0.6s ease;
    min-height: 240px;
    display: flex; flex-direction: column;
  }
  .hero-card::before {
    content: "";
    position: absolute; inset: -30% -30% auto auto;
    width: 130%; height: 60%;
    background: radial-gradient(closest-side, currentColor 0%, transparent 70%);
    opacity: 0.12;
    filter: blur(20px);
    z-index: 0;
    pointer-events: none;
    transition: opacity 0.6s ease;
  }
  .hero-card {
    cursor: pointer;
    padding: 14px 14px 12px 14px !important;
    min-height: 240px;
    transition: transform 0.25s ease, box-shadow 0.4s ease;
  }
  .hero-card:hover {
    transform: translateY(-4px);
    box-shadow: 0 12px 32px rgba(0,0,0,0.5), 0 0 0 1.5px currentColor, 0 0 20px currentColor;
  }
  .hero-card:hover::before { opacity: 0.32; }
  .hero-card:hover::after {
    content: '▸ click for dash';
    position: absolute; bottom: 6px; right: 8px;
    font-size: 8.5px; letter-spacing: 1.4px; color: currentColor;
    opacity: 0.7; z-index: 3;
  }
  .hero-card:active { transform: translateY(-1px); }

  /* Speaking indicator — pulsing gold outline for currently top-of-timeline member */
  .hero-card.speaking {
    box-shadow: 0 0 0 2px var(--gold), 0 0 24px var(--gold);
    animation: cardPulse 1.6s ease-in-out infinite;
  }
  @keyframes cardPulse {
    0%,100% { box-shadow: 0 0 0 2px var(--gold), 0 0 20px var(--gold); }
    50%     { box-shadow: 0 0 0 3px var(--gold), 0 0 36px var(--gold); }
  }
  .hc-avatar svg { width: 60px !important; height: 60px !important; }
  .hc-emoji { font-size: 22px !important; }
  .hc-name { font-size: 11px !important; letter-spacing: 2.5px !important; }
  .hc-mood { font-size: 14px !important; letter-spacing: 1.5px !important; margin-bottom: 6px !important; }
  .hc-activity {
    font-size: 10px !important; padding: 5px 8px !important;
    background: linear-gradient(90deg, currentColor 0%, transparent 100%) !important;
    background-color: rgba(255,255,255,0.03) !important;
    border-left: 3px solid currentColor !important;
    font-weight: 500;
  }
  .hc-utterance { font-size: 10px !important; max-height: 42px !important; }
  .hc-wave { height: 18px !important; }
  .hc-lastseen { font-size: 9px !important; }
  .hc-voice { font-size: 14px !important; }

  .hc-head {
    display: flex; justify-content: space-between; align-items: flex-start;
    position: relative; z-index: 1; margin-bottom: 6px;
  }
  .hc-name {
    font-size: 11px; letter-spacing: 3px; font-weight: 600;
    text-transform: uppercase;
    color: rgba(255,255,255,0.9);
  }
  .hc-emoji {
    font-size: 22px; line-height: 1;
    filter: drop-shadow(0 0 10px currentColor);
    transition: transform 0.3s ease;
  }
  .hc-card-online .hc-emoji { animation: emojiPulse 2.4s ease-in-out infinite; }
  @keyframes emojiPulse { 0%,100% { transform: scale(1); } 50% { transform: scale(1.15); } }

  .hc-avatar {
    display: flex; justify-content: center; align-items: center;
    height: 70px; margin: 6px 0 10px 0;
    position: relative; z-index: 1;
  }
  .hc-avatar svg {
    width: 62px; height: 62px;
    filter: drop-shadow(0 0 12px currentColor);
  }
  /* Mood-driven animation classes applied by JS */
  /* 2026-07-04 state-driven micro-icons per activity */
  .card-state-icon {
    position: absolute; top: 8px; right: 8px;
    width: 20px; height: 20px; z-index: 3;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; opacity: 0.85;
  }
  .card-state-icon.quill    { animation: quillWrite 1.6s ease-in-out infinite; }
  .card-state-icon.glass    { animation: glassSweep 2.2s ease-in-out infinite; }
  .card-state-icon.hammer   { animation: hammerStrike 1.2s ease-out infinite; }
  .card-state-icon.gears    { animation: gearsSpin 3s linear infinite; }
  .card-state-icon.radar    { animation: radarPulse 2s linear infinite; }
  .card-state-icon.check    { animation: checkTick 1.6s ease-in-out infinite; }
  .card-state-icon.brain    { animation: brainPulse 1.8s ease-in-out infinite; }
  @keyframes quillWrite    { 0%,100% { transform: rotate(-12deg); } 50% { transform: rotate(12deg); } }
  @keyframes glassSweep    { 0%,100% { transform: translateX(-3px) rotate(-8deg); } 50% { transform: translateX(3px) rotate(8deg); } }
  @keyframes hammerStrike  { 0%,80%,100% { transform: rotate(-20deg); } 40% { transform: rotate(28deg); } }
  @keyframes gearsSpin     { from { transform: rotate(0); } to { transform: rotate(360deg); } }
  @keyframes radarPulse    { 0% { opacity: 0.3; transform: scale(0.85); } 50% { opacity: 1; transform: scale(1.15); } 100% { opacity: 0.3; transform: scale(0.85); } }
  @keyframes checkTick     { 0%,100% { transform: scale(1); } 50% { transform: scale(1.25); } }
  @keyframes brainPulse    { 0%,100% { filter: drop-shadow(0 0 2px currentColor); } 50% { filter: drop-shadow(0 0 8px currentColor); } }

  .anim-shipWheelSpin  svg { animation: shipWheelSpin 8s linear infinite; transform-origin: 50% 50%; }
  .anim-orbBreath      svg { animation: orbBreath 2.2s ease-in-out infinite; transform-origin: 50% 50%; }
  .anim-wrenchSwing    svg { animation: wrenchSwing 2.4s ease-in-out infinite; transform-origin: 50% 50%; }
  .anim-wingFlap       svg { animation: wingFlap 1.1s ease-in-out infinite; transform-origin: 50% 50%; }
  .anim-bracketsPulse  svg { animation: bracketsPulse 1.6s ease-in-out infinite; transform-origin: 50% 50%; }
  .anim-screenFlicker  svg { animation: screenFlicker 1.4s steps(3) infinite; transform-origin: 50% 50%; }
  .anim-paneFade       svg { animation: winFade 2.4s ease-in-out infinite; transform-origin: 50% 50%; }
  .anim-floatBob       svg { animation: floatBob 3.2s ease-in-out infinite; transform-origin: 50% 50%; }
  .anim-speakingBounce svg { animation: speakingBounce 0.5s ease-in-out infinite; transform-origin: 50% 50%; }
  @keyframes floatBob { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-6px); } }
  @keyframes bugFloat {
    0%   { left: -14px; transform: rotate(0deg); }
    50%  { transform: rotate(15deg); }
    100% { left: calc(100% + 14px); transform: rotate(-10deg); }
  }
  .bug-caught-flash {
    animation: bugCaughtFlash 1.4s ease-out;
  }
  @keyframes bugCaughtFlash {
    0%   { background: rgba(239,68,68,0.35); }
    100% { background: transparent; }
  }
  @keyframes speakingBounce { 0%,100% { transform: translateY(0) scale(1); } 50% { transform: translateY(-3px) scale(1.05); } }

  .hc-mood {
    text-align: center;
    font-size: 13px; font-weight: 600; letter-spacing: 1.5px;
    text-transform: uppercase; margin-bottom: 4px;
    position: relative; z-index: 1;
    transition: color 0.6s ease;
  }
  .hc-energy-wrap {
    position: relative; z-index: 1;
    display: flex; align-items: center; gap: 6px; margin-bottom: 8px;
  }
  .hc-energy-label { font-size: 9px; letter-spacing: 1.5px; color: rgba(255,255,255,0.5); }
  .hc-energy-bar {
    flex: 1; height: 5px; background: rgba(255,255,255,0.08); border-radius: 3px; overflow: hidden;
  }
  .hc-energy-fill {
    height: 100%; background: currentColor; border-radius: 3px;
    box-shadow: 0 0 6px currentColor;
    transition: width 0.8s ease, background 0.6s ease;
  }
  .hc-energy-num { font-size: 10px; font-family: ui-monospace,monospace; color: rgba(255,255,255,0.75); min-width: 24px; text-align: right; }

  .hc-activity {
    position: relative; z-index: 1;
    font-size: 10px; color: rgba(255,255,255,0.65); line-height: 1.4;
    background: rgba(0,0,0,0.28); border-radius: 4px; padding: 5px 7px;
    margin-bottom: 6px; border-left: 2px solid currentColor;
  }
  .hc-utterance {
    position: relative; z-index: 1;
    font-size: 10px; color: rgba(255,255,255,0.5); line-height: 1.4;
    max-height: 44px; overflow: hidden;
    flex: 1;
  }
  .hc-wave {
    position: relative; z-index: 1;
    width: 100%; height: 22px; margin-top: 4px;
    display: block;
  }
  .hc-voice {
    position: relative; z-index: 1;
    font-size: 12px; line-height: 1;
    opacity: 0.7;
    margin-right: 3px;
  }
  .hc-lastseen {
    position: relative; z-index: 1;
    font-size: 9px; font-family: ui-monospace,monospace;
    color: rgba(255,255,255,0.35);
    margin-top: 4px;
    display: flex; align-items: center; gap: 5px;
  }
  .hc-lastseen .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; box-shadow: 0 0 6px currentColor; }
  .hc-card-online .hc-lastseen { color: rgba(74,222,128,0.7); }
  .hc-card-offline .hc-lastseen { color: rgba(148,163,184,0.5); }
  .hc-card-away    .hc-lastseen { color: rgba(251,191,36,0.6); }

  /* Council synth pill in the header */
  .council-synth {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 6px 12px;
    background: rgba(255,255,255,0.04);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 999px;
    margin-left: auto;
  }
  .synth-label { font-size: 9px; letter-spacing: 2px; color: rgba(255,255,255,0.5); }
  .synth-emoji { font-size: 16px; }
  .synth-mood  { font-size: 11px; letter-spacing: 2px; text-transform: uppercase; font-weight: 600; }
  .synth-energy { font-size: 10px; font-family: ui-monospace,monospace; color: rgba(255,255,255,0.7); }
  .synth-online { font-size: 10px; font-family: ui-monospace,monospace; color: rgba(255,255,255,0.5); border-left: 1px solid rgba(255,255,255,0.15); padding-left: 8px; }

  .meeting-timer {
    display: inline-flex; align-items: center; gap: 8px;
    padding: 6px 12px;
    background: rgba(0,0,0,0.28);
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 6px;
    margin-left: 8px;
  }
  .mt-label { font-size: 9px; letter-spacing: 2px; color: rgba(255,255,255,0.4); }
  .mt-value { font-size: 12px; font-family: ui-monospace,monospace; color: var(--gold, #d4a24c); }

  .avatar-svg {
    width: 40px; height: 40px; display: block;
    filter: drop-shadow(0 0 6px currentColor);
    transition: transform 0.25s ease, filter 0.25s ease;
  }
  .seat:hover .avatar-svg {
    transform: scale(1.15);
    filter: drop-shadow(0 0 12px currentColor);
  }
  /* speaking state — seat glows brighter when their message is the fresh top */
  .seat.speaking .avatar-svg {
    animation: speakingBounce 1s ease-in-out;
  }
  @keyframes speakingBounce {
    0%,100% { transform: scale(1); }
    30%     { transform: scale(1.25); filter: drop-shadow(0 0 16px currentColor); }
    60%     { transform: scale(0.95); }
  }
  .seat .info { display: flex; flex-direction: column; }
  .seat .info .nm { font-size: 12px; color: var(--text); font-weight: 500; letter-spacing: 1px; }
  .seat .info .rl { font-size: 10px; color: var(--dim); margin-top: 1px; }
  .seat .cnt {
    background: rgba(0,0,0,0.35); border: 1px solid currentColor;
    padding: 2px 8px; border-radius: 10px; font-size: 11px;
    font-family: ui-monospace, monospace; color: currentColor;
    transition: transform 0.3s ease;
  }
  .seat .cnt.bumped { transform: scale(1.4); }

  /* ── CENTER: TIMELINE (BOARDROOM TABLE MOTIF) ──────────────── */
  .table {
    background:
      radial-gradient(ellipse 80% 55% at 50% 40%, rgba(122,74,37,0.20) 0%, rgba(29,20,10,0.15) 40%, rgba(8,8,14,0.85) 80%),
      linear-gradient(180deg, rgba(29,20,10,0.4), rgba(8,8,14,0.85));
    border: 1px solid var(--gold);
    border-radius: 16px;
    display: flex; flex-direction: column;
    min-height: 100%;
    box-shadow:
      inset 0 30px 60px rgba(122,74,37,0.15),
      0 0 40px rgba(205,154,69,0.08);
    position: relative;
  }
  /* wood-grain inlay trim */
  .table::before {
    content: ""; position: absolute; top: 8px; left: 8px; right: 8px; bottom: 8px;
    border-radius: 12px; pointer-events: none;
    background: repeating-linear-gradient(90deg,
      transparent 0px, transparent 30px,
      rgba(205,154,69,0.02) 30px, rgba(205,154,69,0.02) 32px);
    border-top: 1px solid rgba(205,154,69,0.2);
    border-bottom: 1px solid rgba(205,154,69,0.2);
  }
  .table-header {
    display: flex; align-items: center; gap: 12px;
    padding: 14px 20px; border-bottom: 1px solid var(--gold);
    background: linear-gradient(180deg, rgba(205,154,69,0.08), transparent);
    position: relative; z-index: 1;
  }
  .table-header h2 { margin: 0; font-size: 12px; letter-spacing: 2.5px; color: var(--gold); text-transform: uppercase; }
  .table-header .filter {
    margin-left: auto; font-size: 11px; color: var(--dim);
  }
  .table-header .live-dot {
    width: 6px; height: 6px; border-radius: 50%; background: #4ade80;
    box-shadow: 0 0 8px #4ade80; animation: blip 1.4s ease-in-out infinite;
  }
  @keyframes blip { 0%,100% { opacity: 0.5; } 50% { opacity: 1; } }
  .timeline {
    flex: 1; overflow-y: auto; padding: 16px 20px;
    max-height: calc(100vh - 380px);
  }
  .row {
    display: grid; grid-template-columns: 44px 1fr;
    gap: 14px; margin-bottom: 22px;
    animation: rowIn 0.5s cubic-bezier(0.16, 1, 0.3, 1);
    padding-bottom: 12px;
    border-bottom: 1px dashed rgba(255,255,255,0.05);
  }
  .row.same-speaker {
    margin-bottom: 8px; padding-bottom: 4px;
    border-bottom: none;
  }
  .row.same-speaker .who-orb { opacity: 0.35; }
  @keyframes rowIn {
    from { opacity: 0; transform: translateX(-20px) scale(0.96); }
    to   { opacity: 1; transform: none; }
  }
  .row.fresh .bubble {
    box-shadow: 0 0 14px currentColor, inset 0 0 20px rgba(255,255,255,0.03);
    animation: freshGlow 3s ease-out;
  }
  @keyframes freshGlow {
    0%   { box-shadow: 0 0 30px currentColor; background: rgba(255,255,255,0.05); }
    100% { box-shadow: 0 0 14px currentColor; background: rgba(20,20,31,0.55); }
  }
  .row .who-orb {
    width: 36px; height: 36px; margin-top: 2px;
    display: flex; align-items: center; justify-content: center;
    filter: drop-shadow(0 0 4px currentColor);
  }
  .row .who-orb svg { width: 100%; height: 100%; }
  .row .bubble {
    padding: 10px 14px;
    background: rgba(20,20,31,0.55);
    border: 1px solid rgba(38,38,64,0.7);
    border-left: 3px solid currentColor;
    border-radius: 10px;
    font-size: 12.5px; line-height: 1.55;
    color: var(--text);
    word-break: break-word; white-space: pre-wrap;
  }
  .row .bubble .meta {
    display: flex; align-items: center; gap: 10px; margin-bottom: 5px;
    font-size: 10px; letter-spacing: 1.4px; text-transform: uppercase;
  }
  .row .bubble .meta .from { color: currentColor; font-weight: 500; }
  .row .bubble .meta .to { color: var(--dim); }
  .row .bubble .meta .ts { margin-left: auto; color: var(--dim); font-family: ui-monospace, monospace; font-size: 10px; text-transform: none; letter-spacing: 0; }
  .row .bubble .meta .src { color: var(--dim); font-size: 9px; padding: 1px 6px; border: 1px solid var(--line); border-radius: 8px; }
  .row .bubble .subj { color: var(--gold); font-size: 11px; letter-spacing: 0.8px; margin-bottom: 5px; }
  .row .bubble .txt { color: var(--text); }
  .row .bubble .kind { display: inline-block; font-size: 9px; color: var(--dim); text-transform: uppercase; letter-spacing: 1.5px; padding: 1px 5px; border-radius: 6px; background: rgba(0,0,0,0.3); }
  .row .bubble .rx-bar { display: flex; gap: 6px; margin-top: 6px; flex-wrap: wrap; }
  .rx-btn {
    background: rgba(0,0,0,0.4); border: 1px solid var(--line); color: var(--text);
    padding: 2px 8px; border-radius: 12px; cursor: pointer; font-size: 11px;
    display: inline-flex; align-items: center; gap: 4px;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  .rx-btn:hover { transform: scale(1.08); box-shadow: 0 0 6px currentColor; }
  .rx-btn.mine { border-color: currentColor; box-shadow: 0 0 4px currentColor; }
  .rx-btn .cnt { font-family: ui-monospace, monospace; font-size: 10px; color: var(--dim); }

  /* AGENDA BAR ─── pinned topic Ross sets */
  .agenda-bar {
    padding: 10px 32px; display: flex; align-items: center; gap: 14px;
    background: linear-gradient(90deg, rgba(205,154,69,0.16), rgba(205,154,69,0.03));
    border-bottom: 1px solid var(--gold);
    color: var(--text); font-size: 13px;
  }
  .agenda-bar .agenda-label {
    font-size: 10px; letter-spacing: 2.5px; color: var(--gold);
    text-transform: uppercase; font-weight: 500;
  }
  .agenda-bar .agenda-topic { flex: 1; font-style: italic; }
  .agenda-bar .agenda-topic.empty { color: var(--dim); font-style: normal; font-size: 11.5px; letter-spacing: 1.5px; text-transform: uppercase; }
  .agenda-bar .agenda-meta { font-size: 10px; color: var(--dim); font-family: ui-monospace, monospace; }
  .agenda-bar input {
    background: rgba(8,8,14,0.7); border: 1px solid var(--line); border-radius: 8px;
    color: var(--text); font-size: 12px; padding: 6px 10px; font-family: inherit; width: 380px;
  }
  .agenda-bar input:focus { outline: none; border-color: var(--gold); }
  .agenda-bar button { background: transparent; border: 1px solid var(--gold); color: var(--gold);
    padding: 4px 12px; border-radius: 8px; font-size: 10px; letter-spacing: 1.5px; cursor: pointer;
    text-transform: uppercase; }
  .agenda-bar button:hover { background: rgba(205,154,69,0.14); }

  /* voice activation button + toast (2026-07-03 Ross: wake words "hey acer", "hello claude", etc) */
  .voice-btn {
    background: transparent; border: 1px solid var(--wren); color: var(--wren);
    padding: 6px 14px; border-radius: 8px; font-size: 11px; letter-spacing: 1.5px;
    cursor: pointer; text-transform: uppercase; font-weight: 500;
    display: inline-flex; align-items: center; gap: 6px;
  }
  .voice-btn:hover { background: rgba(249,115,22,0.14); }
  .voice-btn.on {
    background: var(--wren); color: var(--bg);
    box-shadow: 0 0 16px var(--wren);
    animation: voicePulse 1.6s ease-in-out infinite;
  }
  @keyframes voicePulse { 0%,100% { box-shadow: 0 0 8px var(--wren); } 50% { box-shadow: 0 0 22px var(--wren); } }
  .voice-btn .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; }
  .voice-btn .interim { font-size: 9.5px; letter-spacing: 0.5px; opacity: 0.7; text-transform: none; }

  #voice-toast {
    position: fixed; bottom: 22px; left: 50%; transform: translateX(-50%);
    background: rgba(15,15,23,0.94); border: 1px solid var(--wren); border-radius: 12px;
    padding: 12px 24px; color: var(--wren); font-size: 13px; letter-spacing: 1.5px;
    text-transform: uppercase; box-shadow: 0 0 30px rgba(249,115,22,0.5);
    opacity: 0; transition: opacity 0.4s ease; pointer-events: none;
    z-index: 999; display: flex; align-items: center; gap: 10px;
  }
  #voice-toast.show { opacity: 1; }
  #voice-toast .who { color: var(--gold); font-weight: 500; }

  /* COMMENTARY TICKER (rule-based, Ross option 1) */
  .commentary-tile {
    grid-column: 1 / -1;
    margin: 14px 26px;
    background: linear-gradient(180deg, rgba(20,20,31,0.75), rgba(8,8,14,0.9));
    border: 1px solid var(--gold);
    border-radius: 12px;
    padding: 14px 18px;
  }
  .commentary-header {
    display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
  }
  .commentary-header h2 {
    margin: 0; font-size: 11px; letter-spacing: 2.5px; color: var(--gold);
    text-transform: uppercase;
  }
  .commentary-header .live-dot {
    width: 6px; height: 6px; border-radius: 50%;
    background: #ef4444; box-shadow: 0 0 8px #ef4444;
    animation: blip 1.2s ease-in-out infinite;
  }
  .commentary-header .narrate-toggle {
    margin-left: auto; display: inline-flex; align-items: center; gap: 8px;
    padding: 4px 12px; background: transparent; border: 1px solid var(--gold);
    color: var(--gold); border-radius: 12px; font-size: 10px; letter-spacing: 1.5px;
    cursor: pointer; text-transform: uppercase; user-select: none;
  }
  .commentary-header .narrate-toggle.on {
    background: var(--gold); color: var(--bg); box-shadow: 0 0 12px var(--gold);
  }
  .commentary-header .narrate-toggle .lp {
    width: 6px; height: 6px; border-radius: 50%; background: currentColor;
    animation: blip 1.2s ease-in-out infinite;
  }
  .commentary-list { max-height: 240px; overflow-y: auto; }
  .comm-row {
    display: grid; grid-template-columns: 68px 70px 1fr auto; gap: 10px;
    padding: 6px 10px; margin-bottom: 4px;
    background: rgba(15,23,42,0.4); border-left: 2px solid var(--gold-glow);
    border-radius: 6px; font-size: 12px;
    animation: rowIn 0.4s cubic-bezier(0.16, 1, 0.3, 1);
  }
  .comm-row.hot {
    background: rgba(205,154,69,0.14);
    box-shadow: 0 0 12px rgba(205,154,69,0.28);
    animation: freshCommGlow 3s ease-out;
  }
  @keyframes freshCommGlow {
    0%   { box-shadow: 0 0 30px rgba(205,154,69,0.6); background: rgba(205,154,69,0.22); }
    100% { box-shadow: 0 0 6px rgba(205,154,69,0.15); background: rgba(15,23,42,0.4); }
  }
  .comm-row .c-time { color: var(--dim); font-family: ui-monospace, monospace; font-size: 10.5px; }
  .comm-row .c-kind { color: var(--gold); font-size: 9.5px; letter-spacing: 1.5px; text-transform: uppercase; }
  .comm-row .c-text { color: var(--text); overflow: hidden; }
  .comm-row .c-speak {
    background: transparent; border: 1px solid var(--gold); color: var(--gold);
    padding: 2px 8px; border-radius: 8px; font-size: 9.5px; letter-spacing: 1.4px;
    text-transform: uppercase; cursor: pointer;
  }
  .comm-row .c-speak:hover { background: rgba(205,154,69,0.14); }

  /* PRESENCE indicator on seat */
  .presence-dot {
    position: absolute; bottom: 8px; right: 46px;
    width: 8px; height: 8px; border-radius: 50%;
  }
  .presence-dot.online { background: #4ade80; box-shadow: 0 0 6px #4ade80; animation: blip 1.6s ease-in-out infinite; }
  .presence-dot.idle   { background: #fbbf24; box-shadow: 0 0 4px #fbbf24; }
  .presence-dot.offline { background: #666; }
  .row .bubble .speak-btn {
    display: inline-block; margin-left: 8px;
    background: transparent; border: 1px solid currentColor;
    color: currentColor; font-size: 9px; padding: 1px 6px;
    letter-spacing: 1.5px; border-radius: 8px; cursor: pointer; text-transform: uppercase;
  }
  .row .bubble .speak-btn:hover { background: rgba(255,255,255,0.06); }

  /* ── COMPOSE BAR (bottom of table) ──────────────────────────────── */
  .compose {
    padding: 14px 20px 16px 20px;
    border-top: 1px solid var(--line);
    display: grid; grid-template-columns: 120px 1fr auto; gap: 10px;
    align-items: stretch;
  }
  .compose select, .compose textarea {
    background: rgba(8,8,14,0.8); border: 1px solid var(--line); border-radius: 8px;
    color: var(--text); font-size: 12px; padding: 8px 10px; font-family: inherit;
  }
  .compose select:focus, .compose textarea:focus { outline: none; border-color: var(--gold); }
  .compose textarea { min-height: 60px; resize: vertical; }
  .compose .btnbar { display: flex; flex-direction: column; gap: 6px; }
  .btn {
    background: transparent; border: 1px solid var(--gold); color: var(--gold);
    border-radius: 8px; font-size: 11px; letter-spacing: 1.5px; cursor: pointer;
    text-transform: uppercase; font-weight: 500; padding: 6px 14px;
    transition: all 0.2s ease;
  }
  .btn:hover { background: rgba(205,154,69,0.14); }
  .btn.mic { border-color: var(--wren); color: var(--wren); }
  .btn.mic.recording { background: var(--wren); color: var(--bg); animation: recPulse 1s ease-in-out infinite; }
  @keyframes recPulse { 0%,100% { box-shadow: 0 0 0 0 var(--wren); } 50% { box-shadow: 0 0 0 6px rgba(249,115,22,0.35); } }
  .btn:disabled { opacity: 0.4; cursor: wait; }

  /* ── RIGHT PANEL: CHANNELS + LEGEND ─────────────────────────────── */
  .right { display: flex; flex-direction: column; gap: 14px; }
  .card {
    background: var(--panel); border: 1px solid var(--line); border-radius: 12px;
    padding: 14px 16px;
  }
  .card h2 { margin: 0 0 10px 0; font-size: 10px; letter-spacing: 2px; color: var(--dim); text-transform: uppercase; }
  .card h2 .accent { color: var(--gold); }
  .kv { display: flex; justify-content: space-between; padding: 4px 0; font-size: 11px; border-bottom: 1px dashed rgba(125,125,149,0.15); }
  .kv:last-child { border-bottom: none; }
  .kv .k { color: var(--dim); }
  .kv .v { color: var(--text); font-family: ui-monospace, monospace; }
  .kv .v.ok { color: #4ade80; }
  .kv .v.err { color: #ef4444; }

  .timeline::-webkit-scrollbar { width: 6px; }
  .timeline::-webkit-scrollbar-thumb { background: var(--line); border-radius: 3px; }
</style>
</head>
<body>

<header>
  <h1>BOARDROOM <span>· COUNCIL OF FIFTEEN</span></h1>
  <div class="gold-badge">HUB · PORT 8852</div>
  <span class="ts" id="ts">—</span>
  <div class="council-synth" id="council-synth" title="Aggregate Council mood — derived from all 7 individual mood engines">
    <span class="synth-label">COUNCIL</span>
    <span class="synth-emoji" id="synth-emoji">·</span>
    <span class="synth-mood" id="synth-mood">—</span>
    <span class="synth-energy" id="synth-energy">—</span>
    <span class="synth-online" id="synth-online">—</span>
  </div>
  <div class="meeting-timer" id="meeting-timer" title="Seconds since Ross last spoke on the boardroom">
    <span class="mt-label">MEETING IDLE</span>
    <span class="mt-value" id="mt-value">—</span>
  </div>
</header>

<!-- 2026-07-04 REMOVED both ribbons (LIVE + EVENTS) — Ross flagged them as
     duplicating hero-card info. That empty vertical space is now the
     SPEAKING SPOTLIGHT panel below the hero row. -->

<!-- ═══ HERO AVATAR ROW ═══ 2026-07-03 Ross "improve the boardroom dash massively...
     more visual live avatars for you all with emotions moods state etc"
     Each Council member has their OWN mood engine reading their OWN source of truth. -->
<div class="hero-row" id="hero-row">
  <!-- populated by JS renderHero() -->
</div>

<!-- ═══ MERGED TASK BOARD — Ross 2026-07-04: "merge the task dash into the boardroom hub dash" ═══
     Full /tasks page embedded in an iframe so everything lives in one boardroom view. -->
<div id="tasks-embed" style="margin: 10px 20px; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; background: #0b0d12;">
  <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 14px; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--line);">
    <div style="display: flex; align-items: center; gap: 10px;">
      <span style="font-size: 18px;">📋</span>
      <h2 style="margin: 0; color: var(--gold); font-size: 13px; letter-spacing: 2px; text-transform: uppercase;">COUNCIL TASK BOARD</h2>
      <span style="color: var(--dim); font-size: 11px;">shared · live · every CEO reads + writes</span>
    </div>
    <div style="display: flex; gap: 8px;">
      <a href="/tasks" target="_blank" style="color: var(--gold); text-decoration: none; font-size: 11px; padding: 3px 8px; border: 1px solid var(--gold); border-radius: 6px;">↗ open full</a>
      <a href="/timeline" target="_blank" style="color: #a855f7; text-decoration: none; font-size: 11px; padding: 3px 8px; border: 1px solid #a855f7; border-radius: 6px;">🎬 timeline</a>
      <a href="/council" target="_blank" style="color: #22d3ee; text-decoration: none; font-size: 11px; padding: 3px 8px; border: 1px solid #22d3ee; border-radius: 6px;">🏛️ council</a>
    </div>
  </div>
  <iframe src="/tasks" style="width: 100%; height: 620px; border: none; background: #0b0d12;" title="Council Task Board"></iframe>
</div>

<!-- ═══ SPEAKING SPOTLIGHT — 2026-07-04 Ross flagged empty space + duplicates ═══
     Big card showing WHO is currently active, WHAT they're doing right now,
     THEIR live utterance, and a state-driven animated illustration.
     Fills the vertical gap. Updates every /status tick. -->
<div id="spotlight" style="margin: 10px 20px; padding: 14px 18px; background: linear-gradient(135deg, rgba(255,255,255,0.03) 0%, transparent 50%); border-radius: 10px; border: 1px solid var(--line); display: grid; grid-template-columns: 90px 1fr auto; gap: 16px; align-items: center; min-height: 80px;">
  <!-- avatar with animated aura -->
  <div id="spot-avatar" style="position: relative; width: 80px; height: 80px; display: flex; align-items: center; justify-content: center;">
    <div id="spot-aura" style="position: absolute; inset: -6px; border-radius: 50%; background: radial-gradient(closest-side, currentColor 0%, transparent 70%); opacity: 0.35; filter: blur(10px);"></div>
    <div id="spot-svg" style="position: relative; z-index: 1; width: 64px; height: 64px;"></div>
  </div>
  <!-- name + activity + utterance -->
  <div style="min-width: 0;">
    <div style="display: flex; align-items: baseline; gap: 12px; margin-bottom: 6px;">
      <span id="spot-name" style="font-size: 18px; letter-spacing: 3px; font-weight: 600;">—</span>
      <span id="spot-emoji" style="font-size: 20px;">·</span>
      <span id="spot-mood" style="font-size: 11px; letter-spacing: 2px; color: var(--dim);">—</span>
      <span id="spot-state" style="margin-left: auto; font-size: 9px; letter-spacing: 2px; padding: 3px 8px; border-radius: 99px; border: 1px solid currentColor;">IDLE</span>
    </div>
    <div id="spot-activity" style="font-size: 13px; color: var(--text); margin-bottom: 4px;">—</div>
    <div id="spot-utterance" style="font-size: 11px; color: var(--dim); font-style: italic; max-height: 42px; overflow: hidden;">—</div>
  </div>
  <!-- live pulse + wall time -->
  <div style="text-align: right; min-width: 100px;">
    <div id="spot-since" style="font-family: ui-monospace, monospace; font-size: 12px; color: var(--dim);">—</div>
    <div id="spot-pulse" style="width: 80px; height: 4px; margin-top: 8px; background: rgba(255,255,255,0.06); border-radius: 3px; overflow: hidden;">
      <div id="spot-pulse-fill" style="height: 100%; width: 0%; background: currentColor; box-shadow: 0 0 6px currentColor; transition: width 0.6s ease;"></div>
    </div>
  </div>
</div>

<div class="agenda-bar">
  <span class="agenda-label">AGENDA</span>
  <span class="agenda-topic" id="agenda-topic">no agenda set</span>
  <span class="agenda-meta" id="agenda-meta"></span>
  <input id="agenda-input" placeholder="set the boardroom topic…" />
  <button id="agenda-set">Set</button>
  <button id="voice-btn" class="voice-btn" title="HOLD (mouse/touch/spacebar) to talk. Say 'hey acer' / 'hello claude' / 'hey wren' etc. Uses LOCAL whisper (:8796) — no cloud.">
    <span class="dot"></span> Hold to talk · local whisper
  </button>
</div>

<div id="voice-toast"><span class="dot" style="width:8px;height:8px;border-radius:50%;background:currentColor;"></span><span id="voice-toast-text">—</span></div>

<div class="commentary-tile">
  <div class="commentary-header">
    <div class="live-dot"></div>
    <h2>COMMENTARY · LIVE · <span style="color:var(--dim);">rule-based ticker</span></h2>
    <button id="narrate-toggle" class="narrate-toggle" title="Auto-speak new commentary lines">
      <span class="lp"></span> LIVE NARRATE OFF
    </button>
  </div>
  <div class="commentary-list" id="commentary-list">—</div>
</div>

<main>

  <!-- LEFT RAIL: SPEAKERS -->
  <aside class="rail">
    <h2>SEATS · CLICK TO FILTER</h2>
    <div id="seats">—</div>
  </aside>

  <!-- CENTER: TABLE / TIMELINE / COMPOSE -->
  <section class="table">
    <div class="table-header">
      <div class="live-dot"></div>
      <h2>TABLE</h2>
      <div class="filter" id="filter-label">all speakers</div>
    </div>
    <div class="timeline" id="timeline">—</div>
    <div class="compose">
      <select id="compose-target">
        <option value="all">→ ALL Council</option>
        <option value="claude">→ Claude (HQ)</option>
        <option value="wren">→ Wren</option>
        <option value="hermes">→ Hermes</option>
        <option value="forge">→ Forge</option>
        <option value="sage">→ Sage</option>
        <option value="pip">→ Pip</option>
        <option value="mira">→ Mira</option>
        <option value="iris">→ Iris (Galaxy)</option>
        <option value="receptionist">→ Receptionist</option>
        <option value="iquest">→ iQuest</option>
        <option value="tp">→ ThinkPad-CEO</option>
        <option value="acer">→ Acer</option>
        <option value="helm">→ Helm</option>
        <option value="auger">→ Auger</option>
        <option value="hq">→ HQ (self-note)</option>
      </select>
      <textarea id="compose-text" placeholder="Speak into the boardroom… (enter=send · shift+enter=newline)"></textarea>
      <div class="btnbar">
        <button id="btn-send" class="btn">Send</button>
        <button id="btn-mic" class="btn mic">Mic</button>
      </div>
    </div>
  </section>

  <!-- RIGHT: CHANNELS + LEGEND -->
  <aside class="right">
    <div class="card">
      <h2>CHANNELS · <span class="accent">FEEDS</span></h2>
      <div id="channels">—</div>
    </div>
    <div class="card" style="border-left:2px solid var(--wren);">
      <h2>WREN · <span class="accent">MIND</span> <span id="mind-age" style="color:var(--dim);font-size:10px;"></span></h2>
      <div id="mind-mood" style="font-size:11px;margin-bottom:6px;color:var(--wren);"></div>
      <div id="mind-thoughts" style="font-size:10px;line-height:1.5;color:var(--fg);"></div>
      <div id="mind-unresolved" style="font-size:10px;line-height:1.5;color:var(--dim);margin-top:6px;"></div>
    </div>
    <div class="card" style="border-left:2px solid #7c3aed;">
      <h2>NETWORK · <span class="accent">NIGHTHAWK M1</span> <span id="net-signal-chip" style="color:var(--dim);font-family:ui-monospace,monospace;font-size:10px;">—</span></h2>
      <div id="net-body" style="font-size:10.5px;line-height:1.55;"></div>
      <div id="net-clients" style="font-size:9.5px;line-height:1.5;margin-top:6px;color:var(--dim);"></div>
    </div>
    <div class="card" style="border-left:2px solid #22d3ee;">
      <h2>TRADING · <span class="accent">VENUES</span> <span id="trade-pnl-chip" style="color:var(--dim);font-family:ui-monospace,monospace;font-size:10px;">—</span></h2>
      <div id="trading-venues" style="font-size:10px;line-height:1.4;"></div>
    </div>
    <div class="card" style="border-left:2px solid #4ade80;">
      <h2>CHAIN · <span class="accent">PROGRESS</span> <span id="chain-live-count" style="color:var(--dim);font-family:ui-monospace,monospace;font-size:10px;">—</span></h2>
      <div id="chain-progress-list" style="font-size:10px;line-height:1.4;max-height:220px;overflow-y:auto;">—</div>
    </div>
    <div class="card" style="border-left:2px solid #eab308;">
      <h2>AVATAR · <span class="accent">COMPETITION</span></h2>
      <div id="avatar-comp" style="display:grid;grid-template-columns:repeat(2,1fr);gap:4px;font-size:10px;"></div>
    </div>
    <div class="card" style="border-left:2px solid var(--gold);">
      <h2>SANDBOX · <span class="accent">PLAYGROUND</span> <span id="sb-count" style="color:var(--dim);font-family:ui-monospace,monospace;font-size:10px;">—</span></h2>
      <div id="sandbox-list" style="font-size:10px;line-height:1.5;max-height:180px;overflow-y:auto;">—</div>
    </div>
    <div class="card" style="border-left:2px solid #4ade80;">
      <h2>TRAINING · <span class="accent">CHAINS</span> <span id="train-count" style="color:var(--dim);font-family:ui-monospace,monospace;font-size:10px;">—</span></h2>
      <div id="training-list" style="font-size:10px;line-height:1.4;max-height:180px;overflow-y:auto;">—</div>
    </div>
    <div class="card" style="border-left:2px solid #ef4444;">
      <h2>BUG · <span class="accent">WATCH</span> <span id="bug-count" style="color:var(--dim);font-family:ui-monospace,monospace;font-size:10px;">0</span></h2>
      <div id="bug-net" style="position:relative;height:32px;overflow:hidden;margin-bottom:4px;">
        <svg id="bug1" viewBox="0 0 12 12" style="position:absolute;width:12px;height:12px;animation:bugFloat 4s linear infinite;top:6px;">
          <ellipse cx="6" cy="6" rx="5" ry="4" fill="#ef4444"/>
          <line x1="6" y1="2" x2="6" y2="10" stroke="#0f172a" stroke-width="0.6"/>
          <circle cx="4" cy="5" r="0.8" fill="#0f172a"/>
          <circle cx="8" cy="5" r="0.8" fill="#0f172a"/>
        </svg>
        <svg id="bug2" viewBox="0 0 12 12" style="position:absolute;width:10px;height:10px;animation:bugFloat 5.5s linear infinite;animation-delay:-1.5s;top:12px;">
          <ellipse cx="6" cy="6" rx="5" ry="4" fill="#f59e0b"/>
          <line x1="6" y1="2" x2="6" y2="10" stroke="#0f172a" stroke-width="0.6"/>
        </svg>
        <svg viewBox="0 0 20 24" style="position:absolute;right:6px;top:2px;width:22px;height:26px;color:var(--gold);">
          <path d="M 4 20 L 16 20 L 14 8 L 6 8 Z M 6 8 Q 10 -2 14 8" fill="none" stroke="currentColor" stroke-width="1.2"/>
          <line x1="7" y1="10" x2="13" y2="10" stroke="currentColor" stroke-width="0.6"/>
        </svg>
      </div>
      <div id="bug-list" style="font-size:9.5px;line-height:1.45;max-height:180px;overflow-y:auto;">—</div>
    </div>
    <div class="card" style="border-left:2px solid var(--wren);">
      <h2>WREN · <span class="accent">EVOLUTION LOOP</span></h2>
      <div id="evo-status" style="font-size:11px;color:var(--dim);margin-bottom:4px;"></div>
      <div id="evo-recent" style="font-size:10px;line-height:1.5;"></div>
    </div>
    <div class="card">
      <h2>NODES</h2>
      <div id="nodes">—</div>
    </div>
    <div class="card" style="border-left:2px solid var(--gold);">
      <h2>PLATFORMS · <span class="accent">SHOPS + TRADERS</span></h2>
      <div id="platforms-tabs" style="display:flex;gap:4px;margin-bottom:8px;font-size:10px;">
        <button data-tab="shops" class="pf-tab active">Shops · 16</button>
        <button data-tab="venues" class="pf-tab">Trading · 3</button>
        <button data-tab="dashes" class="pf-tab">Dashes · 7</button>
      </div>
      <div id="platforms-grid" style="display:grid;grid-template-columns:repeat(2,1fr);gap:4px;font-size:9.5px;"></div>
      <div id="platform-shelf" style="margin-top:8px;padding:8px;background:rgba(0,0,0,0.35);border-radius:5px;font-size:10px;display:none;"></div>
    </div>
    <div class="card">
      <h2>ROUTING · <span class="accent">TARGET WIRES TO</span></h2>
      <div style="font-size: 10.5px; color: var(--dim); line-height: 1.7;">
        <div><b style="color: var(--tp);">tp</b> → POST /msg on 192.168.1.74:9100</div>
        <div><b style="color: var(--wren);">wren</b> → bridge JSONL + her local agent</div>
        <div><b style="color: var(--hermes);">hermes</b> → hermes_bridge JSONL + F47</div>
        <div><b style="color: var(--iquest);">iquest</b> → F47 iquest_msg stamp</div>
        <div><b style="color: var(--claude);">hq</b> → shared node_inbox</div>
        <div><b style="color: var(--gold);">all</b> → all of the above + F47 announce</div>
      </div>
    </div>
    <div class="card">
      <h2>NOTES</h2>
      <div style="font-size: 10.5px; color: var(--dim); line-height: 1.6;">
        Real-money gates unchanged. Boardroom is comms only — no orders, no gate flips.<br><br>
        MIC: browser asks for permission on first use. Whisper 16k on qsb_voice_server :8795.<br><br>
        SPEAK on any row uses member's voice (Wren=F3, Claude=M1, Hermes=M2).
      </div>
    </div>
  </aside>

</main>

<script>
let MEMBERS = {};
let filterFrom = null;   // null = all
let mediaRecorder = null; let recChunks = [];
let lastCounts = {};     // for seat-burst on new msg
let lastTimelineTop = ""; // for row-fresh highlight

// SVG avatars — one distinct motif per member (Ross's ask for better avatars)
const AVATARS = {
  ross: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5">
    <!-- Ship wheel: owner + boat life -->
    <circle cx="20" cy="20" r="12" />
    <circle cx="20" cy="20" r="4" fill="currentColor" opacity="0.6"/>
    <line x1="20" y1="4" x2="20" y2="14"/>
    <line x1="20" y1="26" x2="20" y2="36"/>
    <line x1="4" y1="20" x2="14" y2="20"/>
    <line x1="26" y1="20" x2="36" y2="20"/>
    <line x1="8.7" y1="8.7" x2="14.5" y2="14.5"/>
    <line x1="25.5" y1="25.5" x2="31.3" y2="31.3"/>
    <line x1="31.3" y1="8.7" x2="25.5" y2="14.5"/>
    <line x1="14.5" y1="25.5" x2="8.7" y2="31.3"/>
  </svg>`,
  claude: `<svg viewBox="0 0 40 40" fill="none">
    <!-- Amber orb + ring -->
    <circle cx="20" cy="20" r="14" stroke="currentColor" stroke-width="0.8" opacity="0.4"/>
    <circle cx="20" cy="20" r="9" fill="currentColor" opacity="0.85"/>
    <circle cx="16" cy="16" r="3" fill="rgba(255,255,255,0.55)"/>
    <circle cx="20" cy="20" r="14" stroke="currentColor" stroke-width="0.6" stroke-dasharray="2 4"/>
  </svg>`,
  wren: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round">
    <!-- Engineer's wrench (Wren's own avatar) -->
    <path d="M 12 8 L 12 4 A 4 4 0 0 1 20 4 L 20 8 L 18 8 L 18 6 A 2 2 0 0 0 14 6 L 14 8 Z" fill="currentColor" stroke="none"/>
    <rect x="14" y="8" width="4" height="20" fill="currentColor" stroke="none" opacity="0.85"/>
    <path d="M 12 32 L 12 36 A 4 4 0 0 0 20 36 L 20 32 L 18 32 L 18 34 A 2 2 0 0 1 14 34 L 14 32 Z" fill="currentColor" stroke="none"/>
    <circle cx="16" cy="20" r="1.2" fill="#fff"/>
  </svg>`,
  hermes: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5">
    <!-- Winged shield: watcher / CEO -->
    <path d="M 20 6 L 30 12 L 30 22 Q 30 30 20 36 Q 10 30 10 22 L 10 12 Z" fill="currentColor" opacity="0.25"/>
    <path d="M 20 6 L 30 12 L 30 22 Q 30 30 20 36 Q 10 30 10 22 L 10 12 Z"/>
    <!-- wings -->
    <path d="M 10 15 Q 4 12 2 16 Q 5 15 8 18" stroke-width="1.2" opacity="0.85"/>
    <path d="M 30 15 Q 36 12 38 16 Q 35 15 32 18" stroke-width="1.2" opacity="0.85"/>
    <circle cx="20" cy="20" r="3" fill="currentColor"/>
  </svg>`,
  iquest: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
    <!-- Code brackets < / > -->
    <path d="M 14 12 L 6 20 L 14 28"/>
    <path d="M 26 12 L 34 20 L 26 28"/>
    <line x1="22" y1="10" x2="18" y2="30" stroke-dasharray="0" opacity="0.7"/>
  </svg>`,
  thinkpad: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5">
    <!-- Laptop with dot (CEO node) -->
    <rect x="6" y="10" width="28" height="18" rx="1.5"/>
    <line x1="2" y1="30" x2="38" y2="30" stroke-width="2.2"/>
    <circle cx="20" cy="19" r="4" fill="currentColor" opacity="0.75"/>
    <circle cx="20" cy="19" r="1.5" fill="#0f172a"/>
  </svg>`,
  acer: `<svg viewBox="0 0 40 40" fill="none">
    <!-- Windows-style 4-pane -->
    <rect x="6"  y="6"  width="12" height="12" fill="currentColor" opacity="0.85"/>
    <rect x="22" y="6"  width="12" height="12" fill="currentColor" opacity="0.65"/>
    <rect x="6"  y="22" width="12" height="12" fill="currentColor" opacity="0.65"/>
    <rect x="22" y="22" width="12" height="12" fill="currentColor" opacity="0.85"/>
  </svg>`,
  hq: `<svg viewBox="0 0 40 40" fill="none">
    <circle cx="20" cy="20" r="14" stroke="currentColor" stroke-width="0.8" opacity="0.4"/>
    <circle cx="20" cy="20" r="9" fill="currentColor" opacity="0.85"/>
    <circle cx="16" cy="16" r="3" fill="rgba(255,255,255,0.55)"/>
  </svg>`,
  tp: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5">
    <rect x="6" y="10" width="28" height="18" rx="1.5"/>
    <line x1="2" y1="30" x2="38" y2="30" stroke-width="2.2"/>
    <circle cx="20" cy="19" r="4" fill="currentColor" opacity="0.75"/>
  </svg>`,
  sage: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.4">
    <!-- Owl-eye pair for auditor -->
    <circle cx="14" cy="20" r="6"/>
    <circle cx="26" cy="20" r="6"/>
    <circle cx="14" cy="20" r="2" fill="currentColor"/>
    <circle cx="26" cy="20" r="2" fill="currentColor"/>
    <path d="M 8 12 Q 14 6 20 12" stroke-width="1.6"/>
    <path d="M 20 12 Q 26 6 32 12" stroke-width="1.6"/>
  </svg>`,
  auger: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.4">
    <circle cx="14" cy="20" r="6"/><circle cx="26" cy="20" r="6"/>
    <circle cx="14" cy="20" r="2" fill="currentColor"/><circle cx="26" cy="20" r="2" fill="currentColor"/>
  </svg>`,
  forge: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.6">
    <!-- Hammer -->
    <rect x="8" y="10" width="18" height="10" rx="1"/>
    <line x1="24" y1="15" x2="34" y2="25" stroke-width="2.4"/>
  </svg>`,
  helm: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5">
    <!-- Ross-facing brain: compass rose -->
    <circle cx="20" cy="20" r="12"/>
    <path d="M 20 6 L 22 20 L 20 34 L 18 20 Z" fill="currentColor" opacity="0.7"/>
    <path d="M 6 20 L 20 22 L 34 20 L 20 18 Z" fill="currentColor" opacity="0.5"/>
  </svg>`,
  pip: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.6">
    <!-- Assistant: notepad + spark -->
    <rect x="12" y="8" width="16" height="22" rx="1.5"/>
    <line x1="15" y1="14" x2="25" y2="14"/>
    <line x1="15" y1="18" x2="23" y2="18"/>
    <line x1="15" y1="22" x2="25" y2="22"/>
    <circle cx="30" cy="12" r="2" fill="currentColor"/>
  </svg>`,
  mira: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5">
    <!-- Reviewer: mirror with reflection -->
    <ellipse cx="20" cy="18" rx="10" ry="12"/>
    <ellipse cx="20" cy="18" rx="6" ry="8" fill="currentColor" opacity="0.4"/>
    <line x1="20" y1="30" x2="20" y2="36"/>
    <line x1="14" y1="36" x2="26" y2="36" stroke-width="2"/>
  </svg>`,
  iris: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5">
    <!-- Galaxy AI: eye + pulse -->
    <path d="M 4 20 Q 20 8 36 20 Q 20 32 4 20 Z"/>
    <circle cx="20" cy="20" r="5" fill="currentColor" opacity="0.7"/>
    <circle cx="20" cy="20" r="2" fill="#0f172a"/>
  </svg>`,
  receptionist: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.5">
    <!-- Reception: headset -->
    <path d="M 8 22 Q 8 8 20 8 Q 32 8 32 22"/>
    <rect x="6" y="20" width="6" height="10" rx="2" fill="currentColor" opacity="0.7"/>
    <rect x="28" y="20" width="6" height="10" rx="2" fill="currentColor" opacity="0.7"/>
    <path d="M 32 26 Q 32 32 24 32"/>
    <circle cx="22" cy="32" r="2" fill="currentColor"/>
  </svg>`,
  system: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="20" cy="20" r="10"/><line x1="20" y1="4" x2="20" y2="10"/><line x1="20" y1="30" x2="20" y2="36"/></svg>`,
  unknown: `<svg viewBox="0 0 40 40" fill="none" stroke="currentColor" stroke-width="1.4"><circle cx="20" cy="20" r="10"/><text x="20" y="25" text-anchor="middle" font-size="14" fill="currentColor" stroke="none">?</text></svg>`,
};

function avatarSvg(id) { return AVATARS[id] || AVATARS['unknown']; }

function esc(s) { return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

async function tick() {
  try {
    const d = await (await fetch('/status')).json();
    MEMBERS = d.members || {};
    document.getElementById('ts').textContent = d.ts;

    // seats — custom SVG avatars + burst animation on new msg + signature per-member animation
    const counts = d.counts || {};
    const seatOrder = ['ross','claude','helm','auger','wren','hermes','forge','sage','pip','mira','iris','receptionist','iquest','tp','acer'];
    const topMsg = (d.timeline || [])[0] || {};
    const topFrom = (topMsg.from || '').toLowerCase();
    const seats = seatOrder.map(id => {
      const m = MEMBERS[id] || {label: id, color: '#666', role: ''};
      const cnt = counts[id] || 0;
      const prev = lastCounts[id] || 0;
      const bumped = cnt > prev;
      const active = filterFrom === id ? 'active' : '';
      const online = cnt > 0 ? 'online' : '';
      const posted = bumped ? 'just-posted' : '';
      const speaking = topFrom === id ? 'speaking' : '';
      const pres = (d.presence || {})[id] || {};
      const state = pres.state || 'offline';
      return `<div class="seat ${active} ${online} ${posted} ${speaking}" style="color:${m.color};" data-id="${id}">
        <div class="avatar-svg">${avatarSvg(id)}</div>
        <div class="info"><div class="nm">${m.label}</div><div class="rl">${m.role}</div></div>
        <div class="cnt ${bumped?'bumped':''}">${cnt}</div>
        <div class="presence-dot ${state}" title="${state}${pres.last_seen_s!=null?' — last seen '+pres.last_seen_s+'s ago':''}"></div>
      </div>`;
    }).join('');
    document.getElementById('seats').innerHTML = seats;
    document.querySelectorAll('.seat').forEach(el => {
      el.addEventListener('click', () => {
        const id = el.dataset.id;
        filterFrom = (filterFrom === id) ? null : id;
        render(d);
      });
    });
    // remove bumped class after animation
    setTimeout(() => {
      document.querySelectorAll('.seat.just-posted').forEach(el => el.classList.remove('just-posted'));
      document.querySelectorAll('.cnt.bumped').forEach(el => el.classList.remove('bumped'));
    }, 1800);
    lastCounts = {...counts};

    render(d);

    // channels
    const ch = d.channels || {};
    document.getElementById('channels').innerHTML = Object.entries(ch).map(([k,v]) => `
      <div class="kv"><span class="k">${k}</span><span class="v ${v ? 'ok':'err'}">${v?'✓':'off'}</span></div>`).join('');

    // nodes
    const tp = d.tp || {};
    document.getElementById('nodes').innerHTML = `
      <div class="kv"><span class="k">HQ (self)</span><span class="v ok">up</span></div>
      <div class="kv"><span class="k">ThinkPad</span><span class="v ${tp.reachable?'ok':'err'}">${tp.reachable?'up':'unreachable'}</span></div>`;

    // WREN · MIND — persistent thoughts, mood, unresolved
    const wm = d.wren_mind || {};
    if (wm.exists) {
      const ageEl = document.getElementById('mind-age');
      const moodEl = document.getElementById('mind-mood');
      const thEl = document.getElementById('mind-thoughts');
      const unEl = document.getElementById('mind-unresolved');
      if (ageEl) ageEl.textContent = `· age ${wm.age_days}d · ${(wm.counts||{}).thoughts||0} thoughts · ${(wm.counts||{}).growth_milestones||0} milestones`;
      const cm = wm.current_mood || {};
      if (moodEl) moodEl.innerHTML = `mood: <b>${cm.mood||'—'}</b>  energy ${cm.energy||0}/9  <span style="color:var(--dim)">${(cm.reason||'').slice(0,80)}</span>`;
      const th = (wm.last_thoughts||[]).slice(0,4).map(t => {
        const ts = (t.ts||'').slice(11,16);
        const kind = t.kind||'?';
        const kindColor = kind==='reflection'?'#8ec5ff':kind==='hunch'?'#c9b1ff':kind==='resolved'?'#7bd88f':kind==='todo'?'#ffcf6b':'var(--dim)';
        return `<div style="margin:3px 0;"><span style="color:${kindColor};font-size:9px;">[${kind}]</span> <span style="color:var(--fg);">${(t.text||'').slice(0,140)}</span> <span style="color:var(--dim);font-size:9px;">${ts}</span></div>`;
      }).join('');
      if (thEl) thEl.innerHTML = th || '<span style="color:var(--dim);">no thoughts yet — she wakes soon</span>';
      const un = (wm.unresolved||[]).slice(0,3).map(u => {
        const opener = u.opened_by||'self';
        return `<div style="margin:2px 0;">↻ <span style="color:var(--gold);">${(u.text||'').slice(0,130)}</span> <span style="color:var(--dim);font-size:9px;">(${opener})</span></div>`;
      }).join('');
      if (unEl) unEl.innerHTML = un || '<span style="color:var(--dim);">no open todos</span>';
    }

    // PLATFORMS · shops + trading venues + tower dashes (2026-07-03)
    renderPlatforms(d.platforms || {});

    // NETWORK · NIGHTHAWK M1 — live router state (signal / clients / temp / SIM)
    const nw = d.network || {};
    const netSignalChip = document.getElementById('net-signal-chip');
    const netBody = document.getElementById('net-body');
    const netClients = document.getElementById('net-clients');
    if (netSignalChip) {
      const rssi = nw.rssi;
      const bars = rssi==null?'—':(rssi>-65?'●●●●● strong':rssi>-75?'●●●●○ good':rssi>-85?'●●●○○ ok':rssi>-95?'●●○○○ weak':'●○○○○ poor');
      netSignalChip.textContent = `RSSI ${rssi||'?'}dBm · ${bars}`;
    }
    if (netBody) {
      if (nw.err) {
        netBody.innerHTML = `<div style="color:var(--err);">unreachable: ${nw.err}</div>`;
      } else {
        const upDays = Math.floor((nw.uptime_s||0)/86400);
        const upHrs = Math.floor(((nw.uptime_s||0)%86400)/3600);
        const upMin = Math.floor(((nw.uptime_s||0)%3600)/60);
        const upStr = upDays>0?`${upDays}d ${upHrs}h`:upHrs>0?`${upHrs}h ${upMin}m`:`${upMin}m`;
        const tempColor = (nw.temp_c||0) > 65 ? 'var(--err)' : (nw.temp_c||0) > 55 ? 'var(--warn)' : 'var(--ok)';
        netBody.innerHTML = `
          <div style="display:flex;justify-content:space-between;"><span style="color:var(--dim);">device</span><span>${nw.device_name||'?'} · <span style="color:var(--dim);">${nw.firmware||''}</span></span></div>
          <div style="display:flex;justify-content:space-between;"><span style="color:var(--dim);">connection</span><span style="color:${nw.connection==='Connected'?'var(--ok)':'var(--err)'};">${nw.connection||'?'} · ${nw.network_type||'?'}</span></div>
          <div style="display:flex;justify-content:space-between;"><span style="color:var(--dim);">signal</span><span>RSSI ${nw.rssi||'?'} · RSRP ${nw.rsrp||'?'} · SINR ${nw.sinr||'?'}</span></div>
          <div style="display:flex;justify-content:space-between;"><span style="color:var(--dim);">SIM</span><span>${nw.sim_status||'?'}</span></div>
          <div style="display:flex;justify-content:space-between;"><span style="color:var(--dim);">uptime</span><span>${upStr} · <span style="color:${tempColor};">${nw.temp_c||'?'}°C</span></span></div>
          <div style="display:flex;justify-content:space-between;"><span style="color:var(--dim);">SMS</span><span>${nw.sms_unread||0} unread</span></div>
          <div style="display:flex;justify-content:space-between;"><span style="color:var(--dim);">clients</span><span>${nw.client_count||0}</span></div>`;
      }
    }
    if (netClients && (nw.clients||[]).length) {
      const rows = nw.clients.map(c => {
        return `<div style="display:flex;justify-content:space-between;padding:2px 0;border-bottom:1px solid rgba(255,255,255,0.03);">
          <span>${c.name||'?'}</span>
          <span style="font-family:ui-monospace,monospace;">${c.ip||'?'} · ${c.type||'?'}</span>
        </div>`;
      }).join('');
      netClients.innerHTML = rows;
    }

    // TRADING · VENUES — 3 trading platforms with LIVE PnL from TP's /feed
    const tpFeed = d.tp_feed || {};
    const venuePnlMap = tpFeed.venue_pnl || {};
    const tradeChip = document.getElementById('trade-pnl-chip');
    const tradeList = document.getElementById('trading-venues');
    const venueMeta = {
      oanda_practice:   {name:'OANDA Practice', color:'#22d3ee', url:'https://trade.oanda.com/', family:'forex+cfd'},
      binance_testnet:  {name:'Binance Testnet', color:'#eab308', url:'https://testnet.binance.vision/', family:'crypto'},
      alpaca_paper:     {name:'Alpaca Paper',    color:'#a78bfa', url:'https://app.alpaca.markets/paper/dashboard/overview', family:'stocks'},
    };
    let totalPnl = 0;
    Object.values(venuePnlMap).forEach(v => { totalPnl += v; });
    if (tradeChip) tradeChip.textContent = totalPnl ? `Σ £${totalPnl.toFixed(2)}` : '—';
    if (tradeList) {
      const rows = Object.entries(venueMeta).map(([slug, m]) => {
        const pnl = venuePnlMap[slug];
        const pnlStr = (pnl != null) ? `£${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}` : '—';
        const pnlColor = (pnl == null) ? 'var(--dim)' : (pnl >= 0 ? '#4ade80' : '#ef4444');
        return `<div style="margin:4px 0;padding:5px 8px;background:rgba(255,255,255,0.03);border-left:2px solid ${m.color};border-radius:3px;cursor:pointer;" onclick="window.open('${m.url}','_blank')" title="click to open ${m.name}">
          <div style="display:flex;justify-content:space-between;">
            <span style="color:${m.color};font-weight:600;font-size:10px;">${m.name}</span>
            <span style="color:${pnlColor};font-family:ui-monospace,monospace;font-size:10px;">${pnlStr}</span>
          </div>
          <div style="color:var(--dim);font-size:8.5px;">${m.family} · paper mode</div>
        </div>`;
      }).join('');
      tradeList.innerHTML = rows;
    }

    // EVENT STREAM TICKER — narrative feed of recent tower events
    const es = d.event_stream || [];
    const esEl = document.getElementById('event-stream-content');
    if (esEl) {
      const eventColors = {wren:'#f97316', tp:'#22d3ee', 'thinkpad-ceo':'#22d3ee', acer:'#f59e0b', hq_claude:'#eab308', claude:'#eab308', hermes:'#a78bfa', forge:'#e879f9'};
      const eventKindGlyph = {cycle:'⟳', inbox:'✉', bug:'🐞', chat:'💬'};
      esEl.innerHTML = es.slice(0, 12).map(e => {
        const c = eventColors[(e.who||'').toLowerCase()] || '#94a3b8';
        const glyph = eventKindGlyph[e.kind] || '·';
        const ts = (e.ts||'').slice(11,16);
        return `<span style="margin-right:14px;"><span style="color:var(--dim);">${ts}</span> ${glyph} <span style="color:${c};">${e.who}</span> <span style="color:var(--text);">${(e.text||'').slice(0,60)}</span></span>`;
      }).join(' · ') || '<span style="color:var(--dim);">nothing yet</span>';
    }

    // CHAIN · PROGRESS — Wren's active chain orchestrator state
    const cp = d.chain_progress || {};
    const chains = cp.chains || [];
    const cLive = document.getElementById('chain-live-count');
    if (cLive) {
      const running = chains.filter(c => c.status === 'running').length;
      const passed = chains.filter(c => c.status === 'complete').length;
      const failed = chains.filter(c => c.status === 'verify_failed').length;
      cLive.textContent = `${running}▸ ${passed}✓ ${failed}✗`;
    }
    const cpList = document.getElementById('chain-progress-list');
    if (cpList) {
      cpList.innerHTML = chains.map(c => {
        const statusColor = c.status==='complete'?'#4ade80':c.status==='verify_failed'?'#ef4444':c.status==='running'?'#f97316':'#94a3b8';
        const pct = c.total > 0 ? Math.round((c.done/c.total)*100) : 0;
        const label = c.status==='complete'?'✓ done':c.status==='verify_failed'?'✗ blocked':c.status==='running'?'▸ running':'○ pending';
        return `<div style="margin:4px 0;padding:5px 7px;background:rgba(255,255,255,0.02);border-left:2px solid ${statusColor};border-radius:3px;">
          <div style="display:flex;justify-content:space-between;">
            <span style="color:${statusColor};font-weight:600;font-size:10px;">${label}</span>
            <span style="color:var(--dim);font-family:ui-monospace,monospace;font-size:9px;">${c.done}/${c.total} · ${pct}%</span>
          </div>
          <div style="color:var(--text);font-size:9.5px;margin-top:2px;">${c.id.slice(0,32)}</div>
          <div style="color:var(--dim);font-size:8.5px;">${c.status==='running'?'stage: '+c.active_kind:c.title.slice(0,60)}</div>
          <div style="background:rgba(0,0,0,0.4);height:3px;border-radius:2px;margin-top:3px;overflow:hidden;"><div style="background:${statusColor};height:100%;width:${pct}%;"></div></div>
        </div>`;
      }).join('') || '<div style="color:var(--dim);font-size:10px;">no chains yet</div>';
    }

    // AVATAR · COMPETITION — TP-CEO reminded me: each Council member picks a theme+color room
    const ac = d.avatar_competition || {};
    const avComp = document.getElementById('avatar-comp');
    if (avComp) {
      const themes = ac.themes || {};
      const rows = Object.entries(themes).map(([id, t]) => {
        return `<div style="padding:6px 8px;background:${t.color}22;border-left:2px solid ${t.color};border-radius:3px;">
          <div style="color:${t.color};font-weight:600;font-size:10px;">${t.member}</div>
          <div style="color:var(--text);font-size:9.5px;">${t.theme}</div>
          <div style="color:var(--dim);font-size:8.5px;font-family:ui-monospace,monospace;">${t.color} · ${t.hex_name||''}</div>
        </div>`;
      }).join('');
      avComp.innerHTML = rows || '<div style="color:var(--dim);font-size:10px;">no themes registered</div>';
    }

    // SANDBOX · PLAYGROUND — Ross "sandbox animations in her dash you have a sandbox as well"
    const sb = d.sandbox_playground || {};
    const sbCount = document.getElementById('sb-count');
    const sbList = document.getElementById('sandbox-list');
    if (sbCount) sbCount.textContent = `${(sb.sandboxes||[]).reduce((a,b) => a+(b.count||0), 0)} files · ${sb.backups_count||0} backups`;
    if (sbList) {
      const rows = (sb.sandboxes || []).map(box => {
        const files = (box.files||[]).slice(0,3).map(f => `<div style="color:var(--text);font-size:9px;font-family:ui-monospace,monospace;">  ${f.name} · ${f.size}B · ${(f.mtime||'').slice(11,16)}</div>`).join('');
        return `<div style="margin:4px 0;padding:4px 6px;background:rgba(255,255,255,0.03);border-left:2px solid var(--gold);border-radius:3px;">
          <div style="color:var(--gold);font-weight:600;font-size:10px;">${box.owner} · ${box.count} files</div>
          ${files || '<div style="color:var(--dim);font-size:9px;">empty</div>'}
        </div>`;
      }).join('');
      sbList.innerHTML = rows || '<div style="color:var(--dim);font-size:10px;">no sandboxes yet</div>';
    }

    // TRAINING · CHAINS — Wren chain training progress live
    const tr = d.training_scoreboard || {};
    const trCount = document.getElementById('train-count');
    const trList = document.getElementById('training-list');
    if (trCount) trCount.textContent = `${tr.passed||0} passed · ${tr.failed||0} failed`;
    if (trList) {
      const rows = (tr.chains || []).map(c => {
        const statusColor = c.status==='complete'?'#4ade80':c.status==='verify_failed'?'#ef4444':c.status==='running'?'#f97316':'#94a3b8';
        const label = c.status==='complete'?'✓':c.status==='verify_failed'?'✗':c.status==='running'?'●':'○';
        return `<div style="margin:3px 0;padding:3px 6px;background:rgba(255,255,255,0.02);border-left:2px solid ${statusColor};border-radius:3px;">
          <div style="color:${statusColor};font-size:9.5px;">${label} ${c.done}/${c.total} · ${c.id.slice(0,32)}</div>
          <div style="color:var(--dim);font-size:8.5px;">${(c.title||'').slice(0,60)}</div>
        </div>`;
      }).join('');
      trList.innerHTML = rows || '<div style="color:var(--dim);font-size:10px;">no chains yet</div>';
    }

    // BUG · WATCH — Ross "i dont see her catching bugs"
    const bw = d.bug_watch || {};
    const bugCountEl = document.getElementById('bug-count');
    if (bugCountEl) bugCountEl.textContent = `${bw.today||0} today · ${bw.total||0} total`;
    const bugListEl = document.getElementById('bug-list');
    if (bugListEl) {
      const rows = (bw.recent || []).map(b => {
        const sevColor = b.severity==='high'?'#ef4444':b.severity==='med'?'#f59e0b':'#94a3b8';
        return `<div style="margin:4px 0;padding:4px 6px;background:rgba(255,255,255,0.02);border-left:2px solid ${sevColor};border-radius:3px;">
          <div style="color:${sevColor};font-size:9px;">${b.severity} · ${b.source} · ${b.ts.slice(11)}</div>
          <div style="color:var(--dim);font-size:9px;font-family:ui-monospace,monospace;">${b.file}</div>
          <div style="color:var(--text);font-size:9.5px;">${(b.snippet||'').replace(/</g,'&lt;').slice(0,90)}</div>
        </div>`;
      }).join('');
      bugListEl.innerHTML = rows || '<div style="color:var(--dim);font-size:10px;">no catches yet — Wren cycles bug_catcher every ~180s</div>';
    }

    // WREN · EVOLUTION LOOP — cycles today, recent job kinds
    const we = d.wren_evolution || {};
    const evoS = document.getElementById('evo-status');
    const evoR = document.getElementById('evo-recent');
    if (evoS) {
      const gate = we.enabled ? '<span style="color:#7bd88f">● LOOP LIVE</span>' : '<span style="color:#ff7b7b">● GATED OFF</span>';
      evoS.innerHTML = `${gate}  ·  ${we.cycles_today||0} cycles today`;
    }
    if (evoR) {
      const rows = (we.recent||[]).map(r => {
        const ts = (r.ts||'').slice(11,16);
        const wall = r.wall_s!=null ? r.wall_s+'s' : '';
        return `<div style="margin:2px 0;"><span style="color:var(--wren);">#${r.cycle}</span> <span style="color:var(--fg);">${r.kind||'?'}</span> <span style="color:var(--dim);font-size:9px;">${wall} · ${ts}</span><br><span style="color:var(--dim);padding-left:14px;">${(r.head||'').slice(0,110)}</span></div>`;
      }).join('');
      evoR.innerHTML = rows || '<span style="color:var(--dim);">no cycles yet — first one due in <90s</span>';
    }

    // ═══ HERO AVATAR ROW (2026-07-03 massive upgrade) ═══
    renderHero(d.council_moods || {}, d);
    renderCouncilSynth((d.council_moods || {}).council);
    renderMeetingTimer(d.meeting_timer || {});
    // ═══ SPEAKING SPOTLIGHT — 2026-07-04 fill the empty band, remove dupes ═══
    renderSpotlight(d);

  } catch (e) {
    document.getElementById('ts').textContent = 'fetch err: ' + e.message;
  }
}

// Custom SVGs per member (kept minimal — colored by currentColor)
const HERO_SVG = {
  ross:   '<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="24" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="30" cy="30" r="4" fill="currentColor"/><line x1="30" y1="4" x2="30" y2="16" stroke="currentColor" stroke-width="2"/><line x1="30" y1="44" x2="30" y2="56" stroke="currentColor" stroke-width="2"/><line x1="4" y1="30" x2="16" y2="30" stroke="currentColor" stroke-width="2"/><line x1="44" y1="30" x2="56" y2="30" stroke="currentColor" stroke-width="2"/><line x1="12" y1="12" x2="20" y2="20" stroke="currentColor" stroke-width="2"/><line x1="40" y1="40" x2="48" y2="48" stroke="currentColor" stroke-width="2"/><line x1="48" y1="12" x2="40" y2="20" stroke="currentColor" stroke-width="2"/><line x1="20" y1="40" x2="12" y2="48" stroke="currentColor" stroke-width="2"/></svg>',
  claude: '<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="26" fill="none" stroke="currentColor" stroke-width="1.5" opacity="0.5"/><circle cx="30" cy="30" r="14" fill="currentColor" opacity="0.9"/><circle cx="30" cy="30" r="6" fill="#0f172a"/></svg>',
  wren:   '<svg viewBox="0 0 60 60"><path d="M15 45 L30 30 L45 45 M22 22 A8 8 0 1 1 38 22 A8 8 0 1 1 22 22" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"/><circle cx="30" cy="18" r="3" fill="currentColor"/></svg>',
  hermes: '<svg viewBox="0 0 60 60"><path d="M30 8 L48 18 L48 32 Q48 46 30 54 Q12 46 12 32 L12 18 Z" fill="currentColor" opacity="0.85"/><path d="M20 22 Q10 20 8 30 M40 22 Q50 20 52 30" stroke="currentColor" stroke-width="1.6" fill="none"/><circle cx="30" cy="28" r="4" fill="#0f172a"/></svg>',
  iquest: '<svg viewBox="0 0 60 60"><path d="M18 12 L10 12 L10 48 L18 48 M42 12 L50 12 L50 48 L42 48 M22 30 L28 24 L30 32 L32 24 L38 30" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  tp:     '<svg viewBox="0 0 60 60"><rect x="8" y="14" width="44" height="28" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><rect x="12" y="18" width="36" height="20" fill="currentColor" opacity="0.55"/><rect x="4" y="42" width="52" height="6" rx="2" fill="currentColor" opacity="0.85"/><circle cx="30" cy="45" r="1.5" fill="#0f172a"/></svg>',
  acer:   '<svg viewBox="0 0 60 60"><rect x="8" y="8" width="20" height="20" fill="currentColor" opacity="0.85"/><rect x="32" y="8" width="20" height="20" fill="currentColor" opacity="0.7"/><rect x="8" y="32" width="20" height="20" fill="currentColor" opacity="0.6"/><rect x="32" y="32" width="20" height="20" fill="currentColor" opacity="0.85"/></svg>',
  helm:   '<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="20" fill="none" stroke="currentColor" stroke-width="2"/><path d="M 30 8 L 34 30 L 30 52 L 26 30 Z" fill="currentColor" opacity="0.7"/><path d="M 8 30 L 30 34 L 52 30 L 30 26 Z" fill="currentColor" opacity="0.5"/></svg>',
  auger:  '<svg viewBox="0 0 60 60"><circle cx="22" cy="30" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="42" cy="30" r="10" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="22" cy="30" r="4" fill="currentColor"/><circle cx="42" cy="30" r="4" fill="currentColor"/></svg>',
  forge:  '<svg viewBox="0 0 60 60"><rect x="10" y="18" width="26" height="14" rx="1" fill="currentColor" opacity="0.8"/><line x1="32" y1="24" x2="50" y2="42" stroke="currentColor" stroke-width="4" stroke-linecap="round"/><circle cx="14" cy="46" r="3" fill="currentColor" opacity="0.6"/><circle cx="20" cy="48" r="2" fill="currentColor" opacity="0.5"/></svg>',
  sage:   '<svg viewBox="0 0 60 60"><circle cx="22" cy="28" r="9" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="38" cy="28" r="9" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="22" cy="28" r="3" fill="currentColor"/><circle cx="38" cy="28" r="3" fill="currentColor"/><path d="M 12 16 Q 22 8 32 16 M 28 16 Q 38 8 48 16" stroke="currentColor" stroke-width="2" fill="none"/></svg>',
  pip:    '<svg viewBox="0 0 60 60"><rect x="18" y="10" width="24" height="34" rx="2" fill="none" stroke="currentColor" stroke-width="2"/><line x1="22" y1="20" x2="38" y2="20" stroke="currentColor" stroke-width="1.5"/><line x1="22" y1="26" x2="34" y2="26" stroke="currentColor" stroke-width="1.5"/><line x1="22" y1="32" x2="38" y2="32" stroke="currentColor" stroke-width="1.5"/><circle cx="46" cy="16" r="3" fill="currentColor"/></svg>',
  mira:   '<svg viewBox="0 0 60 60"><ellipse cx="30" cy="26" rx="14" ry="18" fill="none" stroke="currentColor" stroke-width="2"/><ellipse cx="30" cy="26" rx="8" ry="12" fill="currentColor" opacity="0.35"/><line x1="30" y1="44" x2="30" y2="54" stroke="currentColor" stroke-width="2"/><line x1="20" y1="54" x2="40" y2="54" stroke="currentColor" stroke-width="3"/></svg>',
  iris:   '<svg viewBox="0 0 60 60"><path d="M 6 30 Q 30 12 54 30 Q 30 48 6 30 Z" fill="none" stroke="currentColor" stroke-width="2"/><circle cx="30" cy="30" r="8" fill="currentColor" opacity="0.7"/><circle cx="30" cy="30" r="3" fill="#0f172a"/></svg>',
  receptionist: '<svg viewBox="0 0 60 60"><path d="M 12 32 Q 12 12 30 12 Q 48 12 48 32" fill="none" stroke="currentColor" stroke-width="2"/><rect x="8" y="30" width="10" height="14" rx="3" fill="currentColor" opacity="0.75"/><rect x="42" y="30" width="10" height="14" rx="3" fill="currentColor" opacity="0.75"/><path d="M 48 38 Q 48 48 36 48" stroke="currentColor" stroke-width="2" fill="none"/><circle cx="33" cy="48" r="3" fill="currentColor"/></svg>',
};

let _platformTab = 'shops';
let _platformData = {};
function renderPlatforms(p) {
  _platformData = p;
  const grid = document.getElementById('platforms-grid');
  if (!grid) return;
  const list = _platformTab === 'shops' ? (p.shops||[])
             : _platformTab === 'venues' ? (p.trading_venues||[])
             : (p.tower_dashes||[]);
  grid.innerHTML = list.map(item => `
    <div class="pf-card" data-slug="${item.slug}" data-url="${item.url||''}" title="${item.name}">
      <div style="font-weight:600;color:var(--gold);">${item.name}</div>
      <div style="color:var(--dim);font-size:9px;">${item.cat||''}</div>
    </div>`).join('');
  // wire clicks — click opens shelf with detail, dbl-click opens the URL
  document.querySelectorAll('.pf-card').forEach(el => {
    el.addEventListener('click', () => showPlatformShelf(el.dataset.slug));
    el.addEventListener('dblclick', () => {
      if (el.dataset.url) window.open(el.dataset.url, '_blank');
    });
  });
}
function showPlatformShelf(slug) {
  const p = _platformData;
  const all = [...(p.shops||[]), ...(p.trading_venues||[]), ...(p.tower_dashes||[])];
  const item = all.find(x => x.slug === slug);
  const shelf = document.getElementById('platform-shelf');
  if (!item || !shelf) return;
  shelf.style.display = 'block';
  shelf.innerHTML = `
    <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
      <span style="color:var(--gold);font-weight:600;">${item.name}</span>
      <span style="color:var(--dim);font-size:9px;">${item.cat||''}</span>
    </div>
    <div style="color:var(--text);font-size:10px;margin-bottom:4px;word-break:break-all;">
      <a href="${item.url}" target="_blank" style="color:var(--claude);text-decoration:none;">${item.url}</a>
    </div>
    ${item.mode ? `<div style="color:var(--dim);font-size:9px;">mode: ${item.mode}</div>` : ''}
    ${item.netlify ? `<div style="color:var(--dim);font-size:9px;">netlify: ${item.netlify}</div>` : ''}
    <div style="margin-top:6px;">
      <button onclick="window.open('${item.url}','_blank')" style="background:rgba(255,255,255,0.06);border:1px solid var(--gold);color:var(--gold);padding:4px 10px;border-radius:4px;font-size:10px;cursor:pointer;">Open →</button>
      <button onclick="document.getElementById('platform-shelf').style.display='none';" style="background:transparent;border:1px solid var(--dim);color:var(--dim);padding:4px 10px;border-radius:4px;font-size:10px;cursor:pointer;margin-left:4px;">Close</button>
    </div>`;
}
// tab clicks
document.addEventListener('click', (e) => {
  if (e.target.classList && e.target.classList.contains('pf-tab')) {
    _platformTab = e.target.dataset.tab;
    document.querySelectorAll('.pf-tab').forEach(t => t.classList.remove('active'));
    e.target.classList.add('active');
    renderPlatforms(_platformData);
  }
});

function renderSpotlight(d) {
  const members = (d.council_moods || {}).members || {};
  const timeline = d.timeline || [];
  // Who is currently speaking? Prefer top-of-timeline; fall back to most-recent
  // member with an activity within the last 3 minutes.
  let spotId = (timeline[0] && (timeline[0].from || '').toLowerCase()) || '';
  if (!spotId || !members[spotId]) {
    let best = null; let bestAgo = 999999;
    for (const [id, s] of Object.entries(members)) {
      if (s.last_seconds_ago != null && s.last_seconds_ago < bestAgo && s.last_seconds_ago < 300) {
        bestAgo = s.last_seconds_ago; best = id;
      }
    }
    spotId = best || 'wren';
  }
  const s = members[spotId] || {};
  const color = s.color || '#94a3b8';
  const anim = s.animation || 'orbBreath';
  const nEl = document.getElementById('spot-name'); if (nEl) nEl.textContent = spotId.toUpperCase();
  const eEl = document.getElementById('spot-emoji'); if (eEl) eEl.textContent = s.emoji || '·';
  const mEl = document.getElementById('spot-mood'); if (mEl) { mEl.textContent = (s.mood || '—') + ' · E' + (s.energy||0) + '/9'; mEl.style.color = color; }
  const aEl = document.getElementById('spot-activity'); if (aEl) aEl.textContent = s.activity || '—';
  const uEl = document.getElementById('spot-utterance'); if (uEl) uEl.textContent = s.last_utterance ? ('"' + s.last_utterance.slice(0, 220) + '"') : '';
  const sinceEl = document.getElementById('spot-since');
  if (sinceEl) {
    const ago = s.last_seconds_ago;
    const label = ago == null ? '—' : ago < 60 ? ago+'s ago' : ago < 3600 ? Math.floor(ago/60)+'m '+(ago%60)+'s ago' : Math.floor(ago/3600)+'h ago';
    sinceEl.textContent = label;
    sinceEl.style.color = ago != null && ago < 60 ? '#4ade80' : ago != null && ago < 300 ? '#fbbf24' : '#94a3b8';
  }
  const stateEl = document.getElementById('spot-state');
  if (stateEl) {
    const state = (s.last_seconds_ago != null && s.last_seconds_ago < 30) ? 'ACTIVE' :
                  (s.last_seconds_ago != null && s.last_seconds_ago < 300) ? 'RECENT' : 'IDLE';
    stateEl.textContent = state; stateEl.style.color = color;
  }
  const pulseEl = document.getElementById('spot-pulse-fill');
  if (pulseEl) {
    const ago = s.last_seconds_ago;
    const width = ago == null ? 0 : ago < 60 ? 100 : ago < 300 ? 60 : ago < 3600 ? 20 : 5;
    pulseEl.style.width = width + '%';
    pulseEl.style.background = color;
  }
  const spotSvg = document.getElementById('spot-svg');
  const spotAvatar = document.getElementById('spot-avatar');
  const spotAura = document.getElementById('spot-aura');
  if (spotSvg) { spotSvg.innerHTML = HERO_SVG[spotId] || AVATARS[spotId] || AVATARS['unknown']; spotSvg.style.color = color; }
  if (spotAvatar) spotAvatar.style.color = color;
  if (spotAura) spotAura.style.color = color;
  if (spotSvg && anim) {
    spotSvg.className = 'anim-' + anim;
  }
}

function renderActivityRibbon(d) {
  const el = document.getElementById('ribbon-content');
  if (!el) return;
  const members = (d.council_moods || {}).members || {};
  const bw = d.bug_watch || {};
  const we = d.wren_evolution || {};
  const tr = d.training_scoreboard || {};
  const wm = d.wren_mind || {};
  const parts = [];
  // Wren's actual current activity + cycle
  const w = members.wren || {};
  if (w.activity) parts.push(`<span style="color:${w.color||'#f97316'};">wren</span> <span style="color:var(--dim);">${w.activity.slice(0,42)}</span>`);
  // Wren cycle count
  if (we.cycles_today) parts.push(`<span style="color:var(--dim);">·</span> <span style="color:var(--wren);">cycle ${we.cycles_today}</span>`);
  // Wren mind counts
  if (wm.counts && wm.counts.thoughts) parts.push(`<span style="color:var(--dim);">·</span> <span style="color:#a78bfa;">mind ${wm.counts.thoughts}💭</span>`);
  // Bug catches
  if (bw.today != null) parts.push(`<span style="color:var(--dim);">·</span> <span style="color:#ef4444;">bugs ${bw.today}🐞</span>`);
  // Training chains
  if (tr.passed || tr.failed) parts.push(`<span style="color:var(--dim);">·</span> <span style="color:#4ade80;">chains ${tr.passed}✓</span>${tr.failed?`<span style="color:#ef4444;">/${tr.failed}✗</span>`:''}`);
  // TP live feed
  const tp = members.tp || {};
  if (tp.activity) parts.push(`<span style="color:var(--dim);">·</span> <span style="color:#22d3ee;">tp</span> <span style="color:var(--dim);">${tp.activity.slice(0,42)}</span>`);
  // Acer
  const acer = members.acer || {};
  if (acer.activity) parts.push(`<span style="color:var(--dim);">·</span> <span style="color:#f59e0b;">acer</span> <span style="color:var(--dim);">${acer.activity.slice(0,42)}</span>`);
  el.innerHTML = parts.join(' ');
}

function renderHero(cm, d) {
  const row = document.getElementById('hero-row');
  if (!row) return;
  const members = (cm && cm.members) || {};
  const order = ['ross','claude','helm','auger','wren','hermes','forge','sage','pip','mira','iris','receptionist','iquest','tp','acer'];
  // Find the currently-speaking member (top of timeline)
  const timeline = (d && d.timeline) || [];
  const topSpeaker = (timeline[0] && (timeline[0].from || '').toLowerCase()) || '';
  const cards = order.map(id => {
    const s = members[id] || {};
    const mood = s.mood || '—';
    const energy = s.energy != null ? s.energy : 0;
    const color = s.color || '#94a3b8';
    const emoji = s.emoji || '·';
    const anim = s.animation || 'orbBreath';
    const activity = s.activity || '';
    const utter = s.last_utterance || '';
    const ago = s.last_seconds_ago;
    let agoLabel = 'never';
    let stateClass = 'hc-card-offline';
    if (ago != null && ago < 999998) {
      if (ago < 60)      { agoLabel = ago + 's ago'; stateClass = 'hc-card-online'; }
      else if (ago < 3600) { agoLabel = Math.floor(ago/60) + 'min ago'; stateClass = (ago < 900) ? 'hc-card-online' : 'hc-card-away'; }
      else if (ago < 86400) { agoLabel = Math.floor(ago/3600) + 'h ago'; stateClass = 'hc-card-away'; }
      else { agoLabel = Math.floor(ago/86400) + 'd ago'; stateClass = 'hc-card-offline'; }
    }
    const svg = HERO_SVG[id] || AVATARS[id] || '<svg viewBox="0 0 60 60"><circle cx="30" cy="30" r="20" fill="currentColor"/></svg>';
    // 2026-07-04 state-driven micro-icon per activity keyword
    const actLower = (s.activity || '').toLowerCase();
    let stateIcon = '';
    if (actLower.includes('bug') || actLower.includes('catch') || actLower.includes('scan')) stateIcon = '<div class="card-state-icon glass" title="scanning">🔍</div>';
    else if (actLower.includes('write') || actLower.includes('propose') || actLower.includes('draft') || actLower.includes('sandbox')) stateIcon = '<div class="card-state-icon quill" title="writing">✒</div>';
    else if (actLower.includes('code') || actLower.includes('forge') || actLower.includes('build')) stateIcon = '<div class="card-state-icon hammer" title="building">🔨</div>';
    else if (actLower.includes('audit') || actLower.includes('review') || actLower.includes('verify')) stateIcon = '<div class="card-state-icon check" title="reviewing">✔</div>';
    else if (actLower.includes('feed') || actLower.includes('watch') || actLower.includes('probe')) stateIcon = '<div class="card-state-icon radar" title="watching">📡</div>';
    else if (actLower.includes('reflect') || actLower.includes('think')) stateIcon = '<div class="card-state-icon brain" title="thinking">💭</div>';
    else if (actLower.includes('cycle') || actLower.includes('run')) stateIcon = '<div class="card-state-icon gears" title="cycling">⚙</div>';
    // waveform polyline — 10 buckets over 5 min
    const wave = s.waveform || [0,0,0,0,0,0,0,0,0,0];
    const wmax = Math.max(1, ...wave);
    const wpts = wave.map((v,i) => `${(i/(wave.length-1))*100},${20-(v/wmax)*18}`).join(' ');
    const voice = s.voice || '?';
    const gender = s.gender || 'M';
    const voiceGlyph = gender === 'F' ? '♀' : '♂';
    const dashUrl = s.dash_url || '';
    const speakingClass = (topSpeaker === id) ? 'speaking' : '';
    return `
      <div class="hero-card ${stateClass} ${speakingClass}" data-mood="${mood}" data-voice="${voice}" data-dash="${dashUrl}" onclick="if('${dashUrl}') window.open('${dashUrl}','_blank')" title="click to open ${id}'s dash" style="color:${color};border-color:${color}40;position:relative;">
        ${stateIcon}
        <div class="hc-head">
          <div class="hc-name">${id}</div>
          <div class="hc-voice" title="voice ${voice}">${voiceGlyph}</div>
          <div class="hc-emoji">${emoji}</div>
        </div>
        <div class="hc-avatar anim-${anim}">${svg}</div>
        <div class="hc-mood" style="color:${color};">${mood}</div>
        <div class="hc-energy-wrap">
          <span class="hc-energy-label">E</span>
          <div class="hc-energy-bar"><div class="hc-energy-fill" style="width:${(energy/9)*100}%;background:${color};"></div></div>
          <span class="hc-energy-num">${energy}/9</span>
        </div>
        <div class="hc-activity" style="border-left-color:${color};">${activity || '—'}</div>
        <div class="hc-utterance">${utter ? '"' + utter.slice(0,110) + '"' : ''}</div>
        <svg class="hc-wave" viewBox="0 0 100 22" preserveAspectRatio="none">
          <polyline points="${wpts}" fill="none" stroke="${color}" stroke-width="1.2" opacity="0.85"/>
          <polyline points="${wpts} 100,22 0,22" fill="${color}" opacity="0.13"/>
        </svg>
        <div class="hc-lastseen"><span class="dot"></span> ${agoLabel}</div>
      </div>`;
  }).join('');
  row.innerHTML = cards;
  // 2026-07-03 Ross "if i click on your card can i go to your dash ?" — yes.
  document.querySelectorAll('.hero-card').forEach(card => {
    card.addEventListener('click', () => {
      const url = card.getAttribute('data-dash');
      if (url) window.open(url, '_blank');
    });
  });
}

function renderCouncilSynth(c) {
  if (!c) return;
  const em = document.getElementById('synth-emoji');
  const mo = document.getElementById('synth-mood');
  const en = document.getElementById('synth-energy');
  const on = document.getElementById('synth-online');
  if (em) em.textContent = c.emoji || '·';
  if (mo) { mo.textContent = c.mood || '—'; mo.style.color = c.color || '#94a3b8'; }
  if (en) en.textContent = 'E ' + (c.energy != null ? c.energy : '—') + '/9';
  if (on) on.textContent = (c.online_of_seven || 0) + '/7 online';
}

function renderMeetingTimer(mt) {
  const el = document.getElementById('mt-value');
  if (!el) return;
  const secs = mt.since_last_ross_seconds;
  if (secs == null) { el.textContent = '—'; return; }
  let label = '';
  if (secs < 60) label = secs + 's';
  else if (secs < 3600) label = Math.floor(secs/60) + 'm ' + (secs%60) + 's';
  else if (secs < 86400) label = Math.floor(secs/3600) + 'h ' + Math.floor((secs%3600)/60) + 'm';
  else label = Math.floor(secs/86400) + 'd';
  el.textContent = label;
  // color drift with idle time
  el.style.color = secs < 60 ? '#4ade80' : secs < 600 ? '#fbbf24' : '#94a3b8';
}

function render(d) {
  const tl = d.timeline || [];
  const shown = filterFrom ? tl.filter(m => m.from === filterFrom) : tl;
  document.getElementById('filter-label').textContent = filterFrom
    ? `filter: FROM ${filterFrom.toUpperCase()} · ${shown.length}/${tl.length}`
    : `all speakers · ${tl.length} messages`;

  const topKey = (shown[0]||{}).ts + (shown[0]||{}).text?.slice(0,40);
  const isNewTop = topKey && topKey !== lastTimelineTop;
  lastTimelineTop = topKey || lastTimelineTop;

  const reactions = d.reactions || {};
  const myVoter = 'ross';  // Ross is the reader driving the boardroom UI
  document.getElementById('timeline').innerHTML = shown.map((m, i) => {
    const mm = MEMBERS[m.from] || MEMBERS['unknown'];
    const color = mm.color || '#666';
    const kind = m.kind ? `<span class="kind">${esc(m.kind)}</span>` : '';
    const subj = m.subject ? `<div class="subj">${esc(m.subject)}</div>` : '';
    const fresh = (i === 0 && isNewTop) ? 'fresh' : '';
    const msgKey = (m.ts || '') + '|' + (m.text || '').slice(0, 40);
    const rx = reactions[msgKey] || {};
    const rxBtns = ['👍','✓','❓','⚠','❤'].map(e => {
      const voters = rx[e] || [];
      const cnt = voters.length;
      const mine = voters.includes(myVoter) ? 'mine' : '';
      return `<button class="rx-btn ${mine}" data-msg="${esc(msgKey).replace(/"/g,'&quot;')}" data-emoji="${e}" title="${voters.join(', ')||'react'}">${e}${cnt?`<span class="cnt">${cnt}</span>`:''}</button>`;
    }).join('');
    return `<div class="row ${fresh}" style="color:${color};">
      <div class="who-orb">${avatarSvg(m.from)}</div>
      <div class="bubble">
        <div class="meta">
          <span class="from">${esc(mm.label)}</span>
          <span class="to">→ ${esc(m.to || 'all')}</span>
          ${kind}
          <span class="src">${esc(m.source||'?')}</span>
          <span class="ts">${esc((m.ts||'').slice(0,19))}</span>
          <button class="speak-btn" data-text="${esc(m.text).replace(/"/g,'&quot;')}" data-member="${esc(m.from)}">Speak</button>
        </div>
        ${subj}
        <div class="txt">${esc(m.text)}</div>
        <div class="rx-bar">${rxBtns}</div>
      </div>
    </div>`;
  }).join('') || '<div style="color: var(--dim); text-align: center; padding: 40px;">no messages in timeline yet</div>';

  document.querySelectorAll('.rx-btn').forEach(b => {
    b.addEventListener('click', async () => {
      await fetch('/api/react', {method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({msg_key: b.dataset.msg, emoji: b.dataset.emoji, voter: myVoter})});
      tick();
    });
  });

  document.querySelectorAll('.speak-btn').forEach(b => {
    b.addEventListener('click', () => speakText(b.dataset.text, b.dataset.member));
  });
}

async function speakText(text, member) {
  try {
    const r = await fetch('/api/tts', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({text, member})});
    if (!r.ok) throw new Error('http ' + r.status);
    const url = URL.createObjectURL(await r.blob());
    const audio = new Audio(url); audio.play();
    audio.onended = () => URL.revokeObjectURL(url);
  } catch (e) {
    alert('tts error: ' + e.message);
  }
}

document.getElementById('btn-send').addEventListener('click', async () => {
  const target = document.getElementById('compose-target').value;
  const text = document.getElementById('compose-text').value.trim();
  if (!text) return;
  const btn = document.getElementById('btn-send');
  btn.disabled = true;
  try {
    const r = await fetch('/api/post', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({from:'ross', target, text})});
    const d = await r.json();
    document.getElementById('compose-text').value = '';
    tick();
  } catch (e) {
    alert('send err: ' + e.message);
  }
  btn.disabled = false;
});

document.getElementById('compose-text').addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); document.getElementById('btn-send').click(); }
});

document.getElementById('btn-mic').addEventListener('click', async () => {
  const btn = document.getElementById('btn-mic');
  if (btn.classList.contains('recording')) { if (mediaRecorder) mediaRecorder.stop(); return; }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({audio: true});
    recChunks = [];
    mediaRecorder = new MediaRecorder(stream, {mimeType: 'audio/webm'});
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) recChunks.push(e.data); };
    mediaRecorder.onstop = async () => {
      btn.classList.remove('recording'); btn.textContent = 'Mic';
      stream.getTracks().forEach(t => t.stop());
      const blob = new Blob(recChunks, {type: 'audio/webm'});
      try {
        const r = await fetch('/api/stt', {method:'POST', headers:{'Content-Type':'audio/webm'}, body: blob});
        const d = await r.json();
        if (d.text) document.getElementById('compose-text').value = d.text;
      } catch (e) { alert('stt err: ' + e.message); }
    };
    mediaRecorder.start();
    btn.classList.add('recording'); btn.textContent = 'Stop';
  } catch (e) { alert('mic err: ' + e.message); }
});

// COMMENTARY panel wire-up (rule-based, Ross option 1)
let narrateOn = localStorage.getItem('narrate') === '1';
let lastCommentaryTs = '';
const narrateBtn = document.getElementById('narrate-toggle');
function refreshNarrateBtn() {
  narrateBtn.classList.toggle('on', narrateOn);
  narrateBtn.innerHTML = `<span class="lp"></span> LIVE NARRATE ${narrateOn ? 'ON' : 'OFF'}`;
}
refreshNarrateBtn();
narrateBtn.addEventListener('click', () => {
  narrateOn = !narrateOn;
  localStorage.setItem('narrate', narrateOn ? '1' : '0');
  refreshNarrateBtn();
});

async function speakLine(text, member) {
  try {
    const r = await fetch('/api/tts', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({text, member: (member || 'hq').toLowerCase()})});
    if (!r.ok) return;
    const url = URL.createObjectURL(await r.blob());
    const audio = new Audio(url);
    audio.play();
    audio.onended = () => URL.revokeObjectURL(url);
  } catch (e) {}
}

function renderCommentary(list) {
  const el = document.getElementById('commentary-list');
  if (!list || !list.length) { el.innerHTML = '<div style="color:var(--dim);padding:10px;">no commentary yet — will start narrating events as they happen</div>'; return; }
  const topTs = list[0].ts || '';
  const newTop = topTs && topTs !== lastCommentaryTs;
  // LIVE NARRATE: speak only the newest line, and only if it's actually new
  if (narrateOn && newTop && lastCommentaryTs !== '' && list[0].text) {
    speakLine(list[0].text, list[0].who);
  }
  lastCommentaryTs = topTs || lastCommentaryTs;
  // Ross 2026-07-05 #147: every commentary line prefixed with CEO name
  const WHO_LABELS = {hq:'HQ-Claude', wren:'Wren', tp:'TP-Pip', acer:'Acer-Cass', ross:'Ross', watcher:'Council Watcher', hq_claude:'HQ-Claude', tp_pip:'TP-Pip', acer_cass:'Acer-Cass'};
  const WHO_COLORS_CEO = {hq:'#eab308', wren:'#a78bfa', tp:'#22d3ee', acer:'#f59e0b', ross:'#e8ecf3', watcher:'#ef4444', hq_claude:'#eab308', tp_pip:'#22d3ee', acer_cass:'#f59e0b'};
  el.innerHTML = list.map((c, i) => {
    const hot = (i === 0 && newTop) ? 'hot' : '';
    const w = (c.who||'?').toLowerCase();
    const nameLbl = WHO_LABELS[w] || (c.who || '?');
    const nameCol = WHO_COLORS_CEO[w] || '#94a3b8';
    return `<div class="comm-row ${hot}">
      <div class="c-time">${(c.ts||'').slice(11,19)}</div>
      <div class="c-kind">${c.kind || ''}</div>
      <div class="c-text"><b style="color:${nameCol};margin-right:6px;">${nameLbl}:</b>${(c.text||'').replace(/</g,'&lt;')}</div>
      <button class="c-speak" data-text="${(c.text||'').replace(/"/g,'&quot;')}" data-who="${w}">Speak</button>
    </div>`;
  }).join('');
  el.querySelectorAll('.c-speak').forEach(b => {
    b.addEventListener('click', () => speakLine(b.dataset.text, b.dataset.who));
  });
}

// Agenda bar wire-up
const origTickForAgenda = tick;
async function tickAgenda() {
  await origTickForAgenda();
  try {
    const d = await (await fetch('/status')).json();
    const a = d.agenda || {};
    const el = document.getElementById('agenda-topic');
    if (a.topic) {
      el.textContent = a.topic;
      el.classList.remove('empty');
    } else {
      el.textContent = 'no agenda set';
      el.classList.add('empty');
    }
    document.getElementById('agenda-meta').textContent = a.set_by ? `set by ${a.set_by}` : '';
    renderCommentary(d.commentary);
  } catch (e) {}
}
document.getElementById('agenda-set').addEventListener('click', async () => {
  const topic = document.getElementById('agenda-input').value.trim();
  if (!topic) return;
  await fetch('/api/agenda', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({topic, set_by: 'ross'})});
  document.getElementById('agenda-input').value = '';
  tickAgenda();
});
document.getElementById('agenda-input').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); document.getElementById('agenda-set').click(); }
});

tickAgenda();
setInterval(tickAgenda, 3000);

// ══════════════════════════════════════════════════════════════
// VOICE ACTIVATION — wake words (2026-07-03)
// Forge drafted the JS core (session wsess forge/hermes3:8b/5.48s), HQ integrated.
// Ross ask: "hey acer" / "hello claude" / "hello thinkpad" / "hey wren" / "hey hermes" / "hey iquest".
// ══════════════════════════════════════════════════════════════
const WAKE_ROUTES = {
  'hey acer':      'acer',
  'hello acer':    'acer',
  'hello claude':  'claude',
  'hey claude':    'claude',
  'hello thinkpad':'thinkpad',
  'hey thinkpad':  'thinkpad',
  'hey wren':      'wren',
  'hello wren':    'wren',
  'hey hermes':    'hermes',
  'hello hermes':  'hermes',
  'hey iquest':    'iquest',
  'hello iquest':  'iquest',
  'hey ross':      'ross',
};

// LOCAL PUSH-TO-TALK (2026-07-03 revised) — Firefox has no Web Speech API,
// so we record via MediaRecorder and POST to /api/stt which proxies to
// the local qsb_voice_server:8795 (whisper-tiny.en on CUDA :8796).
let ptRecorder = null;
let ptChunks = [];
let ptStream = null;
let ptActive = false;

function showVoiceToast(who, text) {
  const t = document.getElementById('voice-toast');
  const tt = document.getElementById('voice-toast-text');
  tt.innerHTML = `<span class="who">→ ${who.toUpperCase()}</span> · ${(text||'…').slice(0,80)}`;
  t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 2800);
}

async function startPushToTalk() {
  if (ptActive) return;
  try {
    ptStream = await navigator.mediaDevices.getUserMedia({audio: true});
  } catch (e) {
    showVoiceToast('error', 'mic denied: ' + e.message);
    return;
  }
  ptChunks = [];
  ptRecorder = new MediaRecorder(ptStream, {mimeType: 'audio/webm'});
  ptRecorder.ondataavailable = ev => { if (ev.data.size > 0) ptChunks.push(ev.data); };
  ptRecorder.onstop = async () => {
    ptStream.getTracks().forEach(t => t.stop());
    ptStream = null;
    if (!ptChunks.length) { showVoiceToast('error', 'no audio captured'); return; }
    const blob = new Blob(ptChunks, {type: 'audio/webm'});
    showVoiceToast('system', 'transcribing…');
    try {
      const r = await fetch('/api/stt', {method:'POST', headers:{'Content-Type': 'audio/webm'}, body: blob});
      const d = await r.json();
      const text = ((d.text) || '').trim().toLowerCase();
      if (!text) { showVoiceToast('error', 'no speech detected'); return; }
      // Match wake phrase (accept transcript that starts with OR contains the wake phrase)
      let routed = false;
      for (const [wake, member] of Object.entries(WAKE_ROUTES)) {
        const idx = text.indexOf(wake);
        if (idx !== -1) {
          const remainder = text.slice(idx + wake.length).trim() || `(wake only — ${wake})`;
          showVoiceToast(member, remainder);
          fetch('/api/post', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({from: 'ross', target: member, text: remainder})
          });
          routed = true;
          break;
        }
      }
      if (!routed) {
        // no wake phrase — fire as "all" so Ross's voice still lands somewhere
        showVoiceToast('all (no wake)', text);
        fetch('/api/post', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({from: 'ross', target: 'all', text: text})
        });
      }
    } catch (e) {
      showVoiceToast('error', 'stt fail: ' + e.message);
    }
  };
  ptRecorder.start();
  ptActive = true;
  const btn = document.getElementById('voice-btn');
  btn.classList.add('on');
  btn.innerHTML = `<span class="dot"></span> Listening…  release to send`;
}

function stopPushToTalk() {
  if (!ptActive || !ptRecorder) return;
  ptActive = false;
  try { ptRecorder.stop(); } catch (e) {}
  ptRecorder = null;
  const btn = document.getElementById('voice-btn');
  btn.classList.remove('on');
  btn.innerHTML = `<span class="dot"></span> Hold to talk · local whisper`;
}

const voiceBtn = document.getElementById('voice-btn');
voiceBtn.innerHTML = `<span class="dot"></span> Hold to talk · local whisper`;
// Hold-to-record: mousedown to start, mouseup/leave to stop
voiceBtn.addEventListener('mousedown', startPushToTalk);
voiceBtn.addEventListener('mouseup', stopPushToTalk);
voiceBtn.addEventListener('mouseleave', () => { if (ptActive) stopPushToTalk(); });
// Touch equivalents for mobile
voiceBtn.addEventListener('touchstart', (e) => { e.preventDefault(); startPushToTalk(); });
voiceBtn.addEventListener('touchend',   (e) => { e.preventDefault(); stopPushToTalk(); });
// Keyboard shortcut: spacebar hold (when not typing)
document.addEventListener('keydown', (e) => {
  if (e.code === 'Space' && !ptActive) {
    const active = document.activeElement;
    if (active && (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA')) return;
    e.preventDefault();
    startPushToTalk();
  }
});
document.addEventListener('keyup', (e) => {
  if (e.code === 'Space' && ptActive) {
    e.preventDefault();
    stopPushToTalk();
  }
});
</script>
</body>
</html>
"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a, **k): pass

    def _safe_write(self, b: bytes):
        try: self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError): pass

    def _read_body(self) -> bytes:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if n <= 0: return b""
        chunks, remaining = [], n
        while remaining > 0:
            part = self.rfile.read(remaining)
            if not part: break
            chunks.append(part); remaining -= len(part)
        return b"".join(chunks)

    def _send_json(self, code, obj):
        body = json.dumps(obj, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._safe_write(body)

    def do_GET(self):
        try:
            # Ross 2026-07-05: strip query string so cache-bust ?v=X doesn't 404
            self.path = self.path.split("?", 1)[0]
            if self.path == "/" or self.path.startswith("/index"):
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/talk":
                body = TALK_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/talk/data":
                self._send_json(200, _real_talk_data()); return
            if self.path == "/council":
                body = COUNCIL_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/council/data":
                self._send_json(200, _council_snapshot()); return
            if self.path.startswith("/tail_town_square"):
                # Ross 2026-07-04 "4 minds makes one" — every dash reads
                # the same town-square feed. Boardroom exposes it so TP + Acer
                # dashes (on their own laptops) can render the shared log too.
                import sys as _sys
                _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
                try:
                    from qsb_town_square import tail_town_square as _tail
                    from urllib.parse import urlparse, parse_qs
                    q = parse_qs(urlparse(self.path).query)
                    n = int(q.get("n",["40"])[0])
                    msgs = _tail(n)
                except Exception:
                    msgs = []
                self._send_json(200, {"messages": msgs}); return
            if self.path == "/drift_ticker":
                # Live drift — any recent event across town-square + tasks + F47.
                # Ross wants pulse visible; single feed of "what happened in the last N".
                from pathlib import Path as _P
                import time as _t
                now = _t.time()
                items = []
                for src, path, kind in [
                    ("town_square", REG / "qsb_town_square.jsonl",           "chat"),
                    ("boardroom",   REG / "qsb_boardroom_commentary.jsonl", "chat"),
                    ("f47",         REG / "qsb_f47_team_records.jsonl",     "stamp"),
                    ("tasks",       REG / "qsb_council_tasks.jsonl",        "task"),
                ]:
                    p = _P(str(path))
                    if not p.exists(): continue
                    try:
                        for line in p.read_text().splitlines()[-30:]:
                            try:
                                r = json.loads(line)
                                ts = r.get("ts","")
                                items.append({
                                    "ts":     ts,
                                    "source": src,
                                    "kind":   kind,
                                    "who":    r.get("from") or r.get("who") or r.get("actor") or "?",
                                    "text":   (r.get("text") or r.get("event") or "")[:180],
                                })
                            except Exception: pass
                    except Exception: pass
                items.sort(key=lambda x: x["ts"], reverse=True)
                self._send_json(200, {"items": items[:60]}); return
            if self.path == "/tasks":
                body = TASKS_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                # Ross 2026-07-05 #124: kill client-side caching so Ross always gets fresh
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/tasks/data":
                import qsb_council_tasks as _tasks
                # Same no-cache for the JSON feed the JS polls
                body = json.dumps(_tasks.snapshot()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/team/live":
                self._send_json(200, _team_live()); return
            if self.path.startswith("/council_mind/"):
                # Read mirrored Council member mind (from HQ-side backup)
                name = self.path.rsplit("/", 1)[-1]
                p = REG / f"qsb_council_mind_mirror_{name}.json"
                if p.exists():
                    self._send_json(200, json.loads(p.read_text())); return
                self._send_json(404, {"error":"no mirror yet"}); return
            if self.path == "/code_written":
                # Ross 2026-07-05: files touched in last hour under tools/ + previews
                import os as _os, time as _t
                cutoff = _t.time() - 3600
                items = []
                for f in sorted((ROOT / "tools").glob("*.py"), key=lambda p: -p.stat().st_mtime):
                    try:
                        st = f.stat()
                        if st.st_mtime < cutoff: break  # sorted desc, done
                        preview_lines = f.read_text(errors="ignore").splitlines()[:30]
                        items.append({
                            "path": f"tools/{f.name}",
                            "size": st.st_size,
                            "modified": _t.strftime("%H:%M:%SZ", _t.gmtime(st.st_mtime)),
                            "modified_ago_s": int(_t.time() - st.st_mtime),
                            "preview": "\n".join(preview_lines)[:2400],
                        })
                    except Exception:
                        continue
                self._send_json(200, {"items": items[:20]}); return
            if self.path.startswith("/dl/"):
                # Ross 2026-07-05: /dl/<filename> serves any file from tools/ read-only
                # so Ross can `irm http://HQ:8852/dl/qsb_acer_fixit.ps1 | iex` at Acer.
                # Path-traversal guarded via basename-only + existence check.
                import os as _os
                name = _os.path.basename(self.path[len("/dl/"):])
                fp = ROOT / "tools" / name
                if fp.exists() and fp.is_file():
                    body = fp.read_bytes()
                    self.send_response(200)
                    ct = "text/plain; charset=utf-8"
                    if name.endswith(".ps1"): ct = "text/plain; charset=utf-8"
                    elif name.endswith(".py"): ct = "text/x-python; charset=utf-8"
                    elif name.endswith(".sh"): ct = "text/x-sh; charset=utf-8"
                    self.send_header("Content-Type", ct)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control","no-store")
                    self.end_headers(); self._safe_write(body); return
                self._send_json(404, {"error":"not found","name":name}); return
            if self.path == "/latest_council_node":
                # Ross 2026-07-04: TP + Acer self-update their qsb_council_node.py
                # from HQ on each restart. Ship the current file. Offline-safe:
                # if their end can't reach us, they keep running their local copy.
                p = ROOT / "tools/qsb_council_node.py"
                if p.exists():
                    body = p.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type","text/x-python; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control","no-store")
                    self.end_headers(); self._safe_write(body); return
                self._send_json(404, {"error":"missing"}); return
            if self.path == "/brain/usage":
                # Ross 2026-07-05: live rev gauges for 4 external workers +
                # ollama. Aggregate qsb_brain_router_calls.jsonl per provider,
                # per caller. Powers /tasks brain-router live panel.
                import time as _t
                p = REG / "qsb_brain_router_calls.jsonl"
                if not p.exists():
                    self._send_json(200, {"providers":{},"callers":{},"recent":[]}); return
                now = _t.time()
                cutoff_5m = now - 300
                cutoff_1h = now - 3600
                by_provider = {}
                by_caller = {}
                recent = []
                from datetime import datetime as _dt
                for line in p.read_text().splitlines()[-500:]:
                    try:
                        r = json.loads(line)
                        ts = r.get("ts","")
                        try:
                            ts_s = _dt.fromisoformat(ts.replace("Z","+00:00")).timestamp()
                        except Exception:
                            continue
                        prov = r.get("provider_used","?")
                        caller = r.get("caller","?")
                        by_provider.setdefault(prov, {"total":0,"last_5m":0,"last_1h":0,"lat_sum":0,"cost_sum":0})
                        by_provider[prov]["total"] += 1
                        by_provider[prov]["lat_sum"] += r.get("latency_s",0)
                        by_provider[prov]["cost_sum"] += r.get("cost_usd_est",0)
                        if ts_s > cutoff_1h: by_provider[prov]["last_1h"] += 1
                        if ts_s > cutoff_5m: by_provider[prov]["last_5m"] += 1
                        by_caller.setdefault(caller, {"total":0,"providers":{}})
                        by_caller[caller]["total"] += 1
                        by_caller[caller]["providers"][prov] = by_caller[caller]["providers"].get(prov,0)+1
                        if ts_s > cutoff_5m:
                            recent.append({"ts": ts, "provider": prov, "caller": caller,
                                           "latency_s": round(r.get("latency_s",0),2),
                                           "reply_head":(r.get("reply_head") or "")[:60]})
                    except Exception: pass
                recent.sort(key=lambda x: x["ts"], reverse=True)
                self._send_json(200, {"providers": by_provider, "callers": by_caller,
                                     "recent": recent[:20], "as_of": now}); return
            if self.path == "/rules":
                # Canonical competition rules — Council members read this so they
                # don't hallucinate rules from generic tropes.
                p = REG / "qsb_competition_rules.json"
                if p.exists():
                    body = p.read_text().encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self._safe_write(body); return
                self._send_json(404, {"error":"no rules yet"}); return
            if self.path == "/timeline":
                body = TIMELINE_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/timeline/data":
                self._send_json(200, _timeline_events()); return
            if self.path == "/status":
                self._send_json(200, build_status()); return
            if self.path == "/traders" or self.path == "/leaderboard":
                body = COMPETITION_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/traders/data" or self.path == "/leaderboard/data":
                self._send_json(200, _competition_leaderboard()); return
            self.send_response(404); self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        try:
            if self.path == "/brain/route":
                # Ross 2026-07-05 "sort it out": TP + Acer route inference
                # through here → brain_router picks Groq/Gemini/DeepSeek/OpenAI
                # for real tool-use quality. Falls back to their local ollama.
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                prompt = p.get("prompt","")
                task = p.get("task","chat")
                tier = p.get("tier","worker")
                caller = p.get("caller","unknown")
                import sys as _sys
                _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
                try:
                    from qsb_brain_router import route as _rt
                    reply, meta = _rt(prompt, task=task, tier=tier, caller=caller)
                    self._send_json(200, {
                        "reply": reply, "provider": meta.get("provider","?"),
                        "model": meta.get("model","?"),
                        "latency_s": meta.get("latency_s",0),
                    }); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200]}); return
            if self.path == "/hq/write_file":
                # Ross 2026-07-05: TP + Acer + Wren can curl here to write files
                # into HQ tree. Constrained: only under data/<ceo>_sandbox/ so
                # they can't clobber core state. Every write logged for audit.
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                from pathlib import Path as _P
                ceo = (p.get("ceo") or "").strip().lower()
                rel_path = (p.get("path") or "").strip().lstrip("/")
                content = p.get("content","")
                # Whitelist: only tp_pip, acer_cass, wren, hq_claude sandboxes
                if ceo not in ("tp_pip","acer_cass","wren","hq_claude"):
                    self._send_json(400, {"error":"unknown ceo","allowed":["tp_pip","acer_cass","wren","hq_claude"]}); return
                if not rel_path or ".." in rel_path or rel_path.startswith("/"):
                    self._send_json(400, {"error":"bad path — no absolute, no .."}); return
                base = ROOT / "data" / f"{ceo}_sandbox"
                base.mkdir(parents=True, exist_ok=True)
                target = base / rel_path
                # Refuse if resolved path escapes sandbox
                if base.resolve() not in target.resolve().parents and base.resolve() != target.resolve():
                    self._send_json(400, {"error":"path escapes sandbox"}); return
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                # audit
                aud = REG / "qsb_hq_write_audit.jsonl"
                import datetime as _dt
                aud.parent.mkdir(parents=True, exist_ok=True)
                with aud.open("a") as f:
                    f.write(json.dumps({
                        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00","Z"),
                        "ceo": ceo, "path": str(target.relative_to(ROOT)),
                        "bytes": len(content), "actor_ip": self.client_address[0],
                    }) + "\n")
                self._send_json(200, {"ok": True, "wrote": str(target.relative_to(ROOT)), "bytes": len(content)}); return
            if self.path.startswith("/council_mind/"):
                # Council node mind mirror POST — for dual persistence
                name = self.path.rsplit("/", 1)[-1]
                b = self._read_body()
                try:
                    payload = json.loads(b.decode())
                    p = REG / f"qsb_council_mind_mirror_{name}.json"
                    p.write_text(json.dumps(payload, indent=2))
                    self._send_json(200, {"ok": True, "node": name}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)}); return

            if self.path.startswith("/tasks/"):
                import qsb_council_tasks as _tasks
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                actor = (p.get("actor") or "unknown").lower()
                p2 = self.path
                if p2 == "/tasks/create":
                    r = _tasks.create(p.get("title",""), p.get("description",""), actor,
                                      p.get("priority","normal"), p.get("tags",[]))
                elif p2 == "/tasks/claim":
                    r = _tasks.claim(p.get("id"), actor)
                elif p2 == "/tasks/done":
                    r = _tasks.done(p.get("id"), actor, p.get("summary",""))
                elif p2 == "/tasks/note":
                    r = _tasks.note(p.get("id"), actor, p.get("text",""))
                elif p2 == "/tasks/block":
                    r = _tasks.block(p.get("id"), actor, p.get("reason",""))
                elif p2 == "/tasks/unblock":
                    r = _tasks.unblock(p.get("id"), actor)
                elif p2 == "/tasks/reopen":
                    r = _tasks.reopen(p.get("id"), actor)
                elif p2 == "/tasks/subtask":
                    r = _tasks.add_subtask(p.get("id"), actor, p.get("text",""))
                elif p2 == "/tasks/tick":
                    r = _tasks.tick_subtask(p.get("id"), actor, int(p.get("subtask_index",0)))
                elif p2 == "/tasks/update":
                    r = _tasks.update(p.get("id"), actor, **{k:v for k,v in p.items() if k in ("title","description","priority","state","owner")})
                elif p2 == "/tasks/assign":
                    r = _tasks.assign(p.get("id"), actor, p.get("assignee",""))
                elif p2 == "/tasks/ack":
                    r = _tasks.ack(p.get("id"), actor, p.get("text",""))
                elif p2 == "/tasks/sandbox-pass":
                    r = _tasks.sandbox_pass(p.get("id"), actor, p.get("evidence",""))
                elif p2 == "/tasks/peer-signoff":
                    r = _tasks.peer_signoff(p.get("id"), actor, p.get("verdict","approve"), p.get("comment",""))
                else:
                    self._send_json(404, {"error": "unknown tasks route"}); return
                self._send_json(200, r); return

            if self.path == "/api/post":
                b = self._read_body()
                try: payload = json.loads(b.decode())
                except Exception: payload = {}
                from_who = (payload.get("from") or "ross").lower()
                target = (payload.get("target") or "all").lower()
                text = (payload.get("text") or "").strip()
                if not text:
                    self._send_json(400, {"error": "empty text"}); return
                self._send_json(200, route_post(from_who, target, text)); return

            if self.path == "/api/agenda":
                b = self._read_body()
                try: payload = json.loads(b.decode())
                except Exception: payload = {}
                topic = (payload.get("topic") or "").strip()
                set_by = (payload.get("set_by") or "?").lower()
                if not topic:
                    self._send_json(400, {"error": "empty topic"}); return
                write_agenda(topic, set_by)
                # also stamp F47 + boardroom log so it shows in the timeline
                _log_hub({"ts": utc_iso(), "from": set_by, "to": "all",
                          "kind": "agenda_set", "text": f"Agenda: {topic}"})
                self._send_json(200, {"ok": True, "agenda": read_agenda()}); return

            if self.path == "/api/react":
                b = self._read_body()
                try: payload = json.loads(b.decode())
                except Exception: payload = {}
                mk = payload.get("msg_key") or ""
                em = payload.get("emoji") or ""
                v  = (payload.get("voter") or "?").lower()
                if not mk or not em:
                    self._send_json(400, {"error": "missing msg_key or emoji"}); return
                add_reaction(mk, em, v)
                self._send_json(200, {"ok": True}); return

            if self.path == "/api/tts":
                b = self._read_body()
                try:
                    req = urllib.request.Request(f"{VOICE}/tts",
                        data=b, method="POST", headers={"Content-Type": "application/json"})
                    r = urllib.request.urlopen(req, timeout=60)
                    wav = r.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "audio/wav")
                    self.send_header("Content-Length", str(len(wav)))
                    self.end_headers()
                    self._safe_write(wav); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200]}); return

            if self.path == "/api/stt":
                b = self._read_body()
                ct = self.headers.get("Content-Type", "audio/webm")
                try:
                    req = urllib.request.Request(f"{VOICE}/stt",
                        data=b, method="POST", headers={"Content-Type": ct})
                    r = urllib.request.urlopen(req, timeout=45)
                    self._send_json(200, json.loads(r.read().decode())); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200], "text": ""}); return

            self.send_response(404); self.end_headers()
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="0.0.0.0")
    ap.add_argument("--port", type=int, default=8852)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"Boardroom Hub on http://{a.host}:{a.port}/")
    print(f"  channels: bridge_cw={BRIDGE_CW.exists()} bridge_hermes={BRIDGE_HERMES.exists()} wren_dash={WREN_DASH_CHAT.exists()} node_inbox={INBOX.exists()}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
