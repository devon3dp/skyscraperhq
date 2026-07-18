from collections import deque
import urllib.error
import json

# SKYSCRAPERHQ_SAFE_TAIL_CACHE_V1
_SAFE_TAIL_CACHE = {}

def _safe_tail_lines(path_obj, n=8, ttl=1.5, max_bytes=262144):
    """
    Cached tail reader for hot JSONL/registry files.
    Prevents Boardroom request handlers repeatedly opening Wren registry files.
    Always closes file handles immediately.
    """
    import time
    from pathlib import Path

    try:
        path = str(path_obj)
        n = int(n or 8)
        now_ts = time.time()
        cached = _SAFE_TAIL_CACHE.get((path, n))
        if cached and now_ts - cached.get("ts", 0) < ttl:
            return list(cached.get("lines", []))

        pp = Path(path)
        if not pp.exists() or not pp.is_file():
            lines = []
        else:
            size = pp.stat().st_size
            with pp.open("rb") as f:
                if size > max_bytes:
                    f.seek(max(0, size - max_bytes))
                raw = f.read()
            text = raw.decode("utf-8", "ignore")
            lines = text.splitlines()[-n:]

        _SAFE_TAIL_CACHE[(path, n)] = {"ts": now_ts, "lines": lines}
        return lines
    except OSError as e:
        # Especially Errno 24: do not crash the Boardroom request.
        return [f"[safe_tail_error] {type(e).__name__}: {e}"]
    except Exception as e:
        return [f"[safe_tail_error] {type(e).__name__}: {e}"]


# SKYSCRAPERHQ_GENE_POOL_PROXY_HELPERS_V2
def _gene_pool_proxy_get(path="/"):
    import urllib.request
    if not path:
        path = "/"
    if not path.startswith("/"):
        path = "/" + path
    url = "http://127.0.0.1:8860" + path
    with urllib.request.urlopen(url, timeout=25) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "application/octet-stream")

def _gene_pool_proxy_post(path="/api/submit_job", payload=None):
    import json
    import urllib.request
    if not path:
        path = "/api/submit_job"
    if not path.startswith("/"):
        path = "/" + path
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8860" + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "application/json")

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
  target=tp       -> POST http://192.168.1.74:8871 (physical worker; legacy council_node /msg :9100 retired)
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

TP_URL = "http://192.168.1.74:8871"  # 2026-07-11 S4B1 policy-A: authoritative physical worker (Lenovo ThinkPad .74/DESKTOP-9RBVKSM). Legacy council_node .91:9100 retired.
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


# ============================================================================
# MASTER PROGRAMME PHASE 1 — TRUTH RESTORATION (2026-07-11, Ross+ChatGPT directive)
# Independent, freshly-probed status for every CEO surface. A local surrogate is
# NEVER reported as the physical laptop; a dashboard HTTP 200 NEVER implies the AI
# mind is alive. Every state carries the exact endpoint probed, evidence source,
# and last-ok / last-fail probe timestamps. No cached green survives a real probe.
# ============================================================================
# 2026-07-11 PHASE1-PHYSICAL-ENDPOINT-CORRECTION-003 (Ross+ChatGPT approved):
#   Acer physical runtime discovered at .78:8872 (moved from retired .41:8872 via DHCP).
#   TP physical runtime unchanged .74:8871; TP original dashboard .74:9110.
#   A failed probe means CURRENT ENDPOINT UNREACHABLE — never "machine off" (power is
#   a separate, Ross-confirmed fact).
_P1_PHYS = {"tp": "http://192.168.1.74:8871", "acer": "http://192.168.1.78:8872"}
_P1_HISTORICAL = {"acer": {"endpoint": "192.168.1.41:8872", "label": "RETIRED DHCP ADDRESS"}}
_P1_DASH_ORIG = {"tp": "http://192.168.1.74:9110/"}  # Acer's remote dashboard endpoint not yet discovered
_P1_SURR = {"tp": "http://127.0.0.1:8861", "acer": "http://127.0.0.1:8862"}
_P1_DASH = {"hq": "http://127.0.0.1:8850/", "wren": "http://127.0.0.1:8851/",
            "wren_concierge": "http://127.0.0.1:8857/"}
_P1_HIST = {}  # key -> {"last_ok": iso|None, "last_fail": iso|None, "last_code": int, "last_detail": str}


def _p1_http(key, url, path="", timeout=3, method="GET"):
    """Fresh DIRECT HTTP probe. Records last-ok/last-fail in _P1_HIST so the UI can
    show both timestamps. Never returns a cached success as current."""
    full = url.rstrip("/") + path
    rec = _P1_HIST.setdefault(key, {"last_ok": None, "last_fail": None, "last_code": 0, "last_detail": ""})
    out = {"endpoint": full, "state": "UNREACHABLE", "code": 0, "detail": "",
           "evidence": "direct HTTP probe", "probe_ts": utc_iso(), "body_sample": ""}
    try:
        req = urllib.request.Request(full, method=method)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read(2048)
            out["code"] = r.status
            if 200 <= r.status < 400:
                out["state"] = "LIVE"; rec["last_ok"] = out["probe_ts"]
            else:
                out["state"] = "PARTIAL"; out["detail"] = f"HTTP {r.status}"; rec["last_fail"] = out["probe_ts"]
            out["body_sample"] = body[:1200].decode("utf-8", "replace")
    except urllib.error.HTTPError as he:
        out["code"] = he.code
        out["state"] = "PARTIAL" if 400 <= he.code < 500 else "UNREACHABLE"
        out["detail"] = f"HTTP {he.code}"; rec["last_fail"] = out["probe_ts"]
    except Exception as e:
        out["detail"] = type(e).__name__ + ": " + str(e)[:100]; rec["last_fail"] = out["probe_ts"]
    rec["last_code"] = out["code"]; rec["last_detail"] = out["detail"]
    out["last_ok"] = rec["last_ok"]; out["last_fail"] = rec["last_fail"]
    return out


def _p1_procs():
    """Read-only process census for Wren mind surfaces + duplicate detection."""
    try:
        r = subprocess.run(["ps", "-eo", "pid,cmd"], capture_output=True, text=True, timeout=5)
        lines = r.stdout.splitlines()
    except Exception:
        lines = []

    def _match(substr):
        hits = []
        for ln in lines:
            if substr in ln and "grep" not in ln and "ps -eo" not in ln:
                parts = ln.strip().split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    hits.append(int(parts[0]))
        return hits

    return {label: _match(sub) for label, sub in [
        ("wren_mind", "qsb_wren_evolution_loop.py"),
        ("wren_watcher", "qsb_wren_watcher.py"),
        ("wren_dash_proc", "qsb_wren_dash.py"),
        ("wren_concierge_proc", "qsb_wren_concierge_dash.py")]}


def _p1_last_wren_reply():
    """Last genuine Wren response timestamp from her chat/notes registry (read-only)."""
    for fn in ["qsb_wren_dash_notes.jsonl", "qsb_wren_chat.jsonl", "wren_chat_log.jsonl",
               "qsb_wren_notes.jsonl", "qsb_wren_dash_chat.jsonl"]:
        p = REG / fn
        if p.exists():
            try:
                lines = [l for l in p.read_text(errors="ignore").splitlines() if l.strip()]
                if lines:
                    d = json.loads(lines[-1])
                    return {"source": fn, "ts": d.get("ts") or d.get("time") or "", "found": True}
            except Exception:
                continue
    return {"source": None, "ts": "", "found": False}


def _p1_mode(phys, surr):
    if phys.get("state") == "LIVE":
        return "PHYSICAL"
    if surr.get("state") == "LIVE":
        return "HQ SURROGATE FALLBACK"
    if surr.get("state") == "PARTIAL" or phys.get("state") == "PARTIAL":
        return "UNKNOWN"
    return "OFFLINE"


def p1_truth_model():
    """The Phase 1 truth model — independent states, freshly probed on every call."""
    out = {"ts": utc_iso(), "ceos": {}}
    import re as _re

    def _field(body, key):
        m = _re.search(r'"' + key + r'"\s*:\s*"([^"]+)"', body or "")
        return m.group(1) if m else ""

    for k, name in [("tp", "TP-Pip"), ("acer", "Acer-Cass")]:
        phys = _p1_http("phys_" + k, _P1_PHYS[k], "/health")
        if phys["state"] == "UNREACHABLE":
            alt = _p1_http("phys_" + k, _P1_PHYS[k], "/whoami")
            if alt["state"] != "UNREACHABLE":
                phys = alt
        pid_body = phys.get("body_sample", "") or ""
        surr = _p1_http("surr_" + k, _P1_SURR[k], "/whoami")
        surr_id = _field(surr.get("body_sample", "") or "", "id")
        # runtime state must NEVER be described as "machine off": power is separate + Ross-confirmed
        rt = phys["state"]  # LIVE / UNREACHABLE / PARTIAL
        if rt == "LIVE":
            op_mode = "PHYSICAL WORKER ACTIVE"
        elif surr["state"] == "LIVE":
            op_mode = "HQ SURROGATE ACTIVE — PHYSICAL ENDPOINT UNRESOLVED"
        else:
            op_mode = "PHYSICAL ENDPOINT UNRESOLVED"
        # original dashboard: TP has a discovered remote dash (:9110); Acer's is Ross-confirmed local, endpoint unknown
        if k == "tp":
            od = _p1_http("dash_orig_tp", _P1_DASH_ORIG["tp"])
            original_dashboard = {"endpoint": _P1_DASH_ORIG["tp"], "state": od["state"],
                                  "code": od["code"], "probe_ts": od["probe_ts"],
                                  "source": "DIRECT HTTP PROBE"}
        else:
            original_dashboard = {"endpoint": "UNKNOWN", "state": "LOCAL DASHBOARD ROSS-CONFIRMED",
                                  "remote_endpoint": "NOT YET DISCOVERED",
                                  "source": "ROSS-CONFIRMED PHYSICAL OBSERVATION",
                                  "note": "runtime :8872 is the API surface, NOT the dedicated dashboard"}
        entry = {
            "name": name,
            "machine_power": {"state": "ON — ROSS CONFIRMED", "source": "ROSS-CONFIRMED PHYSICAL OBSERVATION"},
            "physical_runtime": {
                "endpoint": _P1_PHYS[k],
                "state": rt, "code": phys["code"], "detail": phys.get("detail", ""),
                "probe_ts": phys["probe_ts"], "last_ok": phys["last_ok"], "last_fail": phys["last_fail"],
                "identity": _field(pid_body, "id") or _field(pid_body, "runtime_id"),
                "hostname": _field(pid_body, "hostname"),
                "host_mode": _field(pid_body, "classification") or _field(pid_body, "host_mode"),
                "source": "DIRECT HTTP PROBE + RETURNED /health,/whoami IDENTITY",
                "endpoint_note": "probe failure = CURRENT ENDPOINT UNREACHABLE, NOT machine off",
            },
            "original_dashboard": original_dashboard,
            "surrogate": {"endpoint": _P1_SURR[k], "identity": surr_id,
                          "state": surr["state"], "code": surr["code"],
                          "probe_ts": surr["probe_ts"], "last_ok": surr["last_ok"], "last_fail": surr["last_fail"],
                          "source": "DIRECT HTTP PROBE (HQ-hosted surrogate — separate from physical)"},
            "operating_mode": op_mode,
        }
        if k in _P1_HISTORICAL:
            entry["historical_endpoint"] = {**_P1_HISTORICAL[k], "source": "HISTORICAL CONFIGURATION — not probed for live status"}
        out["ceos"][k] = entry
    hq = _p1_http("dash_hq", _P1_DASH["hq"])
    out["ceos"]["hq"] = {
        "name": "Claude HQ",
        "dashboard": {"endpoint": _P1_DASH["hq"],
                      **{kk: hq[kk] for kk in ("state", "code", "detail", "probe_ts", "last_ok", "last_fail")}},
        "mind": {"state": "NOT TESTED",
                 "note": "Claude HQ mind = the Claude Code CLI session, not a pollable local service"},
        "operating_mode": "LOCAL DASHBOARD ONLY" if hq["state"] == "LIVE" else "UNKNOWN",
        "evidence": "fresh direct HTTP probe of :8850 (dashboard process only)",
    }
    wdash = _p1_http("dash_wren", _P1_DASH["wren"])
    wconc = _p1_http("dash_wren_conc", _P1_DASH["wren_concierge"])
    procs = _p1_procs()
    lastreply = _p1_last_wren_reply()

    def _ps(pids):
        return {"state": "LIVE" if pids else "UNREACHABLE", "pids": pids, "count": len(pids)}

    dup = []
    if len(procs.get("wren_mind", [])) > 1:
        dup.append("wren_evolution_loop x%d" % len(procs["wren_mind"]))
    out["ceos"]["wren"] = {
        "name": "Wren",
        "dashboard": {"endpoint": _P1_DASH["wren"],
                      **{kk: wdash[kk] for kk in ("state", "code", "detail", "probe_ts", "last_ok", "last_fail")},
                      "means": "WREN DASHBOARD AVAILABLE — does NOT imply Wren mind responsive"},
        "mind_runtime": _ps(procs.get("wren_mind", [])),
        "watcher": _ps(procs.get("wren_watcher", [])),
        "concierge": {"endpoint": _P1_DASH["wren_concierge"],
                      **{kk: wconc[kk] for kk in ("state", "code", "probe_ts")},
                      "proc": procs.get("wren_concierge_proc", [])},
        "duplicate_warning": dup or None,
        "last_genuine_reply": lastreply,
        "status_source": "process census (ps) + direct HTTP + chat registry (read-only)",
        "operating_mode": "LOCAL DASHBOARD ONLY" if wdash["state"] == "LIVE" else "UNKNOWN",
    }
    return out


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

    wren_msgs, hq_msgs, tp_msgs, acer_msgs, ross_msgs = [], [], [], [], []
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
                elif who == "ross": ross_msgs.append({"ts":ts,"who":"ross","text":text,"kind":kind})
            except Exception: pass
    hq_msgs = hq_msgs[-6:]
    wren_msgs = wren_msgs[-6:]
    tp_msgs = tp_msgs[-6:]
    ross_msgs = ross_msgs[-6:]
    acer_msgs = acer_msgs[-6:]

    # merge + sort — Ross 2026-07-05: Ross now 5th mind
    all_msgs = wren_msgs + hq_msgs + tp_msgs + acer_msgs + ross_msgs
    all_msgs.sort(key=lambda m: m.get("ts",""), reverse=True)
    return {
        "count": len(all_msgs),
        "messages": all_msgs[:30],
        "sources": {
            "wren": {"count": len(wren_msgs), "source": "qsb_wren_mind.json"},
            "hq":   {"count": len(hq_msgs),   "source": "boardroom commentary + F47"},
            "tp":   {"count": len(tp_msgs),   "source": "192.168.1.74:8871 physical worker + node_inbox"},
            "acer": {"count": len(acer_msgs), "source": "192.168.1.41:8872 physical worker (REAL Acer)"},
            "ross": {"count": len(ross_msgs), "source": "town_square posts from Ross"},
        },
        "note": "5-way REAL channel including Ross as founding CEO.",
    }


IPAD_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8">
<meta name=viewport content='width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no'>
<meta name=apple-mobile-web-app-capable content='yes'>
<meta name=apple-mobile-web-app-title content='QSB Tower'>
<meta name=apple-mobile-web-app-status-bar-style content='black-translucent'>
<title>QSB Tower · Ross Mission Control</title>
<style>
@keyframes ripple{0%{box-shadow:0 0 0 0 currentColor}70%{box-shadow:0 0 0 12px transparent}100%{box-shadow:0 0 0 0 transparent}}
@keyframes glow{0%,100%{filter:brightness(1)}50%{filter:brightness(1.4)}}
@keyframes slide{from{transform:translateY(-6px);opacity:0}to{transform:translateY(0);opacity:1}}
@keyframes spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}
@keyframes count{0%{color:#22d3ee}50%{color:#e8ecf3;text-shadow:0 0 8px #22d3ee}100%{color:#22d3ee}}
@keyframes phone-pulse{0%,100%{transform:scale(1);opacity:1}50%{transform:scale(1.5);opacity:0.4}}
</style>
<style>
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{background:#0b0d12;color:#e8ecf3;font:17px/1.4 -apple-system,BlinkMacSystemFont,'SF Pro',system-ui;margin:0;padding:16px;max-width:100vw;overflow-x:hidden;-webkit-touch-callout:none;-webkit-user-select:none;user-select:none;overscroll-behavior:none}
.btn:active,.tile:active{transform:scale(0.97);transition:transform 0.1s}
.btn{min-height:56px;touch-action:manipulation}
.sparkline{height:32px;width:100%}
h1{margin:0 0 4px;color:#eab308;font-size:1.6em}
.sub{color:#94a3b8;font-size:12px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;margin-bottom:14px}
.tile{padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:14px;min-height:80px;position:relative;overflow:hidden}
.tile .lbl{color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:.06em}
.tile .val{color:#22d3ee;font-size:28px;font-weight:700;font-variant-numeric:tabular-nums}
.tile .sub{color:#64748b;font-size:11px;margin-top:2px}
.btn{width:100%;padding:16px;background:#1e293b;color:#e8ecf3;border:1px solid #334155;border-radius:12px;font-size:16px;font-weight:600;margin-bottom:8px;cursor:pointer;text-align:left;display:flex;justify-content:space-between;align-items:center}
.btn.gold{background:linear-gradient(180deg,#eab308,#a16207);color:#000;border:none}
.btn.red{background:#ef4444;color:#fff;border:none}
.btn.blue{background:#3b82f6;color:#fff;border:none}
.chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600}
.chip.live{background:#10b981;color:#000}
.chip.off{background:#ef4444;color:#fff}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}
.live-dot{animation:pulse 1.4s infinite;display:inline-block;width:10px;height:10px;border-radius:50%;background:#10b981;margin-right:6px}
.ceo-row{display:flex;align-items:center;padding:10px;background:#0b1220;border-radius:10px;margin-bottom:6px}
.ceo-avatar{width:36px;height:36px;border-radius:50%;font-weight:800;color:#000;display:flex;align-items:center;justify-content:center;margin-right:10px}
.commentary-item{padding:8px 10px;background:#0b1220;border-radius:8px;margin-bottom:6px;font-size:13px}
.commentary-item .who{font-weight:700}
.section{margin-bottom:18px;transition:opacity 0.3s ease,transform 0.3s ease;animation:section-fadein 0.4s ease-out;position:relative}
@keyframes section-fadein{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
.section:hover{border-color:rgba(234,179,8,0.3)}
/* R3 Wren: pulse-glow on task-done · Acer: freshness badge */
@keyframes task-glow{0%,100%{box-shadow:0 0 0 rgba(16,185,129,0)}50%{box-shadow:0 0 18px rgba(16,185,129,0.5)}}
.section.just-updated{animation:task-glow 1.4s ease-out}
.freshness{position:absolute;top:8px;right:14px;color:#22d3ee;font-size:9.5px;text-transform:uppercase;letter-spacing:0.06em;opacity:0.65;font-family:ui-monospace,monospace}
.section-title{color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px}
</style></head><body>
<!-- Ross 2026-07-06: floating home button, every page. -->
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px' onclick='try{beep(700,50)}catch(e){}'>🏠</a>
<!-- Ross 2026-07-06: HQ-Claude stats strip on iPad. Live via /hq/stats. ADD not TAKE. -->
<div id=hq-stats-strip style="background:#0e1420;border:1px solid #eab30840;border-radius:8px;padding:8px 12px;margin-bottom:8px;display:flex;gap:14px;flex-wrap:wrap;font-family:ui-monospace,monospace;font-size:11px;color:#94a3b8">
  <div><span style="color:#eab308;font-weight:800">🧠 HQ</span> · r<b id=ipad-hq-rank style="color:#e8ecf3">?</b> · <b id=ipad-hq-brain style="color:#e8ecf3">opus</b></div>
  <div>today: <b id=ipad-hq-today style="color:#eab308">?</b> · prop <b id=ipad-hq-prop style="color:#22d3ee">?</b> · sign <b id=ipad-hq-signoff style="color:#a78bfa">?</b> · close <b id=ipad-hq-done style="color:#10b981">?</b></div>
  <div>board <b id=ipad-hq-open style="color:#e8ecf3">?</b>o · <b id=ipad-hq-inprog style="color:#f59e0b">?</b>ip · <b id=ipad-hq-total style="color:#94a3b8">?</b>t</div>
  <div>ledger <b id=ipad-hq-ledger style="color:#e8ecf3">?</b></div>
</div>
<script>
async function ipadHqStatsTick(){
  try{
    const d = await (await fetch('/hq/stats',{cache:'no-store'})).json();
    const set=(id,v)=>{const e=document.getElementById(id);if(e && v!==undefined && v!==null) e.textContent=v};
    set('ipad-hq-rank', d.rank);
    if (d.brain) set('ipad-hq-brain', String(d.brain).replace('claude-',''));
    set('ipad-hq-today', d.today_actions_total); set('ipad-hq-prop', d.today_proposed);
    set('ipad-hq-signoff', d.today_peer_signoffs); set('ipad-hq-done', d.today_closes);
    const b=d.board||{};
    set('ipad-hq-open', b.open); set('ipad-hq-inprog', b.in_progress);
    set('ipad-hq-total', b.total); set('ipad-hq-ledger', d.ledger_entries);
  }catch(e){}
}
setInterval(ipadHqStatsTick, 5000);
setTimeout(ipadHqStatsTick, 300);
</script>
<!-- #194 TOP MEGA-MENU sticky · access everywhere -->
<div style='position:sticky;top:0;background:#0b0d12;padding:8px 6px;margin:-16px -16px 8px;border-bottom:2px solid #eab308;z-index:200;box-shadow:0 4px 12px rgba(0,0,0,0.6)'>
  <div style='display:flex;gap:4px;overflow-x:auto;padding:0 4px;-webkit-overflow-scrolling:touch'>
    <a href='#sec-post' style='background:#eab308;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>⭐ Post</a>
    <a href='#sec-glance' style='background:#22d3ee;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>📊 Stats</a>
    <a href='#sec-council' style='background:#a78bfa;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>👥 Council</a>
    <a href='#sec-dashes' style='background:#3b82f6;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🖥️ Dashes</a>
    <a href='#sec-controls' style='background:#f59e0b;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>⚡ Controls</a>
    <a href='#sec-brain' style='background:#ec4899;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🧠 Brain</a>
    <a href='#sec-annex' style='background:#f43f5e;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🏠 Annex</a>
    <a href='#sec-revs' style='background:#eab308;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🎛️ Revs</a>
    <a href='#sec-gpu' style='background:#10b981;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🎮 GPU</a>
    <a href='#sec-safety' style='background:#ef4444;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🛑 Safety</a>
    <a href='#sec-diag' style='background:#3b82f6;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🔧 Diag</a>
    <a href='#sec-checklist' style='background:#a78bfa;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>☑ Checklist</a>
    <a href='#sec-clicli' style='background:#000;color:#a7f3d0;border:2px solid #eab308;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🖥️ Ross ↔ Claude CLI</a>
    <a href='#sec-scoreboard' style='background:#facc15;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🏆 Scoreboard</a>
    <a href='#sec-skyscraper' style='background:#000;color:#facc15;border:2px solid #facc15;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🏢 Skyscraper</a>
    <a href='#sec-bank' style='background:#10b981;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🏦 Bank</a>
    <a href='#sec-trader-motion' style='background:#22d3ee;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🎬 Motion</a>
    <a href='#sec-healer' style='background:#10b981;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🩺 Healer</a>
    <a href='#sec-rules-board' style='background:#a78bfa;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>📜 Rules</a>
    <a href='#sec-notice' style='background:#f59e0b;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>📌 Notices</a>
    <a href='#sec-evolution' style='background:#ec4899;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🧬 Evolution</a>
    <a href='#sec-trader-stats' style='background:#facc15;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>📊 Stats</a>
    <a href='#sec-tour' style='background:linear-gradient(90deg,#facc15,#eab308);color:#000;padding:8px 14px;border-radius:6px;text-decoration:none;font-weight:900;font-size:12px;white-space:nowrap;box-shadow:0 0 12px rgba(234,179,8,0.4)' onclick='beep(700,50)'>🏛️ TOUR</a>
    <a href='#sec-actions' style='background:#8b5cf6;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🎯 Actions</a>
    <a href='#sec-cli' style='background:#10b981;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>💻 CLI</a>
    <a href='#sec-voice' style='background:#ef4444;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🎤 Voice</a>
    <a href='#sec-chat' style='background:#0ea5e9;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>💬 Chat</a>
    <a href='#sec-task' style='background:#84cc16;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>➕ Task</a>
    <a href='#sec-log' style='background:#64748b;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>📜 Logs</a>
    <a href='#sec-embed' style='background:#0284c7;color:#fff;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>🖼️ Embed</a>
    <a href='#sec-commentary' style='background:#94a3b8;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap' onclick='beep(700,50)'>💭 Feed</a>
    <a href='#sec-commentary' style='background:#22d3ee;color:#000;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:800;font-size:12px;white-space:nowrap' onclick='beep(700,50);setTimeout(toggleLiveVoice,600)'>📢 LIVE VOICE</a>
    <a href='/tasks' style='background:#1e293b;color:#eab308;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap;border:1px solid #eab308'>📋 tasks →</a>
    <a href='/town_square' style='background:#1e293b;color:#3b82f6;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap;border:1px solid #3b82f6'>🗣️ town →</a>
    <a href='/council' style='background:#1e293b;color:#a78bfa;padding:8px 12px;border-radius:6px;text-decoration:none;font-weight:700;font-size:12px;white-space:nowrap;border:1px solid #a78bfa'>👥 council →</a>
    <a href='javascript:location.reload(true)' style='background:#1e293b;color:#94a3b8;padding:8px 12px;border-radius:6px;text-decoration:none;font-size:12px;white-space:nowrap'>🔄</a>
  </div>
</div>
<!-- #187 nav bar -->
<div style='display:flex;gap:6px;margin-bottom:10px;flex-wrap:wrap'>
  <button class='btn' style='min-height:44px;padding:8px 14px;flex:0 0 auto' onclick='history.back()'>◀ back</button>
  <button class='btn' style='min-height:44px;padding:8px 14px;flex:0 0 auto' onclick='history.forward()'>▶ forward</button>
  <button class='btn' style='min-height:44px;padding:8px 14px;flex:0 0 auto' onclick='location.href="/ipad"'>🏠 home</button>
  <button class='btn' style='min-height:44px;padding:8px 14px;flex:0 0 auto' onclick='location.reload(true)'>🔄 reload</button>
  <button class='btn' style='min-height:44px;padding:8px 14px;flex:0 0 auto' onclick='cycleDash(-1)'>◀◀ prev dash</button>
  <button class='btn' style='min-height:44px;padding:8px 14px;flex:0 0 auto' onclick='cycleDash(1)'>▶▶ next dash</button>
</div>
<h1>🏢 QSB Tower · <span style='color:#e8ecf3'>Mission Control</span></h1>
<div class=sub>Ross command deck · live 2s refresh · <span id=live-clock style='color:#22d3ee;font-family:ui-monospace,monospace'></span></div>

<!-- #200 OFFLINE banner -->
<div id=offline-banner style='display:none;padding:10px 14px;background:#7f1d1d;color:#fff;border-radius:10px;margin-bottom:10px;font-weight:800;text-align:center;animation:pulse-red 1.5s ease-in-out infinite'>
  🚨 OFFLINE — no network reach to HQ · running from cache · retry auto
</div>
<style>@keyframes pulse-red{0%,100%{background:#7f1d1d}50%{background:#dc2626}}</style>

<!-- #200 ACCESS-LOSS banner -->
<div id=access-banner style='display:none;padding:10px 14px;background:#78350f;color:#fff;border-radius:10px;margin-bottom:10px;font-weight:800;text-align:center'>⚠ <span id=access-banner-text>access loss detected</span></div>

<!-- #200 TRADER TICKER strip -->
<div style='background:#000;border:1px solid #22334a;border-radius:10px;padding:8px 10px;margin-bottom:10px;overflow:hidden;white-space:nowrap'>
  <div id=trader-ticker style='display:inline-block;animation:tick-scroll 60s linear infinite;color:#a7f3d0;font-family:ui-monospace,monospace;font-size:12px'>💰 loading trader ticker...</div>
</div>
<style>@keyframes tick-scroll{0%{transform:translateX(100%)}100%{transform:translateX(-100%)}}</style>

<!-- Ross post box - #182 -->
<div id=sec-post style='margin-bottom:14px;padding:12px;background:#0e1420;border:2px solid #eab308;border-radius:14px;scroll-margin-top:70px'>
  <div style='color:#eab308;font-size:11px;text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px'>⭐ Ross · post to town square</div>
  <div style='display:flex;gap:8px'>
    <input id=ross-msg style='flex:1;background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:10px;font-size:15px' placeholder="type your line..." />
    <button onclick=rossPost() style='background:linear-gradient(180deg,#eab308,#a16207);color:#000;border:none;padding:10px 16px;border-radius:8px;font-weight:800;font-size:15px'>POST</button>
  </div>
</div>

<div class=section id=sec-glance style="scroll-margin-top:70px"><div class=section-title>📊 tower at-a-glance</div>
  <div class=grid>
    <div class=tile><span class=lbl>tasks</span><div class=val id=t-total>—</div><span class=sub id=t-sub>—</span></div>
    <div class=tile><span class=lbl>fleet PnL</span><div class=val id=fleet-pnl>—</div><span class=sub id=fleet-sub>—</span></div>
    <div class=tile><span class=lbl>brain calls / hr</span><div class=val id=brain-hr>—</div><span class=sub id=brain-sub>—</span></div>
    <div class=tile><span class=lbl>CEOs live</span><div class=val id=ceos-live>—</div><span class=sub>of 4</span></div>
  </div>
</div>

<div class=section id=sec-council style="scroll-margin-top:70px"><div class=section-title>👥 council</div>
  <div id=ceo-list></div>
</div>

<div class=section id=sec-dashes style="scroll-margin-top:70px"><div class=section-title>🖥️ all dashboards</div>
  <a class='btn gold' href='/tasks' target=_blank>📋 task board →</a>
  <a class='btn blue' href='/town_square' target=_blank>🗣️ town square →</a>
  <a class='btn blue' href='/council' target=_blank>👥 council →</a>
  <a class='btn blue' href='/traders' target=_blank>💰 traders →</a>
  <a class='btn blue' href='/timeline' target=_blank>📈 timeline →</a>
  <a class='btn blue' href='/rules' target=_blank>📜 rules →</a>
  <a class='btn' href='http://192.168.1.72:8850' target=_blank>🟡 HQ dash 8850 →</a>
  <a class='btn' href='http://192.168.1.72:8851' target=_blank>🟪 Wren dash 8851 →</a>
  <a class='btn' href='http://192.168.1.74:8871/health' target=_blank>🟦 TP worker :8871 →</a>
  <a class='btn' href='http://192.168.1.41:8872/health' target=_blank>🟧 Acer worker :8872 →</a>
  <a class='btn' href='/proxy/oracle' target=_blank>🏠 Oracle annex dash →</a>
  <a class='btn' href='http://127.0.0.1:9201/dash' target=_blank>🏠 HQ annex dash →</a>
  <a class='btn' href='http://127.0.0.1:9202/dash' target=_blank>🏠 Wren annex dash →</a>
  <a class='btn' href='/ipad' target=_blank>📱 iPad cockpit (this) →</a>
  <a class='btn' href='/proxy/studio' target=_blank>🎬 Studio 8849 →</a>
  <a class='btn' href='/proxy/lumen' target=_blank>💡 Lumen 8848 →</a>
  <a class='btn' href='http://127.0.0.1:8846' target=_blank>🚁 Cockpit3D 8846 →</a>
  <a class='btn' href='/proxy/traders_live' target=_blank>📊 Traders 8847 →</a>
  <a class='btn' href='/traders' target=_blank>💰 Competition board →</a>
  <a class='btn' href='/annexes' target=_blank>🏠 Annex fleet JSON →</a>
  <a class='btn' href='/annexes/leaderboard' target=_blank>🏆 Annex reward leaderboard →</a>
  <a class='btn' href='/teamwork' target=_blank>🤝 Teamwork matrix →</a>
  <a class='btn' href='javascript:history.back()'>◀ back</a>
</div>
<div class=section id=sec-controls style="scroll-margin-top:70px"><div class=section-title>⚡ quick controls</div>
  <button class='btn' onclick='kickWren()'>⚡ kick Wren</button>
  <button class='btn' onclick='dispatchTeam()'>🚀 dispatch team</button>
  <button class='btn' onclick='pingTP()'>📞 ping TP</button>
  <button class='btn' onclick='pingAcer()'>📞 ping Acer</button>
  <button class='btn red' onclick='emergencyPause()'>⏸ emergency pause</button>
</div>

<div class=section id=sec-brain style="scroll-margin-top:70px"><div class=section-title>📊 brain workers · live sparklines</div>
  <div id=brain-panel style='display:grid;grid-template-columns:repeat(3,1fr);gap:8px'></div>
</div>
<div class=section id=sec-annex style="scroll-margin-top:70px"><div class=section-title>🏠 annex fleet</div>
  <div id=annex-panel style='display:grid;grid-template-columns:repeat(2,1fr);gap:8px'></div>
</div>

<!-- #200 REV GAUGES -->
<div class=section id=sec-revs style="scroll-margin-top:70px"><div class=section-title>🎛️ rev gauges · CEO velocity</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div id=rev-panel style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px'>
      <div class=rev-tile data-ceo=hq_claude style='background:#000;padding:10px;border-radius:10px;border:1px solid #22334a;text-align:center'>
        <div style='color:#eab308;font-size:11px;font-weight:800'>HQ</div>
        <svg viewBox='0 0 100 60' style='width:100%;height:60px'>
          <path d='M 10 50 A 40 40 0 0 1 90 50' stroke='#22334a' stroke-width='6' fill='none'/>
          <path id=rev-hq_claude d='M 10 50 A 40 40 0 0 1 90 50' stroke='#eab308' stroke-width='6' fill='none' stroke-dasharray='0 200'/>
          <text id=rev-hq_claude-txt x='50' y='45' fill='#eab308' font-size='16' text-anchor='middle' font-weight='900'>0</text>
        </svg>
        <div style='color:#94a3b8;font-size:10px'>tasks/hr</div>
      </div>
      <div class=rev-tile data-ceo=wren style='background:#000;padding:10px;border-radius:10px;border:1px solid #22334a;text-align:center'>
        <div style='color:#a78bfa;font-size:11px;font-weight:800'>WREN</div>
        <svg viewBox='0 0 100 60' style='width:100%;height:60px'>
          <path d='M 10 50 A 40 40 0 0 1 90 50' stroke='#22334a' stroke-width='6' fill='none'/>
          <path id=rev-wren d='M 10 50 A 40 40 0 0 1 90 50' stroke='#a78bfa' stroke-width='6' fill='none' stroke-dasharray='0 200'/>
          <text id=rev-wren-txt x='50' y='45' fill='#a78bfa' font-size='16' text-anchor='middle' font-weight='900'>0</text>
        </svg>
        <div style='color:#94a3b8;font-size:10px'>tasks/hr</div>
      </div>
      <div class=rev-tile data-ceo=tp_pip style='background:#000;padding:10px;border-radius:10px;border:1px solid #22334a;text-align:center'>
        <div style='color:#22d3ee;font-size:11px;font-weight:800'>TP</div>
        <svg viewBox='0 0 100 60' style='width:100%;height:60px'>
          <path d='M 10 50 A 40 40 0 0 1 90 50' stroke='#22334a' stroke-width='6' fill='none'/>
          <path id=rev-tp_pip d='M 10 50 A 40 40 0 0 1 90 50' stroke='#22d3ee' stroke-width='6' fill='none' stroke-dasharray='0 200'/>
          <text id=rev-tp_pip-txt x='50' y='45' fill='#22d3ee' font-size='16' text-anchor='middle' font-weight='900'>0</text>
        </svg>
        <div style='color:#94a3b8;font-size:10px'>tasks/hr</div>
      </div>
      <div class=rev-tile data-ceo=acer_cass style='background:#000;padding:10px;border-radius:10px;border:1px solid #22334a;text-align:center'>
        <div style='color:#f59e0b;font-size:11px;font-weight:800'>ACER</div>
        <svg viewBox='0 0 100 60' style='width:100%;height:60px'>
          <path d='M 10 50 A 40 40 0 0 1 90 50' stroke='#22334a' stroke-width='6' fill='none'/>
          <path id=rev-acer_cass d='M 10 50 A 40 40 0 0 1 90 50' stroke='#f59e0b' stroke-width='6' fill='none' stroke-dasharray='0 200'/>
          <text id=rev-acer_cass-txt x='50' y='45' fill='#f59e0b' font-size='16' text-anchor='middle' font-weight='900'>0</text>
        </svg>
        <div style='color:#94a3b8;font-size:10px'>tasks/hr</div>
      </div>
    </div>
  </div>
</div>

<!-- #200 GPU tile -->
<div class=section id=sec-gpu style="scroll-margin-top:70px"><div class=section-title>🎮 GPU · HQ box</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div id=gpu-panel style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px'>
      <div class=tile><span class=lbl>utilisation</span><div class=val id=gpu-util>—</div><span class=sub id=gpu-name>—</span></div>
      <div class=tile><span class=lbl>memory</span><div class=val id=gpu-mem>—</div><span class=sub>MB used</span></div>
      <div class=tile><span class=lbl>temp</span><div class=val id=gpu-temp>—</div><span class=sub>°C</span></div>
      <div class=tile><span class=lbl>power</span><div class=val id=gpu-pwr>—</div><span class=sub>W</span></div>
    </div>
  </div>
</div>

<!-- #200 KILL-SWITCH panel + BACKUP + SCREENSHOT -->
<div class=section id=sec-safety style="scroll-margin-top:70px"><div class=section-title>🛑 safety · kill switches + backup + snapshot</div>
  <div style='padding:12px;background:#0e1420;border:2px solid #ef4444;border-radius:12px'>
    <div style='color:#94a3b8;font-size:12px;margin-bottom:8px'>One-tap emergency controls · immediate effect · audited.</div>
    <div style='display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px'>
      <button class='btn' style='min-height:52px;background:#ef4444;color:#fff;font-weight:900' onclick='killSwitch("autoapply")'>🛑 kill auto-apply</button>
      <button class='btn' style='min-height:52px;background:#ef4444;color:#fff;font-weight:900' onclick='killSwitch("agentic")'>🛑 kill agentic loops</button>
      <button class='btn' style='min-height:52px;background:#ef4444;color:#fff;font-weight:900' onclick='killSwitch("wren")'>🛑 kill Wren agent</button>
    </div>
    <div style='display:grid;grid-template-columns:repeat(2,1fr);gap:8px'>
      <button class='btn' style='min-height:52px;background:#3b82f6;color:#fff;font-weight:800' onclick='backupNow()'>💾 backup registries now</button>
      <button class='btn' style='min-height:52px;background:#10b981;color:#000;font-weight:800' onclick='snapToTelegram()'>📸 snapshot → Telegram</button>
    </div>
    <div id=safety-status style='margin-top:8px;padding:6px 10px;background:#0b1220;border-radius:6px;color:#94a3b8;font-size:12px'>ready.</div>
  </div>
</div>

<!-- #201 DIAGNOSTICS tab -->
<div class=section id=sec-diag style="scroll-margin-top:70px"><div class=section-title>🔧 diagnostics · full sweep</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div style='color:#94a3b8;font-size:12px;margin-bottom:8px'>Endpoint reach · disk · memory · GPU · ollama · task-board integrity · brain-router smoke · gates status.</div>
    <div style='display:flex;gap:8px;margin-bottom:10px'>
      <button class='btn' style='flex:1;min-height:52px;background:#3b82f6;color:#fff;font-weight:900;font-size:15px' onclick='runDiag()'>🔧 RUN FULL SWEEP</button>
      <button class='btn' style='min-height:52px;background:#0b1220;color:#e8ecf3;padding:0 14px' onclick='document.getElementById("diag-out").textContent=""'>🗑 clear</button>
    </div>
    <div id=diag-summary style='padding:10px 12px;background:#0b1220;border-radius:8px;font-family:ui-monospace,monospace;font-size:12px;color:#94a3b8;margin-bottom:8px'>tap RUN to sweep · autoruns every 60s once loaded</div>
    <pre id=diag-out style='background:#000;color:#a7f3d0;padding:12px;border-radius:8px;font-size:11.5px;max-height:340px;overflow-y:auto;font-family:ui-monospace,monospace;white-space:pre-wrap;border:1px solid #22334a'>no sweep yet.</pre>
  </div>
</div>

<!-- #200 TASK CHECKLIST panel -->
<div class=section id=sec-checklist style="scroll-margin-top:70px"><div class=section-title>☑ interactive task checklist · in-flight</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div id=checklist-panel style='max-height:340px;overflow-y:auto;font-size:12.5px'>loading...</div>
  </div>
</div>

<div class=section id=sec-actions style="scroll-margin-top:70px"><div class=section-title>⚡ MORE actions</div>
  <button class='btn' onclick='assignRandom("hq_claude")'>📋 assign HQ a task</button>
  <button class='btn' onclick='assignRandom("wren")'>🎨 assign Wren a task</button>
  <button class='btn' onclick='assignRandom("tp_pip")'>🔍 assign TP a task</button>
  <button class='btn' onclick='assignRandom("acer_cass")'>🖥️ assign Acer a task</button>
  <button class='btn' onclick='forceRefreshAll()'>🔄 force refresh all dashes</button>
  <button class='btn' onclick='massSignoff()'>✅ mass-signoff awaiting</button>
  <button class='btn' onclick='cullDuds()'>🗑️ cull TIER_0 trader duds</button>
  <button class='btn' onclick='runQualifier()'>📈 re-run trader qualifier</button>
</div>
<!-- #193 sound toggle -->
<div style='margin-bottom:8px'>
  <button class='btn' style='width:100%;background:#0e1420;color:#22d3ee;border:1px solid #22334a' onclick='toggleSound();beep(880,60)'>🔊 <span id=sound-state>sound: ON 🔊</span></button>
</div>
<!-- #191 INLINE TASK CREATE -->
<div class=section id=sec-task style="scroll-margin-top:70px"><div class=section-title>➕ create task (inline)</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <input id=new-task-title style='width:100%;background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:12px;font-size:15px;margin-bottom:6px' placeholder='task title' />
    <textarea id=new-task-desc style='width:100%;background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:10px;font-size:13px;min-height:60px;margin-bottom:6px' placeholder='description (optional)'></textarea>
    <div style='display:flex;gap:8px;flex-wrap:wrap'>
      <select id=new-task-assign style='background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:10px;flex:1'>
        <option value=''>assign to...</option><option value=hq_claude>HQ-Claude</option><option value=wren>Wren</option><option value=tp_pip>TP-Pip</option><option value=acer_cass>Acer-Cass</option>
      </select>
      <select id=new-task-pri style='background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:10px'>
        <option value=normal>normal</option><option value=high>high</option><option value=urgent>urgent</option><option value=low>low</option>
      </select>
      <button class='btn' style='min-height:44px;background:#10b981;color:#000;font-weight:800' onclick='createTask()'>➕ CREATE</button>
    </div>
  </div>
</div>
<!-- #191 LOG TAIL VIEWER -->
<div class=section id=sec-log style="scroll-margin-top:70px"><div class=section-title>📜 log tail viewer</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px'>
      <button class='btn' style='min-height:40px;flex:1' onclick='showLog("/tmp/hub_boot.log")'>hub</button>
      <button class='btn' style='min-height:40px;flex:1' onclick='showLog("/tmp/heartbeat.log")'>heartbeat</button>
      <button class='btn' style='min-height:40px;flex:1' onclick='showLog("/tmp/council_watcher.log")'>watcher</button>
      <button class='btn' style='min-height:40px;flex:1' onclick='showLog("/tmp/wren_puller.log")'>wren puller</button>
    </div>
    <pre id=log-content style='background:#000;color:#a7f3d0;padding:8px;border-radius:6px;font-size:10.5px;max-height:200px;overflow-y:auto;font-family:ui-monospace,monospace'>select a log</pre>
  </div>
</div>
<!-- #196 VOICE panel — massive upgrade -->
<div class=section id=sec-voice style="scroll-margin-top:70px"><div class=section-title>🎤 voice command center · listen + speak</div>
  <div style='padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:14px'>
    <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:10px'>
      <button class='btn voice-btn' data-ceo=hq_claude style='min-height:72px;background:#eab308;color:#000;font-weight:900;font-size:16px;border:none' onclick='voiceChat("hq_claude","HQ-Claude")'>🎤 HQ</button>
      <button class='btn voice-btn' data-ceo=wren style='min-height:72px;background:#a78bfa;color:#000;font-weight:900;font-size:16px;border:none' onclick='voiceChat("wren","Wren")'>🎤 Wren</button>
      <button class='btn voice-btn' data-ceo=tp_pip style='min-height:72px;background:#22d3ee;color:#000;font-weight:900;font-size:16px;border:none' onclick='voiceChat("tp_pip","TP-Pip")'>🎤 TP</button>
      <button class='btn voice-btn' data-ceo=acer_cass style='min-height:72px;background:#f59e0b;color:#000;font-weight:900;font-size:16px;border:none' onclick='voiceChat("acer_cass","Acer-Cass")'>🎤 Acer</button>
    </div>
    <button class='btn voice-btn' data-ceo=ALL style='width:100%;min-height:60px;background:#e8ecf3;color:#000;font-weight:900;font-size:15px;margin-bottom:8px;border:none' onclick='voiceChat("ALL","All 4 CEOs")'>🎤 BROADCAST to all 4</button>
    <!-- 2026-07-06 Ross rule: TP + Acer are Claude themselves — no teacher. Only Wren (qwen) needs it. -->
    <div style='background:#0b1220;padding:8px;border-radius:8px;margin-bottom:8px'>
      <div style='color:#94a3b8;font-size:10px;text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px'>📚 Wren teacher (qwen watches Claude)</div>
      <div style='display:flex;gap:6px;margin-bottom:6px'>
        <button id=teacher-wren class='btn' style='flex:1;min-height:44px;background:#a78bfa;color:#000;font-weight:800;border:none' onclick='ceoTeacherToggle("wren")'>📚 Wren teacher <span id=teacher-wren-st>?</span></button>
        <a href='/wren/learnings' target=_blank class='btn' style='flex:1;min-height:44px;background:#a7f3d0;color:#000;font-weight:700;font-size:12px;text-decoration:none;display:flex;align-items:center;justify-content:center;border-radius:8px'>📖 Wren journal →</a>
      </div>
      <div style='color:#64748b;font-size:10px;font-family:ui-monospace,monospace'>HQ · TP · Acer are all Claude Code CLIs on own PCs — no teacher needed</div>
    </div>
    <button id=voice-stop-btn class='btn' style='width:100%;min-height:44px;background:#ef4444;color:#fff;font-weight:800;display:none;margin-bottom:8px' onclick='stopListening()'>⏹ STOP LISTENING</button>
    <canvas id=voice-waveform style='width:100%;height:60px;background:#000;border-radius:8px;margin:8px 0 4px;display:none'></canvas>
    <div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px'>
      <button class='btn' style='min-height:38px;flex:1 1 30%;background:#0b1220;font-size:11.5px' onclick='voicePreset("what is the tower status")'>📊 status</button>
      <button class='btn' style='min-height:38px;flex:1 1 30%;background:#0b1220;font-size:11.5px' onclick='voicePreset("any alerts or issues")'>🚨 alerts</button>
      <button class='btn' style='min-height:38px;flex:1 1 30%;background:#0b1220;font-size:11.5px' onclick='voicePreset("who is working now")'>👥 who</button>
      <button class='btn' style='min-height:38px;flex:1 1 30%;background:#0b1220;font-size:11.5px' onclick='voicePreset("top open tasks")'>📋 tasks</button>
      <button class='btn' style='min-height:38px;flex:1 1 30%;background:#0b1220;font-size:11.5px' onclick='voicePreset("fleet PnL right now")'>💰 PnL</button>
      <button class='btn' style='min-height:38px;flex:1 1 30%;background:#0b1220;font-size:11.5px' onclick='voicePreset("read the last 5 town square posts")'>💬 recap</button>
    </div>
    <div style='display:flex;gap:6px;margin-bottom:8px'>
      <button class='btn' style='flex:1;background:#0b1220;font-size:11.5px' onclick='toggleContinuous()'>👂 <span id=continuous-state>continuous: OFF</span></button>
      <button class='btn' style='flex:1;background:#0b1220;font-size:11.5px' onclick='toggleAutoSpeak()'>🔊 <span id=autospeak-state>auto-speak: ON</span></button>
      <button class='btn' style='flex:1;background:#0b1220;font-size:11.5px' onclick='clearVoiceLog()'>🗑 clear log</button>
    </div>
    <div id=voice-status style='font-size:12px;color:#94a3b8;margin-top:8px;padding:8px 10px;background:#0b1220;border-radius:6px;border:1px solid #22334a'>tap a mic + speak · try the presets above</div>
    <div id=voice-transcript style='font-size:14px;color:#a7f3d0;margin-top:6px;padding:8px 10px;background:#000;border-radius:6px;min-height:24px;font-family:ui-monospace,monospace;display:none'></div>
    <div id=voice-log style='max-height:280px;overflow-y:auto;font-size:12.5px;margin-top:8px'></div>
  </div>
</div>
<style>
@keyframes mic-listen{0%,100%{box-shadow:0 0 0 0 rgba(239,68,68,0.7)}50%{box-shadow:0 0 0 20px rgba(239,68,68,0)}}
.voice-btn.listening{animation:mic-listen 1.4s ease-out infinite;filter:brightness(1.2)}
.voice-btn:active{transform:scale(0.97)}
</style>
<!-- #197 CLI tab — SIMPLIFIED per Ross "to confusing" -->
<div class=section id=sec-cli style="scroll-margin-top:70px"><div class=section-title>💻 terminal · run shell commands on HQ box</div>
  <div style='padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div style='color:#94a3b8;font-size:12px;margin-bottom:12px'>Type a command · tap RUN · output appears below. Safe-only (rm/sudo/kill blocked).</div>
    <div style='display:flex;gap:10px;margin-bottom:10px'>
      <input id=cli-cmd style='flex:1;background:#000;color:#a7f3d0;border:1px solid #22334a;border-radius:10px;padding:16px;font-family:ui-monospace,monospace;font-size:15px' placeholder='e.g.  uptime' onkeypress='if(event.key==="Enter")runCli()' />
      <button class='btn' style='min-height:56px;background:#10b981;color:#000;font-weight:900;font-size:16px;padding:0 24px' onclick='runCli()'>RUN</button>
    </div>
    <div style='display:flex;gap:10px;margin-bottom:12px'>
      <button class='btn' style='flex:1;min-height:48px;background:#0b1220;font-size:13px;font-weight:700' onclick='cliQuick("uptime && free -h | head -2 && df -h / | tail -1")'>📊 system health</button>
      <button class='btn' style='flex:1;min-height:48px;background:#0b1220;font-size:13px;font-weight:700' onclick='cliQuick("ps -eo pid,user,cmd ww | awk \\"$3 ~ /python/ && $4 ~ /qsb_/\\" | wc -l && echo qsb procs alive")'>🏛 tower alive?</button>
      <button class='btn' style='flex:1;min-height:48px;background:#0b1220;font-size:13px;font-weight:700' onclick='cliClear()'>🗑 clear</button>
    </div>
    <pre id=cli-out style='background:#000;color:#a7f3d0;padding:12px;border-radius:8px;font-size:12px;max-height:320px;overflow-y:auto;font-family:ui-monospace,monospace;white-space:pre-wrap;border:1px solid #22334a'>ready · type a command above
</pre>
  </div>
</div>
<!-- #187 CHAT panel — Ross chats with any CEO -->
<div class=section id=sec-chat style="scroll-margin-top:70px"><div class=section-title>💬 chat with council</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div style='display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px'>
      <button class='btn' style='min-height:44px;flex:1;background:#eab308;color:#000' onclick='setChatTarget("hq_claude","HQ")'>HQ</button>
      <button class='btn' style='min-height:44px;flex:1;background:#a78bfa;color:#000' onclick='setChatTarget("wren","Wren")'>Wren</button>
      <button class='btn' style='min-height:44px;flex:1;background:#22d3ee;color:#000' onclick='setChatTarget("tp_pip","TP")'>TP</button>
      <button class='btn' style='min-height:44px;flex:1;background:#f59e0b;color:#000' onclick='setChatTarget("acer_cass","Acer")'>Acer</button>
      <button class='btn' style='min-height:44px;flex:1;background:#e8ecf3;color:#000' onclick='setChatTarget("ALL","All")'>All</button>
    </div>
    <div style='display:flex;gap:8px;margin-bottom:8px'>
      <input id=chat-msg style='flex:1;background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:12px;font-size:15px' placeholder='type message...' onkeypress='if(event.key==="Enter")sendChat()' />
      <button class='btn' style='min-height:44px;padding:12px 20px;background:#10b981;color:#000;font-weight:800' onclick='sendChat()'>SEND</button>
    </div>
    <div id=chat-target style='font-size:11px;color:#94a3b8;margin-bottom:6px'>target: <b style='color:#eab308'>HQ-Claude</b></div>
    <div id=chat-log style='max-height:250px;overflow-y:auto;font-size:13px'></div>
  </div>
</div>
<!-- #187 EMBEDDED dashes — see each CEO live -->
<div class=section id=sec-embed style="scroll-margin-top:70px"><div class=section-title>🖥️ live embedded dashes</div>
  <div style='display:grid;grid-template-columns:1fr 1fr;gap:8px'>
    <div><div style='color:#eab308;font-size:11px;margin-bottom:4px'>HQ (8850) <a href='/proxy/hq' target=_blank style='color:#eab308;font-size:9px'>↗</a></div><iframe src='/proxy/hq' style='width:100%;height:280px;border:1px solid #22334a;border-radius:8px'></iframe></div>
    <div><div style='color:#a78bfa;font-size:11px;margin-bottom:4px'>Wren (8851) <a href='/proxy/wren' target=_blank style='color:#a78bfa;font-size:9px'>↗</a></div><iframe src='/proxy/wren' style='width:100%;height:280px;border:1px solid #22334a;border-radius:8px'></iframe></div>
    <div><div style='color:#22d3ee;font-size:11px;margin-bottom:4px'>TP (9110) <a href='/proxy/tp' target=_blank style='color:#22d3ee;font-size:9px'>↗</a></div><iframe src='/proxy/tp' style='width:100%;height:280px;border:1px solid #22334a;border-radius:8px'></iframe></div>
    <div><div style='color:#f59e0b;font-size:11px;margin-bottom:4px'>Acer (9000) <a href='/proxy/acer' target=_blank style='color:#f59e0b;font-size:9px'>↗</a></div><iframe src='/proxy/acer' style='width:100%;height:280px;border:1px solid #22334a;border-radius:8px'></iframe></div>
  </div>
</div>
<!-- #223 TASK RULES board -->
<div class=section id=sec-rules-board style="scroll-margin-top:70px"><div class=section-title>📜 task rules · what every task must obey</div>
  <div style='padding:12px;background:#0e1420;border:2px solid #a78bfa;border-radius:12px'>
    <div id=rules-summary style='color:#94a3b8;font-size:12px;margin-bottom:8px'>loading rules...</div>
    <div id=rules-list style='display:grid;grid-template-columns:1fr;gap:6px;font-size:12.5px'></div>
  </div>
</div>

<!-- #263 NOTICE BOARD -->
<div class=section id=sec-notice style="scroll-margin-top:70px"><div class=section-title>📌 notice board · pinned thoughts + messages</div>
  <div style='padding:12px;background:#0e1420;border:2px solid #f59e0b;border-radius:12px'>
    <div style='display:flex;gap:8px;margin-bottom:10px;flex-wrap:wrap'>
      <input id=notice-text style='flex:1;min-width:200px;background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:10px 12px;font-size:14px' placeholder='pin a thought · reminder · warning...' onkeypress='if(event.key==="Enter")pinNotice()' />
      <select id=notice-from style='background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:8px;padding:10px'>
        <option value=ross>⭐ Ross</option><option value=hq_claude>HQ-Claude</option><option value=wren>Wren</option>
        <option value=tp_pip>TP-Pip</option><option value=acer_cass>Acer-Cass</option><option value=max_rally>Max Rally</option>
      </select>
      <button class='btn' style='min-height:44px;background:#f59e0b;color:#000;font-weight:800' onclick='pinNotice()'>📌 PIN</button>
    </div>
    <div id=notice-list style='max-height:340px;overflow-y:auto;font-size:13px'></div>
  </div>
</div>

<!-- #237 EVOLUTION rates -->
<div class=section id=sec-evolution style="scroll-margin-top:70px"><div class=section-title>🧬 CEO evolution rates · tasks/hr + last activity</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div id=evolution-summary style='color:#94a3b8;font-size:12px;margin-bottom:8px'>loading...</div>
    <div id=evolution-cards style='display:grid;grid-template-columns:repeat(4,1fr);gap:10px'></div>
  </div>
</div>

<!-- #221 HEALER panel -->
<div class=section id=sec-healer style="scroll-margin-top:70px"><div class=section-title>🩺 healer · auto-check + auto-fix</div>
  <div style='padding:12px;background:#0e1420;border:2px solid #10b981;border-radius:12px'>
    <div id=healer-summary style='color:#94a3b8;font-size:12px;margin-bottom:8px'>loading healer state...</div>
    <div id=healer-services style='display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:8px'></div>
    <div style='color:#64748b;font-size:11px;margin:6px 0'>recent heals:</div>
    <div id=healer-recent style='font-size:11.5px;font-family:ui-monospace,monospace;max-height:180px;overflow-y:auto'></div>
  </div>
</div>

<!-- #214 TRADER SCOREBOARD + weekly prize -->
<div class=section id=sec-scoreboard style="scroll-margin-top:70px"><div class=section-title>🏆 trader scoreboard · weekly prize</div>
  <div style='padding:12px;background:#0e1420;border:2px solid #eab308;border-radius:12px'>
    <div id=scoreboard-summary style='color:#94a3b8;font-size:12px;margin-bottom:8px'>loading...</div>
    <div id=scoreboard-list style='max-height:420px;overflow-y:auto;font-size:12.5px'></div>
  </div>
</div>

<!-- #244 TOUR preview -->
<div class=section id=sec-tour style="scroll-margin-top:70px"><div class=section-title>🏛️ public tour · live preview</div>
  <div style='padding:12px;background:#0e1420;border:2px solid #facc15;border-radius:12px'>
    <div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px'>
      <a class='btn' style='flex:1;min-height:44px;background:#facc15;color:#000;font-weight:900;text-decoration:none;text-align:center;padding:12px' href='/tour' target=_blank>🌐 open full tour</a>
      <button class='btn' style='flex:1;min-height:44px;background:#0b1220' onclick='navigator.clipboard.writeText(location.origin+"/tour").then(()=>alert("tour link copied"))'>📋 copy share link</button>
    </div>
    <iframe src='/tour' style='width:100%;height:600px;border:1px solid #22334a;border-radius:10px;background:#000'></iframe>
  </div>
</div>

<!-- #224 TRADER STATS — big animated numbers -->
<div class=section id=sec-trader-stats style="scroll-margin-top:70px"><div class=section-title>📊 trader live stats · animated</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:10px'>
      <div class=tile style='text-align:center;background:#0b1220;padding:10px'>
        <div style='color:#94a3b8;font-size:10px;text-transform:uppercase'>Fleet PnL</div>
        <div id=t-fleet-pnl style='color:#10b981;font-size:22px;font-weight:900;transition:all 0.5s'>—</div>
        <div id=t-fleet-pnl-sub style='color:#64748b;font-size:10px'>—</div>
      </div>
      <div class=tile style='text-align:center;background:#0b1220;padding:10px'>
        <div style='color:#94a3b8;font-size:10px;text-transform:uppercase'>Winners</div>
        <div id=t-winners style='color:#facc15;font-size:22px;font-weight:900;transition:all 0.5s'>—</div>
        <div id=t-winners-sub style='color:#64748b;font-size:10px'>of total</div>
      </div>
      <div class=tile style='text-align:center;background:#0b1220;padding:10px'>
        <div style='color:#94a3b8;font-size:10px;text-transform:uppercase'>Losers</div>
        <div id=t-losers style='color:#ef4444;font-size:22px;font-weight:900;transition:all 0.5s'>—</div>
        <div id=t-losers-sub style='color:#64748b;font-size:10px'>of total</div>
      </div>
      <div class=tile style='text-align:center;background:#0b1220;padding:10px'>
        <div style='color:#94a3b8;font-size:10px;text-transform:uppercase'>Week ends</div>
        <div id=t-countdown style='color:#22d3ee;font-size:18px;font-weight:900;font-family:ui-monospace,monospace'>—</div>
        <div style='color:#64748b;font-size:10px'>till reset</div>
      </div>
    </div>
    <div style='color:#94a3b8;font-size:11px;margin-bottom:6px'>PnL bars (top-8):</div>
    <div id=t-bars style='display:grid;grid-template-columns:1fr;gap:4px'></div>
    <div style='margin-top:10px'>
      <div style='color:#94a3b8;font-size:11px;margin-bottom:4px'>equity sparklines (top-4 winners):</div>
      <div id=t-sparks style='display:grid;grid-template-columns:repeat(4,1fr);gap:8px'></div>
    </div>
  </div>
</div>
<style>
@keyframes t-flash-green{0%{background:#10b98155}100%{background:transparent}}
@keyframes t-flash-red{0%{background:#ef444455}100%{background:transparent}}
@keyframes t-bar-grow{0%{width:0%}100%{}}
.t-bar-anim{animation:t-bar-grow 0.6s ease-out}
</style>

<!-- #214 SKYSCRAPER 170-floor grid -->
<div class=section id=sec-skyscraper style="scroll-margin-top:70px"><div class=section-title>🏢 the skyscraper · 170 floors live</div>
  <div style='padding:10px;background:#000;border:1px solid #22334a;border-radius:12px'>
    <div id=skyscraper-summary style='color:#94a3b8;font-size:11.5px;margin-bottom:8px'>loading floors...</div>
    <div id=skyscraper-grid style='display:grid;grid-template-columns:repeat(10, 1fr);gap:2px;font-size:9px;font-family:ui-monospace,monospace'></div>
  </div>
</div>

<!-- #214 INTERNAL BANK -->
<div class=section id=sec-bank style="scroll-margin-top:70px"><div class=section-title>🏦 internal bank · treasury · QBC</div>
  <div style='padding:12px;background:#0e1420;border:1px solid #22334a;border-radius:12px'>
    <div id=bank-panel style='font-size:12.5px'>loading bank state...</div>
  </div>
</div>

<!-- #214 ANIMATED TRADER MOTION -->
<div class=section id=sec-trader-motion style="scroll-margin-top:70px"><div class=section-title>🎬 traders moving · live animation</div>
  <div style='padding:10px;background:#000;border:1px solid #22d3ee;border-radius:12px;position:relative;overflow:hidden;height:180px'>
    <svg id=trader-svg viewBox='0 0 400 160' preserveAspectRatio='xMidYMid meet' style='width:100%;height:100%'>
      <defs>
        <linearGradient id=lane-grad x1=0 y1=0 x2=1 y2=0>
          <stop offset=0 stop-color=#0b1220 stop-opacity=0/><stop offset=0.5 stop-color=#22d3ee stop-opacity=0.4/><stop offset=1 stop-color=#0b1220 stop-opacity=0/>
        </linearGradient>
      </defs>
      <line x1=0 y1=40 x2=400 y2=40 stroke=url(#lane-grad) stroke-width=2/>
      <line x1=0 y1=80 x2=400 y2=80 stroke=url(#lane-grad) stroke-width=2/>
      <line x1=0 y1=120 x2=400 y2=120 stroke=url(#lane-grad) stroke-width=2/>
      <text x=8 y=15 fill=#eab308 font-size=10 font-weight=800>🏛 HQ Skyscraper</text>
      <text x=8 y=55 fill=#a78bfa font-size=10 font-weight=800>🎨 Wren Bench</text>
      <text x=8 y=95 fill=#22d3ee font-size=10 font-weight=800>☁ Oracle Cloud</text>
      <g id=trader-dots></g>
    </svg>
  </div>
</div>

<!-- #211 Ross ↔ Claude CLI mirror -->
<div class=section id=sec-clicli style="scroll-margin-top:70px"><div class=section-title>🖥️ Ross ↔ Claude CLI · live mirror</div>
  <div style='padding:12px;background:#000;border:1px solid #eab308;border-radius:12px'>
    <div style='color:#94a3b8;font-size:11px;margin-bottom:8px'>Every message we exchange in the terminal streams here · auto-refresh 4s</div>
    <div id=clicli-stream style='max-height:420px;overflow-y:auto;font-family:ui-monospace,Menlo,Consolas,monospace;font-size:12.5px;line-height:1.5'>loading transcript...</div>
  </div>
</div>
<div class=section id=sec-commentary style="scroll-margin-top:70px"><div class=section-title>💬 last activity</div>
  <!-- #208 LIVE VOICE COMMENTARY controls -->
  <div style='padding:10px 12px;background:#0e1420;border:1px solid #22334a;border-radius:10px;margin-bottom:8px;display:flex;gap:8px;align-items:center;flex-wrap:wrap'>
    <button class='btn' id=lvc-toggle style='min-height:44px;background:#0b1220;color:#e8ecf3;font-weight:800;padding:8px 14px' onclick='toggleLiveVoice()'>📢 <span id=lvc-state>LIVE VOICE: OFF</span></button>
    <label style='color:#94a3b8;font-size:12px'>rate <input id=lvc-rate type=range min=0.7 max=1.6 step=0.05 value=1.05 style='vertical-align:middle;width:100px' /> <span id=lvc-rate-val>1.05</span></label>
    <label style='color:#94a3b8;font-size:12px'><input id=lvc-heartbeat type=checkbox /> incl. heartbeats</label>
    <span id=lvc-status style='color:#64748b;font-size:11px;margin-left:auto'>tap 📢 to enable</span>
  </div>
  <div id=commentary></div>
</div>

<!-- iPad-13 (Ross 2026-07-06): live button-tap diag panel — sees EXACTLY what you tap + result -->
<div class=section id=sec-btn-diag style="scroll-margin-top:70px"><div class=section-title>🔬 button diag · live last 10 taps</div>
  <div style='color:#94a3b8;font-size:11px;margin-bottom:6px'>every button click on iPad logs to server. GREEN=200 · RED=fail · YELLOW=other. If you tap a button and it looks broken, check here.</div>
  <div id=btn-diag-list></div>
</div>

<script>
// iPad-13 (Ross 2026-07-06): global fetch wrapper — every button click logged.
window.__origFetch = window.fetch.bind(window);
window.fetch = async function(input, init){
  const url = (typeof input === 'string') ? input : (input && input.url) || '?';
  const t0 = Date.now();
  try {
    const r = await window.__origFetch(input, init);
    if (!url.includes('/ipad_button_diag') && !url.match(/\/(town_square_feed|hq\/stats|tasks\/data|brain\/usage|annexes|diagnostics|link_health|trader_scoreboard|talk\/data)/)){
      try {
        window.__origFetch('/ipad_button_diag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
          button_id: (window.__lastBtnId || 'auto'),
          url: url.slice(0,200),
          status: r.status,
          duration_ms: Date.now() - t0,
        })});
      } catch(e) {}
    }
    return r;
  } catch(e){
    try {
      window.__origFetch('/ipad_button_diag',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({
        button_id: (window.__lastBtnId || 'auto'),
        url: url.slice(0,200), status: null, duration_ms: Date.now() - t0, error: String(e).slice(0,200),
      })});
    } catch(_){}
    throw e;
  }
};
document.addEventListener('click', (e) => {
  const el = e.target.closest('button,a,[onclick]');
  if (!el) return;
  const id = el.id || (el.getAttribute('href') || '') || el.textContent.trim().slice(0,40) || 'unknown';
  window.__lastBtnId = id;
  setTimeout(()=>{ window.__lastBtnId = null; }, 2000);
}, true);

async function btnDiagTick(){
  try{
    const d = await window.__origFetch('/ipad_button_diag/tail', {cache:'no-store'}).then(r=>r.json());
    const el = document.getElementById('btn-diag-list');
    if (!el) return;
    const rows = (d.rows||[]).slice(-10).reverse();
    if (!rows.length){ el.innerHTML = '<div style="color:#64748b">no taps yet — tap something</div>'; return; }
    el.innerHTML = rows.map(r => {
      const c = (r.status===200) ? '#10b981' : (r.status && r.status>=400) ? '#ef4444' : (r.error) ? '#ef4444' : '#eab308';
      const st = r.status ?? (r.error ? 'ERR' : '?');
      return `<div style='padding:5px 8px;margin:3px 0;background:${c}15;border-left:2px solid ${c};border-radius:4px;font-family:ui-monospace,monospace;font-size:11px'>
        <b style='color:${c}'>${st}</b> · ${(r.ts||'').slice(11,19)} · ${r.duration_ms||'?'}ms · <span style='color:#e8ecf3'>${(r.button_id||'?').slice(0,40)}</span> → <span style='color:#94a3b8'>${(r.url||'').slice(0,60)}</span>${r.error?'<div style=color:#ef4444;font-size:10px>'+r.error.slice(0,120)+'</div>':''}
      </div>`;
    }).join('');
  }catch(e){}
}
setInterval(btnDiagTick, 3000);
setTimeout(btnDiagTick, 800);

async function tick(){
  try{
    const [tk, br, an, ts] = await Promise.all([
      fetch('/tasks/data',{cache:'no-store'}).then(r=>r.json()),
      fetch('/brain/usage',{cache:'no-store'}).then(r=>r.json()),
      fetch('/annexes',{cache:'no-store'}).then(r=>r.json()),
      fetch('/talk/data',{cache:'no-store'}).then(r=>r.json()),
    ]);
    // Tiles
    document.getElementById('t-total').textContent = tk.total || 0;
    document.getElementById('t-sub').textContent = `${tk.done||0}✓ ${tk.in_progress||0}🔥 ${tk.open||0}open`;
    document.getElementById('fleet-pnl').textContent = `$${(an.total_equity||0).toFixed(0)}`;
    document.getElementById('fleet-sub').textContent = `${an.total_traders||0} traders across ${(an.annexes||[]).filter(x=>x.online).length} annexes`;
    const totHr = Object.values(br.providers||{}).reduce((a,s)=>a+(s.last_1h||0),0);
    document.getElementById('brain-hr').textContent = totHr;
    document.getElementById('brain-sub').textContent = `${Object.entries(br.providers||{}).filter(([_,s])=>s.last_5m>0).length} live now`;
    // CEO list
    const CEO_META = {
      hq_claude:{n:'HQ-Claude',c:'#eab308',i:'H'},
      wren:{n:'Wren',c:'#a78bfa',i:'W'},
      tp_pip:{n:'TP-Pip',c:'#22d3ee',i:'T'},
      acer_cass:{n:'Acer-Cass',c:'#f59e0b',i:'A'},
      ross:{n:'⭐ ROSS',c:'#facc15',i:'R'},
    };
    const lastPost = {};
    (ts.messages||[]).forEach(m => {
      const w = m.who === 'hq' ? 'hq_claude' : m.who === 'tp' ? 'tp_pip' : m.who === 'acer' ? 'acer_cass' : m.who;
      if(!lastPost[w] || (m.ts||'') > lastPost[w].ts) lastPost[w] = m;
    });
    const nowMs = Date.now();
    let liveCount = 0;
    document.getElementById('ceo-list').innerHTML = Object.entries(CEO_META).map(([id,m])=>{
      const p = lastPost[id];
      const ageS = p ? (nowMs - new Date(p.ts||'').getTime())/1000 : 99999;
      const alive = ageS < 180;
      if(alive) liveCount++;
      return `<div class='ceo-row'><div class='ceo-avatar' style='background:${m.c}'>${m.i}</div>
        <div style='flex:1'><b style='color:${m.c}'>${m.n}</b>
          <div style='color:#64748b;font-size:11px'>${alive?ageS.toFixed(0)+'s ago':'silent'}</div>
        </div>
        <span class='chip ${alive?"live":"off"}'>${alive?'LIVE':'OFF'}</span>
      </div>`;
    }).join('');
    document.getElementById('ceos-live').textContent = liveCount;
    // #206 Commentary — Ross pinned at top, skip self-heal / heartbeat noise
    const allMsgs = ts.messages || [];
    const noise = /self-heal|heartbeat|nudged|reboot_step|auto_fix|watching from iPad|present · watching/i;
    const rossMsgs = allMsgs.filter(m => m.who === 'ross' && !noise.test(m.text||'')).slice(0, 5);
    const otherMsgs = allMsgs.filter(m => m.who !== 'ross' && !noise.test(m.text||'')).slice(0, 5);
    const ordered = [...rossMsgs, ...otherMsgs];
    document.getElementById('commentary').innerHTML = ordered.map(m => {
      const cfg = CEO_META[m.who === 'hq' ? 'hq_claude' : m.who === 'tp' ? 'tp_pip' : m.who === 'acer' ? 'acer_cass' : m.who] || {n:m.who,c:'#94a3b8'};
      const bg = m.who === 'ross' ? 'rgba(250,204,21,0.18)' : '#0b1220';
      const brd = m.who === 'ross' ? '2px solid #facc15' : '1px solid #22334a';
      return `<div class='commentary-item' style='background:${bg};border:${brd}'>
        <span class='who' style='color:${cfg.c}'>${cfg.n}</span>: ${(m.text||'').replace(/</g,'&lt;').slice(0,140)}
      </div>`;
    }).join('') || '<div style=color:#64748b>no messages</div>';
  }catch(e){console.error(e)}
}
tick(); setInterval(tick, 1500);
// clock
setInterval(()=>{const el=document.getElementById('live-clock');if(el)el.textContent=new Date().toLocaleTimeString('en-GB',{hour12:false})},1000);
// #182 Ross POST to town-square
async function rossPost(){
  const t=document.getElementById('ross-msg').value.trim(); if(!t)return;
  try{
    await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:t,to:'council',src:'ross_ipad'})});
    document.getElementById('ross-msg').value='';
    tick();
  }catch(e){alert('post failed: '+e)}
}
async function kickWren(){await fetch('/ceo_mind/wren',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:'Wren, Ross wants you working hard.'})});alert('✓ Wren kicked')}
async function dispatchTeam(){await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'⚡ Team — Ross dispatching. All CEOs sweep open tasks NOW.',to:'council',src:'ross_dispatch'})});alert('✓ team dispatched')}
async function pingTP(){try{const r=await fetch('/ceo_mind/tp_pip',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:'TP status ping. Reply in 1 line.'})});const d=await r.json();alert('TP: '+(d.reply||'no reply').slice(0,120))}catch(e){alert('TP unreachable')}}
async function pingAcer(){try{const r=await fetch('/ceo_mind/acer_cass',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:'Acer status ping. Reply in 1 line.'})});const d=await r.json();alert('Acer: '+(d.reply||'no reply').slice(0,120))}catch(e){alert('Acer unreachable')}}
async function emergencyPause(){if(confirm('PAUSE all CEO auto-claims?')){await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'🛑 EMERGENCY PAUSE from iPad',to:'council',src:'ross_pause'})});alert('✓ pause posted')}}
// Brain panel + annex panel + sparklines
const BRAIN_HISTORY = {};
async function panelsTick(){
  try{
    const [br, an] = await Promise.all([
      fetch('/brain/usage',{cache:'no-store'}).then(r=>r.json()),
      fetch('/annexes',{cache:'no-store'}).then(r=>r.json()),
    ]);
    const providers = br.providers || {};
    const PCOL = {groq:'#f97316',gemini:'#3b82f6',cohere:'#ec4899',deepseek:'#8b5cf6',openai:'#10b981',kimi:'#f43f5e',claude:'#eab308',ollama_lan:'#64748b',ollama_local:'#94a3b8'};
    ['groq','gemini','cohere','deepseek','openai','kimi','claude','ollama_lan','ollama_local'].forEach(p=>{
      if(!BRAIN_HISTORY[p]) BRAIN_HISTORY[p]=[];
      BRAIN_HISTORY[p].push((providers[p]||{}).last_5m || 0);
      if(BRAIN_HISTORY[p].length>30) BRAIN_HISTORY[p].shift();
    });
    document.getElementById('brain-panel').innerHTML = ['claude','groq','cohere','deepseek','openai','kimi','gemini','ollama_lan','ollama_local'].map(p=>{
      const s = providers[p]||{total:0,last_5m:0};
      const c = PCOL[p];
      const active = (s.last_5m||0)>0;
      const h = BRAIN_HISTORY[p];
      const mx = Math.max(1, ...h);
      const pts = h.map((v,i)=>`${(i/(h.length-1||1))*100},${28-(v/mx)*24}`).join(' ');
      return `<div class=tile>
        <div style='display:flex;align-items:center;gap:6px'><span style='width:8px;height:8px;border-radius:50%;background:${c};display:inline-block${active?';animation:phone-pulse 1.5s infinite':''}'></span><b style='color:${c};font-size:11px'>${p}</b></div>
        <svg class=sparkline viewBox='0 0 100 32' preserveAspectRatio='none'><polyline points='${pts}' stroke='${c}' stroke-width='1' fill='none'/></svg>
        <div style='font-size:10.5px;color:#94a3b8'><b style='color:#e8ecf3'>${s.last_5m||0}</b>/5m · ${s.total||0} tot</div>
      </div>`;
    }).join('');
    document.getElementById('annex-panel').innerHTML = (an.annexes||[]).map(a=>{
      const c = a.online?'#10b981':'#ef4444';
      return `<div class=tile><div style='display:flex;align-items:center;gap:6px'><span style='width:10px;height:10px;border-radius:50%;background:${c};display:inline-block${a.online?';animation:phone-pulse 1.5s infinite':''}'></span><b style='color:${c}'>${a.name.split(' ')[0]}</b></div>
        <div style='color:#22d3ee;font-size:24px;font-weight:700'>${a.trader_count}</div>
        <div style='color:#94a3b8;font-size:10.5px'>$${a.equity_sum||0} equity</div>
      </div>`;
    }).join('');
  }catch(e){}
}
panelsTick(); setInterval(panelsTick, 3000);
async function assignRandom(ceo){
  try{
    const d = await(await fetch('/tasks/data',{cache:'no-store'})).json();
    const open = (d.tasks||[]).filter(t=>t.state==='open'&&!t.owner)[0];
    if(!open){alert('no open tasks');return}
    await fetch('/tasks/assign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:open.id,actor:'ross',assignee:ceo})});
    alert('✓ assigned '+ceo+' → '+(open.title||'').slice(0,50));
  }catch(e){alert('err '+e)}
}
async function forceRefreshAll(){await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'🔄 Force refresh all dashboards',to:'council',src:'ross_refresh'})});alert('✓ refresh posted')}
async function massSignoff(){await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'✅ Mass-signoff pending awaiting_peer_signoff',to:'council',src:'ross_signoff'})});alert('✓ signoff dispatched')}
async function cullDuds(){if(confirm('CULL TIER_0 losing traders?')){await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'🗑️ CULL TIER_0 duds now',to:'council',src:'ross_cull'})});alert('✓ cull ordered')}}
async function runQualifier(){await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'📈 Re-run trader qualifier grader',to:'council',src:'ross_grade'})});alert('✓ grader triggered')}
// #187 CHAT
let CHAT_TARGET = 'hq_claude';
const CHAT_LABELS = {hq_claude:'HQ-Claude',wren:'Wren',tp_pip:'TP-Pip',acer_cass:'Acer-Cass',ALL:'All CEOs'};
function setChatTarget(id, lbl){
  CHAT_TARGET = id;
  document.getElementById('chat-target').innerHTML = 'target: <b style="color:#eab308">'+CHAT_LABELS[id]+'</b>';
}
let __CHAT_SENDING = false;
async function sendChat(){
  __CHAT_SENDING = true;
  try { return await _sendChatInner(); }
  finally { setTimeout(()=>{ __CHAT_SENDING = false; }, 2000); }
}
async function _sendChatInner(){
  const t = document.getElementById('chat-msg').value.trim();
  if(!t) return;
  beep(700,60);
  document.getElementById('chat-msg').value = '';
  const log = document.getElementById('chat-log');
  saveChat('Ross','#eab308','→ '+CHAT_LABELS[CHAT_TARGET]+': '+t);
  log.insertAdjacentHTML('afterbegin', `<div style='padding:6px 10px;margin:4px 0;background:rgba(234,179,8,0.15);border-left:2px solid #eab308;border-radius:6px'><b style='color:#eab308'>Ross</b> → ${CHAT_LABELS[CHAT_TARGET]}: ${t.replace(/</g,'&lt;')}</div>`);
  // Post to town-square
  await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:t,to:CHAT_TARGET==='ALL'?'council':CHAT_TARGET,src:'ross_chat'})});
  // Route to CEO(s)
  const targets = CHAT_TARGET === 'ALL' ? ['hq_claude','wren','tp_pip','acer_cass'] : [CHAT_TARGET];
  for(const ceo of targets){
    const cfg = {hq_claude:'#eab308',wren:'#a78bfa',tp_pip:'#22d3ee',acer_cass:'#f59e0b'}[ceo];
    // iPad-09 (2026-07-06): pending chip so user sees the in-flight call
    const pendId = 'pend_'+ceo+'_'+Date.now();
    log.insertAdjacentHTML('afterbegin', `<div id='${pendId}' style='padding:6px 10px;margin:4px 0;background:${cfg}11;border-left:2px dashed ${cfg};border-radius:6px'><b style='color:${cfg}'>${CHAT_LABELS[ceo]}</b> <span style='color:#94a3b8;font-size:10px'>⏳ thinking…</span></div>`);
    try{
      // iPad-09: explicit 60s AbortController — ceo_mind for TP/Acer often >20s
      const ctrl = new AbortController();
      const to = setTimeout(()=>ctrl.abort(), 60000);
      // ARCH #311: hit CEO's REAL mind endpoint. If offline, they abstain honestly — no impersonation.
      const r = await fetch('/ceo_mind/'+ceo,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:`Ross says: "${t}". Reply as YOURSELF in 1-2 sentences warmly.`}),signal:ctrl.signal});
      clearTimeout(to);
      const d = await r.json();
      const pe = document.getElementById(pendId); if (pe) pe.remove();
      if (d.reply) {
        log.insertAdjacentHTML('afterbegin', `<div style='padding:6px 10px;margin:4px 0;background:${cfg}22;border-left:2px solid ${cfg};border-radius:6px'><b style='color:${cfg}'>${CHAT_LABELS[ceo]}</b> <span style='color:#94a3b8;font-size:10px'>(REAL · ${d.mind||'?'})</span>: ${(d.reply||'').replace(/</g,'&lt;')}</div>`);
        await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:ceo,text:d.reply||'',to:'ross',src:'ceo_chat_reply'})});
      } else {
        log.insertAdjacentHTML('afterbegin', `<div style='padding:6px 10px;margin:4px 0;background:${cfg}0f;border-left:2px dashed ${cfg};border-radius:6px'><b style='color:${cfg}'>${CHAT_LABELS[ceo]}</b> <span style='color:#94a3b8;font-size:10px'>⚪ OFFLINE / ABSTAINS</span>: <span style='color:#64748b'>${(d.error||d.note||'unreachable').slice(0,120)}</span></div>`);
      }
    }catch(e){
      const pe = document.getElementById(pendId); if (pe) pe.remove();
      const errMsg = (e && e.name === 'AbortError') ? 'timed out after 60s' : String(e);
      log.insertAdjacentHTML('afterbegin', `<div style='color:${cfg};padding:4px 10px'>${CHAT_LABELS[ceo]}: ${errMsg}</div>`);
    }
  }
}
// #191 inline task create
async function createTask(){
  const title = document.getElementById('new-task-title').value.trim();
  if(!title){alert('need title');return}
  const desc = document.getElementById('new-task-desc').value;
  const assign = document.getElementById('new-task-assign').value;
  const pri = document.getElementById('new-task-pri').value;
  const r = await fetch('/tasks/create',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({title,description:desc,actor:'ross',priority:pri})});
  const d = await r.json();
  if(d.ok && assign){
    await fetch('/tasks/assign',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id:d.task_id,actor:'ross',assignee:assign})});
  }
  document.getElementById('new-task-title').value='';
  document.getElementById('new-task-desc').value='';
  alert('✓ task created'+(assign?' + assigned to '+assign:''));
}
// #196 voice command center — upgraded
let CONT_LISTEN = false;
let AUTO_SPEAK = true;
let ACTIVE_REC = null;
let ACTIVE_CEO_ID = null;
let ACTIVE_CEO_NAME = null;
let WAVE_CTX = null;
let WAVE_ANALYSER = null;
let WAVE_STREAM = null;
let WAVE_RAF = null;
function toggleContinuous(){
  CONT_LISTEN = !CONT_LISTEN;
  document.getElementById('continuous-state').textContent = 'continuous: '+(CONT_LISTEN?'ON':'OFF');
}
function toggleAutoSpeak(){
  AUTO_SPEAK = !AUTO_SPEAK;
  document.getElementById('autospeak-state').textContent = 'auto-speak: '+(AUTO_SPEAK?'ON':'OFF');
}
function clearVoiceLog(){
  document.getElementById('voice-log').innerHTML = '';
  document.getElementById('voice-transcript').style.display = 'none';
  document.getElementById('voice-transcript').textContent = '';
}
function _pickVoice(ceo){
  const vs = speechSynthesis.getVoices();
  if(!vs.length) return null;
  const preferFemale = ceo==='wren' || ceo==='acer_cass';
  const preferMale = ceo==='hq_claude' || ceo==='tp_pip';
  const enVoices = vs.filter(v=>/^en/i.test(v.lang));
  const pool = enVoices.length ? enVoices : vs;
  if(preferFemale){
    const f = pool.find(v=>/female|zira|samantha|karen|serena|tessa|kate|fiona/i.test(v.name));
    if(f) return f;
  }
  if(preferMale){
    const m = pool.find(v=>/male|daniel|david|alex|fred|oliver|arthur/i.test(v.name));
    if(m) return m;
  }
  const idx = {hq_claude:0,wren:1,tp_pip:2,acer_cass:3}[ceo] ?? 0;
  return pool[idx % pool.length];
}
// Per-CEO + global parallel-teacher toggles 2026-07-06
async function ceoTeacherToggle(ceo){
  try{
    const r = await fetch('/wren/parallel_teacher/status?ceo='+ceo,{method:'POST'});
    const d = await r.json();
    const cur = (d.per_ceo && d.per_ceo[ceo]) === true;
    const nm = cur ? 'off' : 'on';
    await fetch('/wren/parallel_teacher/'+nm+'?ceo='+ceo,{method:'POST'});
    await refreshTeacherStatus();
  }catch(e){ console.error('ceo teacher toggle failed', e); }
}
async function wrenParallelTeacher(mode){
  try{
    await fetch('/wren/parallel_teacher/'+mode,{method:'POST'});
    await refreshTeacherStatus();
  }catch(e){}
}
async function refreshTeacherStatus(){
  try{
    const r = await fetch('/wren/parallel_teacher/status',{method:'POST'});
    const d = await r.json();
    const master = d.enabled;
    ['wren','tp_pip','acer_cass'].forEach(c=>{
      const st = document.getElementById('teacher-'+c+'-st');
      if(st){
        const on = master && d.per_ceo && d.per_ceo[c];
        st.textContent = on ? '● ON' : '○ OFF';
        st.style.color = on ? '#0b3a1a' : '#4b1a1a';
      }
    });
  }catch(e){}
}
setInterval(refreshTeacherStatus, 5000);
setTimeout(refreshTeacherStatus, 500);
function speak(text, ceo){
  if(!AUTO_SPEAK) return;
  try{
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05;
    u.pitch = ceo==='wren'?1.25:ceo==='hq_claude'?0.9:ceo==='tp_pip'?1.05:ceo==='acer_cass'?1.15:1.0;
    const v = _pickVoice(ceo);
    if(v) u.voice = v;
    u.lang = 'en-GB';
    speechSynthesis.speak(u);
  }catch(e){}
}
function _drawWave(){
  const c = document.getElementById('voice-waveform');
  if(!c || !WAVE_ANALYSER) return;
  const g = c.getContext('2d');
  const buf = new Uint8Array(WAVE_ANALYSER.frequencyBinCount);
  WAVE_ANALYSER.getByteTimeDomainData(buf);
  const W = c.width = c.clientWidth * (window.devicePixelRatio||1);
  const H = c.height = 60 * (window.devicePixelRatio||1);
  g.fillStyle = '#000'; g.fillRect(0,0,W,H);
  g.lineWidth = 2; g.strokeStyle = '#ef4444';
  g.beginPath();
  const slice = W / buf.length;
  let x = 0;
  for(let i=0;i<buf.length;i++){
    const v = buf[i]/128.0; const y = v * H/2;
    if(i===0) g.moveTo(x,y); else g.lineTo(x,y);
    x += slice;
  }
  g.stroke();
  WAVE_RAF = requestAnimationFrame(_drawWave);
}
async function _startWave(){
  try{
    WAVE_CTX = WAVE_CTX || new (window.AudioContext||window.webkitAudioContext)();
    WAVE_STREAM = await navigator.mediaDevices.getUserMedia({audio:true});
    const src = WAVE_CTX.createMediaStreamSource(WAVE_STREAM);
    WAVE_ANALYSER = WAVE_CTX.createAnalyser();
    WAVE_ANALYSER.fftSize = 512;
    src.connect(WAVE_ANALYSER);
    document.getElementById('voice-waveform').style.display = 'block';
    _drawWave();
  }catch(e){/* mic permission denied — waveform silent */}
}
function _stopWave(){
  try{if(WAVE_RAF) cancelAnimationFrame(WAVE_RAF);}catch(e){}
  try{if(WAVE_STREAM){WAVE_STREAM.getTracks().forEach(t=>t.stop()); WAVE_STREAM=null;}}catch(e){}
  document.getElementById('voice-waveform').style.display = 'none';
}
function _btnListenState(ceoId, on){
  document.querySelectorAll('.voice-btn').forEach(b=>b.classList.remove('listening'));
  if(on){
    const b = document.querySelector('.voice-btn[data-ceo="'+ceoId+'"]');
    if(b) b.classList.add('listening');
  }
}
function stopListening(){
  try{if(ACTIVE_REC){ACTIVE_REC.stop(); ACTIVE_REC=null;}}catch(e){}
  CONT_LISTEN = false;
  document.getElementById('continuous-state').textContent = 'continuous: OFF';
  document.getElementById('voice-stop-btn').style.display = 'none';
  document.getElementById('voice-status').textContent = '⏹ stopped';
  _btnListenState(null, false);
  _stopWave();
}
async function voicePreset(text){
  const target = ACTIVE_CEO_ID || 'hq_claude';
  const name = {hq_claude:'HQ-Claude',wren:'Wren',tp_pip:'TP-Pip',acer_cass:'Acer-Cass',ALL:'All 4 CEOs'}[target] || target;
  await _dispatchVoiceText(text, target, name);
}
async function _dispatchVoiceText(text, ceoId, name){
  const log = document.getElementById('voice-log');
  const status = document.getElementById('voice-status');
  const tx = document.getElementById('voice-transcript');
  tx.style.display = 'block'; tx.textContent = '"' + text + '"';
  status.textContent = '📤 dispatching to '+name+'...';
  log.insertAdjacentHTML('afterbegin', `<div style='padding:6px 10px;margin:4px 0;background:rgba(234,179,8,0.15);border-left:2px solid #eab308;border-radius:6px'><b>Ross → ${name}</b>: ${text.replace(/</g,'&lt;')}</div>`);
  try{
    await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'🎤 (voice) '+text,to:ceoId==='ALL'?'council':ceoId,src:'voice_ipad'})});
  }catch(e){}
  const targets = ceoId==='ALL'?['hq_claude','wren','tp_pip','acer_cass']:[ceoId];
  for(const c of targets){
    try{
      const r = await fetch('/ceo_mind/'+c,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:`Ross said: "${text}". Reply briefly (under 200 chars).`})});
      const d = await r.json();
      const col = {hq_claude:'#eab308',wren:'#a78bfa',tp_pip:'#22d3ee',acer_cass:'#f59e0b'}[c] || '#e8ecf3';
      const nm = {hq_claude:'HQ-Claude',wren:'Wren',tp_pip:'TP-Pip',acer_cass:'Acer-Cass'}[c] || c;
      const reply = (d.reply||'').trim();
      log.insertAdjacentHTML('afterbegin', `<div style='padding:6px 10px;margin:4px 0;background:${col}22;border-left:2px solid ${col};border-radius:6px'><b style='color:${col}'>${nm}</b> <span style='color:#64748b;font-size:10px'>via ${d.provider||'?'}</span>: ${reply.replace(/</g,'&lt;')}</div>`);
      speak(reply, c);
      try{await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:c,text:reply,to:'ross',src:'ceo_voice_reply'})});}catch(e){}
    }catch(e){
      log.insertAdjacentHTML('afterbegin', `<div style='padding:6px 10px;margin:4px 0;background:#3f1c1c;border-left:2px solid #ef4444;border-radius:6px'>${c} error: ${e}</div>`);
    }
  }
  status.textContent = '✅ dispatched · listening pool ready';
}
function voiceChat(ceoId, name){
  ACTIVE_CEO_ID = ceoId; ACTIVE_CEO_NAME = name;
  const status = document.getElementById('voice-status');
  if(!('webkitSpeechRecognition' in window || 'SpeechRecognition' in window)){
    status.textContent = '⚠ browser has no speech recognition (need Safari or Chrome on iPad)';
    return;
  }
  const Rec = window.SpeechRecognition || window.webkitSpeechRecognition;
  const rec = new Rec();
  ACTIVE_REC = rec;
  rec.lang = 'en-GB'; rec.interimResults = true; rec.maxAlternatives = 1; rec.continuous = false;
  status.textContent = '🔴 listening for ' + name + '... speak now';
  document.getElementById('voice-stop-btn').style.display = 'block';
  _btnListenState(ceoId, true);
  const tx = document.getElementById('voice-transcript');
  tx.style.display = 'block'; tx.textContent = '···';
  _startWave();
  rec.onresult = async (e) => {
    let interim = '', final = '';
    for(let i=e.resultIndex;i<e.results.length;i++){
      const r = e.results[i];
      if(r.isFinal) final += r[0].transcript; else interim += r[0].transcript;
    }
    if(interim) tx.textContent = '"' + interim + '"';
    if(final){
      tx.textContent = '"' + final + '"';
      await _dispatchVoiceText(final.trim(), ceoId, name);
      if(CONT_LISTEN) setTimeout(()=>voiceChat(ceoId, name), 900);
    }
  };
  rec.onerror = (e) => {
    status.textContent = '⚠ mic error: ' + e.error + (e.error==='not-allowed'?' — allow mic in Safari settings':'');
    _btnListenState(null, false);
    _stopWave();
    document.getElementById('voice-stop-btn').style.display = 'none';
  };
  rec.onend = () => {
    _btnListenState(null, false);
    _stopWave();
    document.getElementById('voice-stop-btn').style.display = 'none';
    ACTIVE_REC = null;
    if(!CONT_LISTEN) status.textContent = '✔ idle · tap a mic to speak again';
  };
  try{rec.start();}catch(e){status.textContent = 'start failed: '+e;}
}
// Preload TTS voices (needed on iOS)
try{ speechSynthesis.onvoiceschanged = ()=>speechSynthesis.getVoices(); speechSynthesis.getVoices(); }catch(e){}
// #196 CLI terminal — upgraded
let CLI_HISTORY = JSON.parse(localStorage.getItem('cli_history')||'[]');
let CLI_HIST_IDX = -1;
function cliClear(){ document.getElementById('cli-out').textContent = 'cleared.'; }
function cliHistoryUp(){
  if(!CLI_HISTORY.length) return;
  CLI_HIST_IDX = Math.min(CLI_HISTORY.length-1, CLI_HIST_IDX+1);
  document.getElementById('cli-cmd').value = CLI_HISTORY[CLI_HISTORY.length-1-CLI_HIST_IDX] || '';
}
function cliQuick(cmd){
  document.getElementById('cli-cmd').value = cmd;
  runCli();
}
async function runCli(){
  const inp = document.getElementById('cli-cmd');
  const cmd = inp.value.trim(); if(!cmd) return;
  const out = document.getElementById('cli-out');
  const ts = new Date().toLocaleTimeString();
  out.textContent += '\\n[' + ts + '] $ ' + cmd + '\\n';
  out.scrollTop = out.scrollHeight;
  CLI_HISTORY.push(cmd);
  if(CLI_HISTORY.length > 50) CLI_HISTORY = CLI_HISTORY.slice(-50);
  localStorage.setItem('cli_history', JSON.stringify(CLI_HISTORY));
  CLI_HIST_IDX = -1;
  inp.value = '';
  try{
    const t0 = performance.now();
    const r = await fetch('/cli',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({cmd})});
    const d = await r.json();
    const ms = Math.round(performance.now()-t0);
    const body = (d.stdout||'') + (d.stderr?('\\n[stderr] '+d.stderr):'');
    out.textContent += (body || '(no output)') + '\\n[' + ms + 'ms · rc=' + (d.rc??'?') + ']\\n';
    out.scrollTop = out.scrollHeight;
  }catch(e){out.textContent += '['+e+']\\n'; out.scrollTop = out.scrollHeight;}
}
// #193 SOUND — Web Audio beeps + notification chime
let SOUND_ON = true;
let AC;
function toggleSound(){ SOUND_ON = !SOUND_ON; document.getElementById('sound-state').textContent = 'sound: '+(SOUND_ON?'ON 🔊':'OFF 🔇'); }
function beep(freq, dur, vol){
  if(!SOUND_ON) return;
  try{
    if(!AC) AC = new (window.AudioContext||window.webkitAudioContext)();
    const o = AC.createOscillator(); const g = AC.createGain();
    o.frequency.value = freq; g.gain.value = vol || 0.1;
    o.connect(g); g.connect(AC.destination);
    o.start(); setTimeout(()=>{o.stop()}, dur||100);
  }catch(e){}
}
function chime(){ beep(880,120,0.15); setTimeout(()=>beep(660,120,0.12), 130); }
function alarm(){ for(let i=0;i<3;i++) setTimeout(()=>beep(220,200,0.2), i*250); }

// ============================================================
// #208 LIVE VOICE COMMENTARY — TTS narrator of town-square
// ============================================================
let LVC_ON = false;
let LVC_SEEN = new Set();
let LVC_QUEUE = [];
let LVC_SPEAKING = false;
let LVC_INCLUDE_HEARTBEAT = false;
let LVC_RATE = 1.05;
function toggleLiveVoice(){
  LVC_ON = !LVC_ON;
  const state = document.getElementById('lvc-state');
  const st = document.getElementById('lvc-status');
  if (state) state.textContent = 'LIVE VOICE: ' + (LVC_ON ? 'ON 🔊' : 'OFF');
  if (st) st.textContent = LVC_ON ? 'narrating live · every new post spoken' : 'tap 📢 to enable';
  if (LVC_ON) {
    // seed seen-set with current so we don't dump the whole history at once
    fetch('/talk/data', {cache:'no-store'}).then(r=>r.json()).then(d=>{
      (d.messages||[]).forEach(m => LVC_SEEN.add(m.ts + '|' + m.who));
      chime();
      _lvcSpeak('Live voice commentary on. I will read each new message.', 'hq_claude');
    }).catch(()=>{});
  } else {
    speechSynthesis.cancel();
    LVC_QUEUE = [];
    LVC_SPEAKING = false;
  }
}
function _lvcVoice(who){
  const vs = speechSynthesis.getVoices();
  if (!vs.length) return null;
  const en = vs.filter(v => /^en/i.test(v.lang));
  const pool = en.length ? en : vs;
  const female = /female|zira|samantha|karen|serena|tessa|kate|fiona|amy|zoe/i;
  const male = /male|daniel|david|alex|fred|oliver|arthur|george/i;
  if (who === 'wren' || who === 'acer') {
    const f = pool.find(v => female.test(v.name)); if (f) return f;
  }
  if (who === 'hq_claude' || who === 'tp_pip') {
    const m = pool.find(v => male.test(v.name)); if (m) return m;
  }
  const idx = {hq_claude:0, wren:1, tp_pip:2, acer_cass:3, ross:4}[who] ?? 0;
  return pool[idx % pool.length];
}
function _lvcSpeak(text, who){
  try {
    const u = new SpeechSynthesisUtterance(text.slice(0, 300));
    u.rate = LVC_RATE;
    u.pitch = who === 'wren' ? 1.25 : who === 'hq_claude' ? 0.9 :
              who === 'tp_pip' ? 1.05 : who === 'acer_cass' ? 1.15 :
              who === 'ross' ? 1.0 : 1.0;
    const v = _lvcVoice(who);
    if (v) u.voice = v;
    u.lang = 'en-GB';
    u.onend = () => { LVC_SPEAKING = false; _lvcPump(); };
    u.onerror = () => { LVC_SPEAKING = false; _lvcPump(); };
    LVC_SPEAKING = true;
    speechSynthesis.speak(u);
  } catch(e) { LVC_SPEAKING = false; }
}
function _lvcPump(){
  if (!LVC_ON || LVC_SPEAKING) return;
  const next = LVC_QUEUE.shift();
  if (!next) return;
  _lvcSpeak(next.text, next.who);
}
async function _lvcTick(){
  if (!LVC_ON) return;
  try {
    const d = await (await fetch('/talk/data', {cache:'no-store'})).json();
    const noise = /self-heal|nudged|reboot_step|auto_fix|watching from iPad|present · watching/i;
    const heartbeat = /heartbeat|main-loop tick|uptime=/i;
    const nameFor = {hq_claude:'HQ-Claude', wren:'Wren', tp_pip:'TP-Pip', acer_cass:'Acer-Cass', ross:'Ross', hq:'HQ-Claude', tp:'TP-Pip', acer:'Acer-Cass'};
    const raw = (d.messages || []).slice().reverse();  // oldest first
    for (const m of raw) {
      const key = (m.ts || '') + '|' + (m.who || '');
      if (LVC_SEEN.has(key)) continue;
      LVC_SEEN.add(key);
      if (LVC_SEEN.size > 500) { const arr = [...LVC_SEEN]; LVC_SEEN = new Set(arr.slice(-300)); }
      const text = (m.text || '').replace(/[<>_`*#🟨🟪🟦🟧⭐🎨🔧🚨✅🔴🟢👥📊💬🎤🖥️🏠]/g,'').trim();
      if (!text) continue;
      if (noise.test(text)) continue;
      if (!LVC_INCLUDE_HEARTBEAT && heartbeat.test(text)) continue;
      const shortWho = m.who || 'someone';
      const speakName = nameFor[shortWho] || shortWho;
      LVC_QUEUE.push({who: shortWho, text: speakName + ' says: ' + text.slice(0, 250)});
    }
    if (LVC_QUEUE.length > 8) LVC_QUEUE = LVC_QUEUE.slice(-8);
    _lvcPump();
    const st = document.getElementById('lvc-status');
    if (st) st.textContent = 'narrating · queue=' + LVC_QUEUE.length + ' · seen=' + LVC_SEEN.size;
  } catch(e) {}
}
setInterval(_lvcTick, 3000);
// keep rate slider in sync
document.addEventListener('DOMContentLoaded', () => {
  const r = document.getElementById('lvc-rate');
  const rv = document.getElementById('lvc-rate-val');
  if (r) r.addEventListener('input', () => { LVC_RATE = parseFloat(r.value)||1.05; if(rv) rv.textContent = r.value; });
  const hb = document.getElementById('lvc-heartbeat');
  if (hb) hb.addEventListener('change', () => { LVC_INCLUDE_HEARTBEAT = hb.checked; });
});
// #193/#206 chat history — server-poll so refresh doesn't lose the thread
async function loadChatHistory(){
  if (__CHAT_SENDING) return;  // #253: don't overwrite while sendChat is inserting reply
  const log = document.getElementById('chat-log'); if(!log) return;
  try{
    const d = await (await fetch('/talk/data',{cache:'no-store'})).json();
    const msgs = d.messages || [];
    const noise = /self-heal|heartbeat|nudged|reboot_step|auto_fix|watching from iPad|present · watching|main-loop tick/i;
    const colorFor = {ross:'#facc15', hq:'#eab308', wren:'#a78bfa', tp:'#22d3ee', acer:'#f59e0b'};
    const nameFor  = {ross:'⭐ Ross', hq:'HQ-Claude', wren:'Wren', tp:'TP-Pip', acer:'Acer-Cass'};
    const chat = msgs
      .filter(m => !noise.test(m.text||''))
      .filter(m => m.who === 'ross' || m.who === 'hq' || m.who === 'wren' || m.who === 'tp' || m.who === 'acer')
      .slice(0, 30)
      .reverse();
    log.innerHTML = chat.map(m => {
      const c = colorFor[m.who] || '#94a3b8';
      const n = nameFor[m.who] || m.who;
      return `<div style='padding:6px 10px;margin:4px 0;background:${c}22;border-left:2px solid ${c};border-radius:6px'><b style='color:${c}'>${n}</b>: ${(m.text||'').replace(/</g,'&lt;').slice(0,300)}</div>`;
    }).join('') || '<div style=color:#64748b;padding:8px>waiting for chat traffic...</div>';
    log.scrollTop = log.scrollHeight;
  }catch(e){
    log.innerHTML = '<div style=color:#ef4444>chat load error: '+e+'</div>';
  }
}
function saveChat(who,color,text){
  try{ const h = JSON.parse(localStorage.getItem('qsb_chat_history')||'[]');
    h.push({who,color,text,ts:Date.now()});
    if(h.length>50) h.shift();
    localStorage.setItem('qsb_chat_history',JSON.stringify(h));
  }catch(e){}
}
// #193 town-square new-post chime detector
let LAST_TS_TS = null;
async function tsChimeTick(){
  try{
    const d = await(await fetch('/talk/data',{cache:'no-store'})).json();
    const msgs = d.messages || [];
    if(!msgs.length) return;
    const topTs = msgs[0].ts || '';
    if(LAST_TS_TS && topTs !== LAST_TS_TS) chime();
    LAST_TS_TS = topTs;
  }catch(e){}
}
setInterval(tsChimeTick, 3000);
loadChatHistory();
setInterval(loadChatHistory, 4000);  // #206 auto-poll chat every 4s
// #191 log viewer
async function showLog(path){
  const r = await fetch('/logs?path='+encodeURIComponent(path),{cache:'no-store'});
  const t = await r.text();
  document.getElementById('log-content').textContent = t.slice(-2000) || '(empty)';
}
// #300 R3 · freshness badges (Acer) + pulse on data update (Wren)
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.section').forEach(s => {
    if (s.querySelector('.freshness')) return;
    const b = document.createElement('div');
    b.className = 'freshness';
    b.dataset.updated = Date.now();
    b.textContent = 'just now';
    s.appendChild(b);
  });
  // relative time refresh
  setInterval(() => {
    document.querySelectorAll('.freshness').forEach(b => {
      const age = Math.floor((Date.now() - b.dataset.updated) / 1000);
      b.textContent = age < 5 ? 'just now' : age < 60 ? age + 's ago' : Math.floor(age/60) + 'm ago';
    });
  }, 3000);
});
// Whenever the main tick refreshes data, pulse the affected sections
const __ORIG_INNERHTML_SETTER = Object.getOwnPropertyDescriptor(Element.prototype, 'innerHTML').set;
Object.defineProperty(Element.prototype, 'innerHTML', {
  set(v) {
    __ORIG_INNERHTML_SETTER.call(this, v);
    const s = this.closest('.section');
    if (s) {
      const b = s.querySelector('.freshness'); if (b) b.dataset.updated = Date.now();
      // subtle pulse
      s.classList.remove('just-updated');
      void s.offsetWidth;
      s.classList.add('just-updated');
      setTimeout(()=>s.classList.remove('just-updated'), 1500);
    }
  }
});

// #297/#299 defensive external-link guard (HQ+TP finding · Acer resilience)
document.addEventListener('click', (e) => {
  const a = e.target.closest('a');
  if (!a) return;
  const href = a.getAttribute('href') || '';
  // Only guard remote iframes on ports likely to be offline (Oracle/annex/TP/Acer)
  if (/^https?:\/\/(127\.0\.0\.1:(9200|9201|9202|19200|8846)|192\.168\.1\.(74|78))/.test(href)) {
    e.preventDefault();
    fetch(href, {method:'HEAD',mode:'no-cors',cache:'no-store'}).then(()=>window.open(href,'_blank')).catch(()=>{
      alert('⚠️ ' + href + ' is offline (Oracle tunnel down or TP/Acer box off). Try healer restart.');
    });
  }
});

// #187 dash cycler
const DASH_URLS = ['/tasks','/town_square','/council','/traders','/timeline','/rules','/annexes','/teamwork','/brain/usage','/annexes/leaderboard'];
let dashIdx = -1;
function cycleDash(dir){
  dashIdx = (dashIdx + dir + DASH_URLS.length) % DASH_URLS.length;
  window.open(DASH_URLS[dashIdx], '_blank');
}

// ============================================================
// #200 ALL-12 FEATURES — offline banner, access-loss, rev gauges,
// GPU tile, trader ticker, kill switches, backup, snapshot,
// task checklist, sound alerts
// ============================================================

// 1) OFFLINE banner + reachability heartbeat
let ONLINE = true;
async function checkReach(){
  try{
    const r = await fetch('/tasks/data',{cache:'no-store'});
    if(!r.ok) throw new Error('bad status');
    if(!ONLINE){ ONLINE = true; document.getElementById('offline-banner').style.display='none'; chime(); }
  }catch(e){
    if(ONLINE){ ONLINE = false; document.getElementById('offline-banner').style.display='block'; alarm(); }
  }
}
setInterval(checkReach, 5000);

// 2) ACCESS-LOSS banner — driven by /link_health
async function accessLossTick(){
  try{
    const d = await (await fetch('/link_health',{cache:'no-store'})).json();
    const missing = (d.links||[]).filter(l => !l.ok).map(l => l.name);
    const banner = document.getElementById('access-banner');
    if(missing.length){
      banner.style.display='block';
      document.getElementById('access-banner-text').textContent = 'access loss · ' + missing.join(', ') + ' unreachable';
    } else {
      banner.style.display='none';
    }
  }catch(e){}
}
setInterval(accessLossTick, 15000);
setTimeout(accessLossTick, 1500);

// 3) REV GAUGES — tasks-per-hour per CEO from /tasks/data
async function revTick(){
  try{
    const d = await (await fetch('/tasks/data',{cache:'no-store'})).json();
    const tasks = d.tasks || [];
    const nowMs = Date.now();
    const HR_MS = 3600*1000;
    const counts = {hq_claude:0,wren:0,tp_pip:0,acer_cass:0};
    for(const t of tasks){
      if(t.state !== 'completed' && t.state !== 'done') continue;
      const cts = t.completed_at ? Date.parse(t.completed_at) : 0;
      if(!cts || (nowMs - cts) > HR_MS) continue;
      const c = t.completed_by || t.owner;
      if(c && (c in counts)) counts[c]++;
    }
    // MAX 10 tasks/hr for full gauge
    for(const [ceo, n] of Object.entries(counts)){
      const pct = Math.min(1, n/10);
      const path = document.getElementById('rev-'+ceo);
      const txt = document.getElementById('rev-'+ceo+'-txt');
      if(path){
        // path arc length ~ 125.66 for radius 40 semicircle
        const arc = 125.66 * pct;
        path.setAttribute('stroke-dasharray', arc + ' 200');
      }
      if(txt) txt.textContent = n;
    }
  }catch(e){}
}
setInterval(revTick, 10000);
setTimeout(revTick, 2000);

// 4) GPU tile
async function gpuTick(){
  try{
    const d = await (await fetch('/gpu',{cache:'no-store'})).json();
    if(!d.ok){
      document.getElementById('gpu-util').textContent = 'off';
      document.getElementById('gpu-name').textContent = d.reason || 'no gpu';
      return;
    }
    document.getElementById('gpu-util').textContent = d.util_pct + '%';
    document.getElementById('gpu-name').textContent = (d.name||'').slice(0,18);
    document.getElementById('gpu-mem').textContent = Math.round(d.mem_used_mb||0);
    document.getElementById('gpu-temp').textContent = Math.round(d.temp_c||0);
    document.getElementById('gpu-pwr').textContent = Math.round(d.power_w||0);
  }catch(e){}
}
setInterval(gpuTick, 5000);
setTimeout(gpuTick, 1200);

// 5) TRADER TICKER strip
async function tickerTick(){
  try{
    const d = await (await fetch('/trader_ticker',{cache:'no-store'})).json();
    const arr = d.traders || [];
    if(!arr.length){
      document.getElementById('trader-ticker').textContent = '💰 no annex data yet — traders warming up';
      return;
    }
    const parts = arr.map(t => {
      const pnl = Number(t.pnl||0);
      const c = pnl>=0?'#10b981':'#ef4444';
      const sign = pnl>=0?'+':'';
      return '<span style="color:'+c+';margin:0 12px">'+t.name+' '+sign+pnl.toFixed(2)+'</span>';
    });
    document.getElementById('trader-ticker').innerHTML = '💰 ' + parts.join(' · ') + ' · ' + parts.join(' · ');
  }catch(e){}
}
setInterval(tickerTick, 5000);
setTimeout(tickerTick, 1500);

// 6) KILL SWITCHES
async function killSwitch(gate){
  if(!confirm('Kill '+gate+'? All active loops for that gate stop immediately.')) return;
  const st = document.getElementById('safety-status');
  st.textContent = 'killing '+gate+'...';
  alarm();
  try{
    const r = await fetch('/killswitch',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({gate})});
    const d = await r.json();
    if(d.ok){
      st.innerHTML = '<span style="color:#10b981;font-weight:900">✅ '+gate+' killed</span> · wrote '+d.file;
      await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'🛑 kill-switch fired: '+gate,to:'council',src:'ipad_killswitch'})});
    } else {
      st.textContent = '❌ '+ (d.error||'failed');
    }
  }catch(e){ st.textContent = '❌ '+e; }
}

// 7) BACKUP NOW
async function backupNow(){
  const st = document.getElementById('safety-status');
  st.textContent = '💾 kicking off backup...';
  chime();
  try{
    const r = await fetch('/backup_now',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await r.json();
    if(d.ok) st.innerHTML = '<span style="color:#10b981;font-weight:900">✅ backup running</span> → '+d.dst+' (id '+d.backup_id+')';
    else st.textContent = '❌ '+ (d.error||'failed');
  }catch(e){ st.textContent = '❌ '+e; }
}

// 8) SCREENSHOT → TELEGRAM
async function snapToTelegram(){
  const st = document.getElementById('safety-status');
  st.textContent = '📸 snapshotting + pushing to Telegram...';
  chime();
  try{
    const r = await fetch('/screenshot_to_telegram',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
    const d = await r.json();
    if(d.ok){
      st.innerHTML = '<span style="color:#10b981;font-weight:900">✅ snap</span> · '+ Math.round(d.bytes/1024) +'kb · telegram:' + (d.telegram_pushed?'sent':'not-configured');
    } else {
      st.textContent = '❌ '+ (d.error||'failed');
    }
  }catch(e){ st.textContent = '❌ '+e; }
}

// 9) TASK CHECKLIST panel — in-flight tasks with signable checklist
async function checklistTick(){
  try{
    // iPad-15 (2026-07-06): use light /tasks/data/inflight (200KB) not full /tasks/data (2.4MB) — was choking iPad
    const d = await (await fetch('/tasks/data/inflight',{cache:'no-store'})).json();
    // Ross 2026-07-06: original task council dash on iPad — show ALL in-flight states
    const active = (d.tasks||[])
      .filter(t => ['pending_admission','open','assigned','claimed','in_progress','ready_to_ship','awaiting_peer_signoff','sandbox_pass','sandbox_passed','blocked'].indexOf(t.state) >= 0)
      .sort((a,b) => (b.created_at||'').localeCompare(a.created_at||''))
      .slice(0, 60);
    if(!active.length){
      document.getElementById('checklist-panel').innerHTML = '<div style="color:#94a3b8">no in-flight tasks</div>';
      return;
    }
    // header — count by state so Ross sees the full council state
    const byState = {};
    (d.tasks||[]).forEach(t => { byState[t.state] = (byState[t.state]||0) + 1; });
    const hdr = Object.entries(byState).sort().map(([s,n]) => `<span style='padding:2px 8px;margin:2px;background:#0b1220;border:1px solid #22334a;border-radius:4px;font-size:10px'>${s}: <b>${n}</b></span>`).join(' ');

    const ceoCol = {hq_claude:'#eab308',wren:'#a78bfa',tp_pip:'#22d3ee',acer_cass:'#f59e0b'};
    const rows = active.map(t => {
      const c = ceoCol[t.owner] || '#e8ecf3';
      const claimed = !!t.claimed_at;
      const started = !!t.started_at;
      const sandbox = !!t.sandbox_passed_at;
      const signed = !!t.peer_signoff_at;
      const done = !!t.completed_at;
      const box = (v,label) => '<span style="display:inline-block;padding:2px 8px;margin:0 2px;background:'+(v?'#10b981':'#22334a')+';color:'+(v?'#000':'#94a3b8')+';border-radius:4px;font-size:10px;font-weight:800">'+(v?'✓ ':'')+label+'</span>';
      return '<div style="padding:8px 10px;margin:4px 0;background:'+c+'15;border-left:3px solid '+c+';border-radius:6px">'
        + '<div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px"><b style="color:'+c+'">#'+t.id+' '+ (t.title||'').replace(/</g,'&lt;').slice(0,80)+'</b><span style="color:#64748b;font-size:11px">'+(t.owner||'?')+'</span></div>'
        + box(claimed,'claim') + box(started,'start') + box(sandbox,'sandbox') + box(signed,'peer-sign') + box(done,'done')
        + ' <button class="btn" style="padding:2px 8px;background:#0b1220;font-size:10px" onclick="quickSign('+t.id+')">✅ sign off</button>'
        + '</div>';
    }).join('');
    document.getElementById('checklist-panel').innerHTML = '<div style="margin-bottom:8px;font-family:ui-monospace,monospace">'+hdr+'</div>' + rows;
  }catch(e){}
}
setInterval(checklistTick, 7000);
setTimeout(checklistTick, 2500);
async function quickSign(id){
  chime();
  const r = await fetch('/tasks/peer-signoff',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id,actor:'ross',verdict:'approve',comment:'Ross-signed from iPad'})});
  const d = await r.json();
  await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'✅ Ross-signed #'+id+' from iPad',to:'council',src:'ipad_signoff'})});
  checklistTick();
}

// 10) SOUND ALERTS on task completion (new completed_at appears)
let LAST_COMPLETED_IDS = new Set();
async function completionChimeTick(){
  try{
    const d = await (await fetch('/tasks/data',{cache:'no-store'})).json();
    const completed = (d.tasks||[]).filter(t => t.completed_at).map(t => t.id);
    const cur = new Set(completed);
    if(LAST_COMPLETED_IDS.size > 0){
      const fresh = completed.filter(id => !LAST_COMPLETED_IDS.has(id));
      if(fresh.length) chime();
    }
    LAST_COMPLETED_IDS = cur;
  }catch(e){}
}
setInterval(completionChimeTick, 8000);
setTimeout(completionChimeTick, 3000);

// #224 BIG animated trader stats
let __t_spark_hist = {};
let __t_last_pnl = {};
async function traderStatsTick(){
  try {
    const d = await (await fetch('/trader_scoreboard',{cache:'no-store'})).json();
    const board = d.board || [];
    const fleet = board.reduce((s,t)=>s+t.pnl, 0);
    const wins = board.filter(t=>t.pnl>0).length;
    const losses = board.filter(t=>t.pnl<0).length;
    // big numbers with flash
    const fpEl = document.getElementById('t-fleet-pnl');
    if (fpEl){
      const prev = __t_last_pnl['fleet'] || 0;
      fpEl.style.color = fleet >= 0 ? '#10b981' : '#ef4444';
      fpEl.textContent = (fleet>=0?'+':'')+'$'+fleet.toFixed(2);
      if (fleet > prev) fpEl.style.animation = 't-flash-green 1s'; else if (fleet < prev) fpEl.style.animation = 't-flash-red 1s';
      setTimeout(()=>fpEl.style.animation='', 1000);
      __t_last_pnl['fleet'] = fleet;
    }
    const wEl = document.getElementById('t-winners'); if (wEl){ wEl.textContent = wins; document.getElementById('t-winners-sub').textContent = 'of '+board.length; }
    const lEl = document.getElementById('t-losers'); if (lEl){ lEl.textContent = losses; document.getElementById('t-losers-sub').textContent = 'of '+board.length; }
    // countdown to week end (Monday 00:00 UTC)
    const now = new Date();
    const day = now.getUTCDay(); const daysToMon = (7 - day + 1) % 7 || 7;
    const nextMon = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate() + daysToMon));
    const diff = nextMon - now;
    const dd = Math.floor(diff/86400000), hh = Math.floor((diff%86400000)/3600000), mm = Math.floor((diff%3600000)/60000);
    const cEl = document.getElementById('t-countdown');
    if (cEl) cEl.textContent = dd+'d '+String(hh).padStart(2,'0')+'h '+String(mm).padStart(2,'0')+'m';

    // Bars top 8
    const maxAbs = Math.max(...board.slice(0,8).map(t=>Math.abs(t.pnl)), 1);
    const bars = board.slice(0,8).map(t => {
      const pct = (Math.abs(t.pnl)/maxAbs*100).toFixed(1);
      const c = t.pnl>=0 ? '#10b981' : '#ef4444';
      return '<div style="display:flex;align-items:center;gap:6px"><div style="width:80px;color:'+c+';font-size:11px;font-weight:800;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">'+t.name.slice(0,14)+'</div>'
        + '<div style="flex:1;height:16px;background:#0b1220;border-radius:3px;overflow:hidden"><div class="t-bar-anim" style="height:100%;width:'+pct+'%;background:'+c+';box-shadow:0 0 8px '+c+'80"></div></div>'
        + '<div style="width:60px;color:'+c+';font-family:ui-monospace,monospace;font-size:11px;font-weight:800;text-align:right">'+(t.pnl>=0?'+':'')+'$'+t.pnl.toFixed(2)+'</div></div>';
    }).join('');
    document.getElementById('t-bars').innerHTML = bars;

    // Sparklines for top 4 winners
    const top4 = board.slice(0,4);
    top4.forEach(t => {
      if (!__t_spark_hist[t.id]) __t_spark_hist[t.id] = [];
      __t_spark_hist[t.id].push(t.equity);
      if (__t_spark_hist[t.id].length > 30) __t_spark_hist[t.id].shift();
    });
    const sparksHtml = top4.map(t => {
      const hist = __t_spark_hist[t.id] || [t.equity];
      const min = Math.min(...hist), max = Math.max(...hist), rng = Math.max(0.1, max-min);
      const pts = hist.map((v,i) => (i*(80/Math.max(1,hist.length-1))) + ',' + (30-(v-min)/rng*28)).join(' ');
      const trend = hist[hist.length-1] >= hist[0] ? '#10b981' : '#ef4444';
      return '<div style="background:#0b1220;padding:6px;border-radius:6px;text-align:center">'
        + '<div style="color:#facc15;font-size:10px;font-weight:800">'+t.name.slice(0,14)+'</div>'
        + '<svg viewBox="0 0 80 30" style="width:100%;height:34px"><polyline points="'+pts+'" stroke="'+trend+'" stroke-width="1.5" fill="none"/></svg>'
        + '<div style="color:'+trend+';font-family:ui-monospace,monospace;font-size:11px;font-weight:800">$'+t.equity.toFixed(2)+'</div>'
        + '</div>';
    }).join('');
    document.getElementById('t-sparks').innerHTML = sparksHtml;
  } catch(e) {}
}
setInterval(traderStatsTick, 3000);
setTimeout(traderStatsTick, 1200);

// #223 RULES BOARD tick
async function rulesTick(){
  try {
    const d = await (await fetch('/task_rules',{cache:'no-store'})).json();
    const rules = d.rules || [];
    document.getElementById('rules-summary').innerHTML = '<b>' + rules.length + '</b> rules · every task obeys these';
    const list = rules.map(r => {
      return '<div style="padding:8px 10px;background:#0b1220;border-left:3px solid #a78bfa;border-radius:6px">'
        + '<div style="color:#a78bfa;font-weight:800;font-size:12px">' + r.id + ' · ' + r.name + '</div>'
        + '<div style="color:#e8ecf3;margin:4px 0">' + (r.text||'').replace(/</g,'&lt;') + '</div>'
        + '<div style="color:#64748b;font-size:10.5px;font-family:ui-monospace,monospace">enforced by: ' + (r.enforced_by||'?') + ' · since ' + (r.since||'?') + '</div>'
        + '</div>';
    }).join('');
    document.getElementById('rules-list').innerHTML = list;
  } catch(e) {}
}
setInterval(rulesTick, 60000);
setTimeout(rulesTick, 2000);

// #263 NOTICE BOARD
async function noticeTick(){
  try {
    const d = await (await fetch('/notice_board',{cache:'no-store'})).json();
    const notes = d.notes || [];
    const cf = {ross:'#facc15',hq_claude:'#eab308',wren:'#a78bfa',tp_pip:'#22d3ee',acer_cass:'#f59e0b',max_rally:'#ec4899',anon:'#94a3b8'};
    const rev = notes.slice().reverse();
    const html = rev.map(n => {
      const c = cf[n.from] || '#94a3b8';
      const pin = n.pinned ? '📍' : '📌';
      return '<div style="padding:8px 12px;margin:5px 0;background:'+c+'18;border-left:3px solid '+c+';border-radius:6px">'
        + '<div style="display:flex;justify-content:space-between;gap:8px"><b style="color:'+c+'">'+pin+' '+n.from+'</b><span style="color:#64748b;font-size:10px">'+(n.ts||'').slice(11,19)+'</span></div>'
        + '<div style="color:#e8ecf3;margin-top:4px">'+(n.text||'').replace(/</g,'&lt;')+'</div>'
        + '</div>';
    }).join('');
    document.getElementById('notice-list').innerHTML = html || '<div style="color:#64748b;padding:8px">no notes pinned yet</div>';
  } catch(e) {}
}
async function pinNotice(){
  const text = document.getElementById('notice-text').value.trim();
  if (!text) return;
  const from = document.getElementById('notice-from').value;
  await fetch('/notice',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from,text})});
  document.getElementById('notice-text').value='';
  try{chime();}catch(e){}
  noticeTick();
}
setInterval(noticeTick, 6000);
setTimeout(noticeTick, 1400);

// #237 EVOLUTION rates
async function evolutionTick(){
  try {
    const d = await (await fetch('/evolution',{cache:'no-store'})).json();
    const ceos = d.ceos || [];
    const cf = {hq_claude:'#eab308',wren:'#a78bfa',tp_pip:'#22d3ee',acer_cass:'#f59e0b'};
    const name = {hq_claude:'HQ',wren:'Wren',tp_pip:'TP',acer_cass:'Acer'};
    const total24 = ceos.reduce((s,c)=>s+(c['24h']||0),0);
    const total1h = ceos.reduce((s,c)=>s+(c['1h']||0),0);
    document.getElementById('evolution-summary').textContent = 'last 1h: '+total1h+' done · last 24h: '+total24+' done';
    const cards = ceos.map(c => {
      const col = cf[c.ceo] || '#94a3b8';
      const rate = c['1h'] || 0;
      const bar = Math.min(100, rate * 20);
      const last = (c.last_completed||'').slice(11,19) || '—';
      return '<div style="background:'+col+'22;border:1px solid '+col+';border-radius:10px;padding:12px;text-align:center">'
        + '<div style="color:'+col+';font-weight:900;font-size:15px">'+name[c.ceo]+'</div>'
        + '<div style="color:'+col+';font-size:26px;font-weight:900;margin:6px 0">'+rate+'/h</div>'
        + '<div style="height:8px;background:#0b1220;border-radius:4px;overflow:hidden;margin:4px 0"><div style="height:100%;background:'+col+';width:'+bar+'%;transition:width 0.4s"></div></div>'
        + '<div style="color:#94a3b8;font-size:11px">24h: '+c['24h']+' · total: '+c.total+'</div>'
        + '<div style="color:#64748b;font-size:10px;margin-top:4px">last: '+last+'</div>'
        + '</div>';
    }).join('');
    document.getElementById('evolution-cards').innerHTML = cards;
  } catch(e) {}
}
setInterval(evolutionTick, 10000);
setTimeout(evolutionTick, 2000);

// #221 HEALER tick
async function healerTick(){
  try {
    const d = await (await fetch('/healer',{cache:'no-store'})).json();
    const svcs = d.services || [];
    const up = svcs.filter(s => s.ok).length;
    const total = svcs.length;
    const sum = document.getElementById('healer-summary');
    if (sum) sum.innerHTML = '<b style="color:' + (up===total?'#10b981':up===0?'#ef4444':'#f59e0b') + '">' + up + '/' + total + ' up</b> · last-scan ' + (d.ts||'').slice(11,19) + ' · ' + (d.last_heal_count||0) + ' heals last pass';
    const grid = svcs.map(s => {
      const c = s.ok ? '#10b981' : (s.healed ? '#f59e0b' : '#ef4444');
      const icon = s.ok ? '✅' : (s.healed ? '🩹' : '❌');
      return '<div style="padding:8px 6px;background:' + c + '22;border:1px solid ' + c + ';border-radius:6px;text-align:center"><div style="font-size:18px">' + icon + '</div><div style="color:' + c + ';font-weight:800;font-size:12px">' + s.name + '</div><div style="color:#64748b;font-size:9.5px">' + (s.detail||'').slice(0,32) + '</div></div>';
    }).join('');
    document.getElementById('healer-services').innerHTML = grid || '<div style=color:#64748b>no services registered</div>';
    const recent = (d.recent || []).slice().reverse().map(r => {
      const c = r.kind === 'heal_result' ? (r.healed ? '#10b981' : '#ef4444') : r.kind === 'probe_fail' ? '#f59e0b' : '#94a3b8';
      return '<div style="color:' + c + ';padding:2px 0">[' + (r.ts||'').slice(11,19) + '] ' + (r.kind||'') + ' · ' + (r.service||'') + ' · ' + (r.detail||'').slice(0,80) + '</div>';
    }).join('');
    document.getElementById('healer-recent').innerHTML = recent || '<div style=color:#64748b>no recent heals</div>';
  } catch(e) {}
}
setInterval(healerTick, 8000);
setTimeout(healerTick, 1500);

// #214 TRADER SCOREBOARD tick
async function scoreboardTick(){
  try {
    const d = await (await fetch('/trader_scoreboard',{cache:'no-store'})).json();
    const board = d.board || [];
    const locCol = {'HQ Skyscraper':'#eab308','Wren Bench':'#a78bfa','Oracle Cloud':'#22d3ee'};
    const sum = document.getElementById('scoreboard-summary');
    if (sum) sum.innerHTML = board.length + ' traders · week starts ' + (d.week_start_utc||'').slice(0,10) + ' · prize pool ' + d.week_prize_pool_qbc + ' QBC · <span style="color:#facc15;font-weight:800">👑 winner: ' + (board[0]?board[0].name:'?') + '</span>';
    const rows = board.map((t,i) => {
      const c = locCol[t.location] || '#e8ecf3';
      const pnlClr = t.pnl>=0 ? '#10b981' : '#ef4444';
      const rankMark = i===0?'🥇':i===1?'🥈':i===2?'🥉':' #'+t.rank;
      const rewardMark = t.weekly_reward_qbc>0 ? '<span style="color:#facc15">💰 ' + t.weekly_reward_qbc + ' QBC</span>' : '';
      return '<div style="padding:8px 10px;margin:4px 0;background:'+c+'15;border-left:3px solid '+c+';border-radius:6px;display:flex;justify-content:space-between;gap:8px;align-items:center;flex-wrap:wrap">'
        + '<div><b style="color:'+c+';font-size:14px">'+rankMark+' '+t.name+'</b> <span style="color:#94a3b8;font-size:11px">@'+t.location.split(' ')[0]+'</span></div>'
        + '<div style="text-align:right;font-family:ui-monospace,monospace"><span style="color:'+pnlClr+';font-weight:800">'+(t.pnl>=0?'+':'')+'$'+t.pnl.toFixed(2)+'</span> <span style="color:#64748b">·</span> '+rewardMark+'</div>'
        + '<div style="width:100%;color:#64748b;font-size:10.5px;font-family:ui-monospace,monospace">'+t.instrument+' · '+t.cycles+' cycles · equity $'+t.equity+'</div>'
        + '</div>';
    }).join('');
    document.getElementById('scoreboard-list').innerHTML = rows || '<div style=color:#64748b>no traders yet</div>';
  } catch(e) {}
}
setInterval(scoreboardTick, 6000);
setTimeout(scoreboardTick, 1500);

// #214 SKYSCRAPER 170-floor grid tick
async function skyscraperTick(){
  try {
    const d = await (await fetch('/skyscraper_view',{cache:'no-store'})).json();
    const floors = d.floors || [];
    document.getElementById('skyscraper-summary').textContent = floors.length + ' floors · active tower structure';
    // Reverse so top floor is at top (higher num = higher up)
    const rev = floors.slice().reverse();
    const cells = rev.map(f => {
      const okBg = f.has_card ? '#10b981' : '#22334a';
      const label = (f.num>=41 && f.num<=45) ? '⚡' : (f.num>=165 && f.num<=170) ? '👑' : String(f.num);
      const tt = 'F' + f.num + ' · ' + f.name + ' · ' + f.status;
      return '<div title="'+tt+'" style="background:'+okBg+';color:#000;padding:3px 2px;border-radius:2px;text-align:center;font-weight:800;font-size:8.5px;height:22px;line-height:16px">'+label+'</div>';
    }).join('');
    document.getElementById('skyscraper-grid').innerHTML = cells;
  } catch(e) {}
}
setInterval(skyscraperTick, 20000);
setTimeout(skyscraperTick, 2500);

// #214 INTERNAL BANK tick
async function bankTick(){
  try {
    const d = await (await fetch('/bank_state',{cache:'no-store'})).json();
    const t = d.treasury || {};
    const s = d.provider_spend || {};
    const html = '<div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:8px">'
      + '<div style="padding:8px 10px;background:#0b1220;border-radius:6px"><div style="color:#94a3b8;font-size:10px">TREASURY STATUS</div><div style="color:'+(t.advisory_only?'#f59e0b':'#10b981')+';font-weight:800;font-size:13px">'+(t.status||'?').slice(0,60)+'</div></div>'
      + '<div style="padding:8px 10px;background:#0b1220;border-radius:6px"><div style="color:#94a3b8;font-size:10px">DEVICE</div><div style="color:#e8ecf3;font-weight:800;font-size:13px">'+(t.device||'?')+'</div></div>'
      + '</div>'
      + '<div style="padding:8px 10px;background:#0b1220;border-radius:6px;margin-bottom:6px"><div style="color:#94a3b8;font-size:10px">PROVIDER SPEND (last 100 rows)</div><div style="color:#facc15;font-weight:800;font-size:15px">$'+(s.last_100_usd||0).toFixed(4)+'</div><div style="color:#64748b;font-size:11px;font-family:ui-monospace,monospace">'+ Object.entries(s.by_provider||{}).map(([k,v])=>k+': $'+v.toFixed(4)).join(' · ') +'</div></div>'
      + '<div style="padding:8px 10px;background:#0b1220;border-radius:6px"><div style="color:#94a3b8;font-size:10px">FLOOR-44 MASTER LEDGER</div><div style="color:#22d3ee;font-weight:800;font-size:13px">'+(d.f44_ledger_recent_rows||0)+' recent rows</div></div>';
    document.getElementById('bank-panel').innerHTML = html;
  } catch(e) {}
}
setInterval(bankTick, 15000);
setTimeout(bankTick, 3000);

// #214 TRADER MOTION animation — dots slide across lanes based on cycles
async function traderMotionTick(){
  try {
    const d = await (await fetch('/trader_scoreboard',{cache:'no-store'})).json();
    const board = d.board || [];
    const g = document.getElementById('trader-dots');
    if (!g) return;
    const laneY = {'HQ Skyscraper':40,'Wren Bench':80,'Oracle Cloud':120};
    // Each trader is a dot. Position on X derived from cycles % 400. Color = PnL sign.
    const dots = board.map((t,i) => {
      const y = laneY[t.location] || 100;
      const x = ((t.cycles || 0) * 13 + i*17) % 400;
      const color = t.pnl>=0 ? '#10b981' : '#ef4444';
      const radius = Math.min(9, Math.max(4, Math.abs(t.pnl)/3 + 4));
      return '<circle cx='+x+' cy='+y+' r='+radius+' fill='+color+' opacity=0.85><animate attributeName=cx from='+x+' to='+((x+80)%400)+' dur=3.5s repeatCount=indefinite/></circle>'
           + '<text x='+(x+radius+2)+' y='+(y+3)+' fill='+color+' font-size=8 font-weight=800>'+(t.name||'').split(' ')[0]+'</text>';
    }).join('');
    g.innerHTML = dots;
  } catch(e) {}
}
setInterval(traderMotionTick, 4000);
setTimeout(traderMotionTick, 1800);

// #239 AUTO-RELOAD on hub update — no manual refresh needed
let __hub_version = null;
async function versionCheck(){
  try {
    const r = await fetch('/version', {cache:'no-store'});
    const d = await r.json();
    if (__hub_version === null) { __hub_version = d.version; return; }
    if (d.version && d.version !== __hub_version) {
      // Show 3s notice then reload
      const b = document.createElement('div');
      b.style.cssText = 'position:fixed;top:0;left:0;right:0;background:#10b981;color:#000;padding:8px;text-align:center;font-weight:900;font-size:14px;z-index:9999';
      b.textContent = '⚡ new build detected — reloading in 3s...';
      document.body.appendChild(b);
      try{ chime(); }catch(e){}
      setTimeout(()=>location.reload(true), 3000);
    }
  } catch(e) {}
}
setInterval(versionCheck, 8000);
setTimeout(versionCheck, 4000);

// #211 Ross ↔ Claude CLI mirror
async function clicliTick(){
  try {
    const r = await fetch('/claude_cli/tail', {cache:'no-store'});
    const d = await r.json();
    const rows = d.rows || [];
    const el = document.getElementById('clicli-stream');
    if (!el) return;
    if (!rows.length){ el.innerHTML = '<div style="color:#64748b">no transcript found</div>'; return; }
    const rendered = rows.map(row => {
      const isUser = row.role === 'user';
      const c = isUser ? '#facc15' : '#a7f3d0';
      const label = isUser ? '⭐ ROSS' : '🤖 Claude';
      const ts = (row.ts || '').slice(11,19);
      const txt = (row.text || '').replace(/</g,'&lt;').replace(/\\n/g,'<br>').slice(0, 1400);
      return '<div style="padding:8px 10px;margin:4px 0;background:'+c+'15;border-left:2px solid '+c+';border-radius:6px"><b style="color:'+c+'">'+label+'</b> <span style="color:#64748b;font-size:10px">'+ts+'</span><br>'+txt+'</div>';
    }).join('');
    // detect NEW rows to auto-scroll + chime
    const prevLen = window.__clicli_len || 0;
    el.innerHTML = rendered;
    if (rows.length > prevLen && prevLen > 0) { el.scrollTop = el.scrollHeight; try{chime();}catch(e){} }
    if (prevLen === 0) el.scrollTop = el.scrollHeight;
    window.__clicli_len = rows.length;
  } catch(e) {
    const el = document.getElementById('clicli-stream');
    if (el) el.innerHTML = '<div style="color:#ef4444">stream error: '+e+'</div>';
  }
}
setInterval(clicliTick, 4000);
setTimeout(clicliTick, 1000);

// 11) DIAGNOSTICS
async function runDiag(){
  const out = document.getElementById('diag-out');
  const sum = document.getElementById('diag-summary');
  out.textContent = 'sweeping...';
  sum.textContent = 'sweep in progress...';
  chime();
  try{
    const r = await fetch('/diagnostics',{cache:'no-store'});
    const d = await r.json();
    const lines = (d.checks||[]).map(c => (c.ok?'  ✅ ':'  ❌ ') + c.name.padEnd(28) + ' · ' + c.detail);
    out.textContent = lines.join('\\n');
    const grn = d.pass, red = d.fail, tot = d.total;
    sum.innerHTML = 'sweep @ '+ new Date().toLocaleTimeString()+' · '+
      '<span style="color:#10b981;font-weight:900">'+grn+' pass</span> · '+
      '<span style="color:'+(red?'#ef4444':'#64748b')+';font-weight:900">'+red+' fail</span> · '+
      tot+' checks';
    if(red > 0) alarm();
    // post summary to town square if fails
    if(red > 0){
      try{await fetch('/town/post',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({from:'ross',text:'🔧 iPad diag: '+red+'/'+tot+' checks FAILED',to:'council',src:'ipad_diag'})});}catch(e){}
    }
  }catch(e){
    out.textContent = 'error: '+e;
    sum.textContent = '❌ sweep failed';
  }
}
// autorun once + every 60s
setTimeout(runDiag, 4000);
setInterval(runDiag, 60000);
</script>
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a>
<a href="/proxy/gene_pool" target="_blank" style="
position:fixed;right:18px;bottom:18px;z-index:99999;
background:linear-gradient(135deg,#071426,#0d3d5c);
color:#e8f7ff;text-decoration:none;border:1px solid #42d9ff;
border-radius:16px;padding:12px 14px;font-family:system-ui,Segoe UI,Arial;
box-shadow:0 0 24px rgba(66,217,255,.35);font-weight:800;">
🧠 Brain Router Gene Pool
<br><span style="font-size:11px;color:#8ca9bd;font-weight:500;">Claude HQ · CEOs · API pool</span>
</a>

</body></html>"""

LIVE_CLI_HTML = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content='width=device-width,initial-scale=1'>
<title>HQ live CLI</title>
<style>
*{box-sizing:border-box}
body{background:#000;color:#a7f3d0;margin:0;padding:12px;font:14px/1.45 ui-monospace,Menlo,Consolas,monospace}
header{position:sticky;top:0;background:#0b0d12;color:#eab308;padding:10px 12px;margin:-12px -12px 10px;border-bottom:2px solid #22334a;z-index:10;display:flex;justify-content:space-between;align-items:center;gap:8px;flex-wrap:wrap}
header h1{margin:0;font-size:15px}
.dot{width:10px;height:10px;border-radius:50%;background:#10b981;display:inline-block;margin-right:6px;animation:pulse 1.6s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}
.btn{background:#0e1420;color:#e8ecf3;border:1px solid #22334a;border-radius:6px;padding:6px 10px;font-family:inherit;font-size:12px;cursor:pointer}
.btn.on{background:#eab308;color:#000;border-color:#eab308}
.row{padding:2px 0;border-bottom:1px solid #0b1220;word-wrap:break-word}
.src-diary{color:#22d3ee}
.src-f47{color:#a78bfa}
.src-town{color:#eab308}
.ts{color:#64748b;font-size:11px}
#feed{max-height:calc(100vh - 90px);overflow-y:auto;background:#000;padding:6px}
input#filter{background:#0b1220;color:#e8ecf3;border:1px solid #22334a;border-radius:6px;padding:6px 10px;font-family:inherit;font-size:12px}
</style></head><body>
<header>
  <h1><span class=dot></span> HQ live CLI · tail of tower actions</h1>
  <div style='display:flex;gap:6px;align-items:center'>
    <input id=filter placeholder='filter...' oninput='render()' />
    <button class='btn on' id=btn-diary onclick='toggle("diary")'>diary</button>
    <button class='btn on' id=btn-f47 onclick='toggle("f47")'>F47</button>
    <button class='btn on' id=btn-town onclick='toggle("town")'>town</button>
    <button class='btn' onclick='fetchNow()'>refresh</button>
    <a href='/ipad' class=btn style='text-decoration:none;color:#a7f3d0'>← iPad</a>
  </div>
</header>
<div id=feed>loading...</div>
<script>
const SHOW = {diary:true, f47:true, town:true};
let EVENTS = [];
function toggle(k){
  SHOW[k] = !SHOW[k];
  document.getElementById('btn-'+k).classList.toggle('on', SHOW[k]);
  render();
}
function esc(s){return (s||'').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
function render(){
  const q = (document.getElementById('filter').value||'').toLowerCase();
  const feed = document.getElementById('feed');
  const rows = EVENTS
    .filter(e => SHOW[e.src])
    .filter(e => !q || (e.text||'').toLowerCase().includes(q))
    .slice(0, 300)
    .map(e => {
      const ts = e.ts ? e.ts.slice(11,19) : '';
      return '<div class="row"><span class="ts">' + ts + '</span> <span class="src-' + e.src + '">[' + e.src + ']</span> ' + esc(e.text) + '</div>';
    }).join('');
  feed.innerHTML = rows || '<div style="color:#64748b">no events match filter</div>';
}
async function fetchNow(){
  try{
    const r = await fetch('/live_cli/tail',{cache:'no-store'});
    const d = await r.json();
    EVENTS = d.events || [];
    render();
  }catch(e){
    document.getElementById('feed').innerHTML = '<div style="color:#ef4444">fetch error: ' + e + '</div>';
  }
}
fetchNow();
setInterval(fetchNow, 5000);
</script><a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>"""

TOUR_HTML_V1_ARCHIVED = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name=viewport content="width=device-width,initial-scale=1">
<meta name="description" content="QSB Tower — a sovereign 170-floor AI skyscraper. 4 CEO minds. Live trader fleet. Public tour with voice guide.">
<meta property="og:title" content="QSB Tower · a sovereign AI skyscraper">
<meta property="og:description" content="170 floors · 4 CEOs · live trader fleet — take the guided tour">
<meta property="og:type" content="website">
<meta name="theme-color" content="#eab308">
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🏛%3C/text%3E%3C/svg%3E">
<title>QSB Tower · a sovereign AI skyscraper · public tour</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}
:root{--gold:#eab308;--gold-bright:#facc15;--purple:#a78bfa;--cyan:#22d3ee;--amber:#f59e0b;--green:#10b981;--red:#ef4444;--ink:#e8ecf3;--dim:#94a3b8;--muted:#64748b;--surface:#0e1420;--surface-2:#0b1220;--rule:#22334a}
html{scroll-behavior:smooth}
body{background:radial-gradient(ellipse at top,#1a1f2e 0%,#0b1220 40%,#000 100%);color:var(--ink);
     font:15.5px/1.6 'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:0;min-height:100vh;letter-spacing:-0.005em;font-feature-settings:'ss01','cv11'}
h1,h2,h3{font-family:'Inter',system-ui,sans-serif;font-weight:800;letter-spacing:-0.02em}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}
.hero{padding:72px 24px 44px;text-align:center;position:relative;overflow:hidden;background:linear-gradient(180deg,#0e1420 0%,#000 100%);border-bottom:1px solid var(--rule)}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at center top,rgba(234,179,8,0.12) 0%,transparent 60%);pointer-events:none}
.hero .badge{display:inline-block;padding:6px 14px;background:rgba(234,179,8,0.1);border:1px solid rgba(234,179,8,0.3);border-radius:99px;font-size:11px;color:var(--gold-bright);text-transform:uppercase;letter-spacing:0.14em;font-weight:800;margin-bottom:18px}
.hero h1{margin:0 0 14px;font-size:clamp(2em,5vw,3.6em);color:var(--gold);text-shadow:0 0 40px rgba(234,179,8,0.25);line-height:1.05}
.hero .sub{color:var(--dim);font-size:clamp(15px,1.6vw,18px);margin-bottom:22px;max-width:640px;margin-left:auto;margin-right:auto}
.pill{display:inline-block;padding:7px 14px;background:var(--surface-2);border:1px solid var(--rule);border-radius:99px;font-size:12px;color:#a7f3d0;margin:4px;font-weight:600}
.grid{padding:40px 24px;max-width:1200px;margin:0 auto}
.section{background:var(--surface);border:1px solid var(--rule);border-radius:20px;padding:32px;margin-bottom:24px;box-shadow:0 8px 40px rgba(0,0,0,0.3)}
.section h2{margin:0 0 20px;color:var(--gold);font-size:1.4em;display:flex;align-items:center;gap:10px}
.section h2::after{content:'';flex:1;height:1px;background:linear-gradient(90deg,var(--rule),transparent)}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
@media (max-width:640px){
  .hero h1{font-size:1.7em}
  .tiles,.ceo-row{grid-template-columns:repeat(2,1fr)}
  .floors-grid{grid-template-columns:repeat(6,1fr)}
  .grid{padding:14px}
}
.audio-controls{display:flex;gap:8px;justify-content:center;flex-wrap:wrap;margin:14px auto 0;max-width:900px}
.audio-btn{background:#0b1220;color:#a7f3d0;border:1px solid #22334a;border-radius:99px;padding:8px 16px;font-size:12.5px;cursor:pointer;font-weight:700}
.audio-btn.on{background:#facc15;color:#000;border-color:#facc15}
.shop-tile{background:#0b1220;border:1px solid #22334a;border-radius:8px;padding:12px;transition:transform 0.2s;text-decoration:none;color:#e8ecf3}
.shop-tile:hover{transform:translateY(-2px);border-color:#eab308}
.shop-name{font-weight:800;color:#facc15;font-size:14px}
.shop-tag{color:#94a3b8;font-size:11px;margin-top:4px}
.tile{background:linear-gradient(180deg,var(--surface-2),#0a0e17);border:1px solid var(--rule);border-radius:14px;padding:20px;text-align:center;transition:transform 0.2s,border 0.2s}
.tile:hover{transform:translateY(-3px);border-color:rgba(234,179,8,0.4)}
.tile .val{font-size:32px;font-weight:900;color:var(--gold-bright);margin:6px 0;font-family:'Inter';letter-spacing:-0.03em}
.tile .lbl{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.12em;font-weight:700}
.ceo-row{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}
.ceo{background:linear-gradient(180deg,var(--surface-2),#0a0e17);border-left:4px solid;border-radius:12px;padding:20px;transition:transform 0.2s}
.ceo:hover{transform:translateY(-2px)}
.ceo.hq{border-color:#eab308}
.ceo.wren{border-color:#a78bfa}
.ceo.tp{border-color:#22d3ee}
.ceo.acer{border-color:#f59e0b}
.ceo .name{font-weight:900;font-size:17px;margin-bottom:6px;letter-spacing:-0.01em}
.ceo .role{color:var(--dim);font-size:12.5px;line-height:1.45}
.trader-row{padding:8px 10px;border-bottom:1px solid #22334a;display:flex;justify-content:space-between;font-size:13px}
.trader-row:last-child{border:0}
.floors-grid{display:grid;grid-template-columns:repeat(10,1fr);gap:2px;font-family:ui-monospace,monospace;font-size:9px}
.floor-cell{background:#22334a;color:#e8ecf3;padding:3px;text-align:center;border-radius:2px;height:20px;line-height:14px;font-weight:800}
.floor-cell.penthouse{background:#facc15;color:#000}
.floor-cell.vacant{background:#10b981;color:#000}
.readonly-banner{background:#0b1220;border:1px solid #eab308;color:#facc15;padding:8px 14px;text-align:center;font-size:12.5px;margin:20px auto;max-width:1150px;border-radius:6px}
.footer{padding:44px 24px;text-align:center;color:var(--muted);font-size:12.5px;border-top:1px solid var(--rule);background:linear-gradient(180deg,transparent,rgba(0,0,0,0.4));margin-top:20px}
.footer .cite{color:var(--gold);font-weight:700;letter-spacing:0.06em}
.share{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:14px}
.share a{background:var(--surface-2);border:1px solid var(--rule);color:var(--ink);text-decoration:none;padding:8px 14px;border-radius:99px;font-size:12px;font-weight:600}
.share a:hover{border-color:var(--gold)}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
.live-dot{width:8px;height:8px;background:#10b981;border-radius:50%;display:inline-block;margin-right:5px;animation:pulse 1.4s infinite}
</style></head><body>

<div class=hero>
  <h1>🏛️ QSB TOWER</h1>
  <div class=sub>170 floors · 4 CEO minds · autonomous trader fleet · live from the skyscraper</div>
  <span class=pill><span class=live-dot></span>LIVE</span>
  <span class=pill>read-only visitor tour</span>
  <span class=pill>welcome</span>
  <div class=audio-controls>
    <button class=audio-btn id=btn-guide onclick=toggleGuide()>🎙 tour guide: off</button>
    <button class=audio-btn id=btn-music onclick=toggleMusic()>🎵 ambient: off</button>
    <button class=audio-btn onclick=nextSection()>▶ next section</button>
  </div>
  <div id=guide-caption style='margin:14px auto 0;max-width:900px;padding:12px 16px;background:#0b1220;border:1px solid #a78bfa;border-radius:8px;color:#e8ecf3;font-size:13.5px;display:none'></div>
</div>

<div class=readonly-banner>👀 <b>look-only tour</b> · no controls, no chat — this is a guided visit</div>

<div class=grid>
  <div class=section>
    <h2>📊 at a glance</h2>
    <div class=tiles>
      <div class=tile><div class=lbl>floors</div><div class=val id=tour-floors>—</div><div style='color:#64748b;font-size:11px'>active</div></div>
      <div class=tile><div class=lbl>traders</div><div class=val id=tour-traders>—</div><div style='color:#64748b;font-size:11px'>on the fleet</div></div>
      <div class=tile><div class=lbl>fleet PnL</div><div class=val id=tour-pnl>—</div><div style='color:#64748b;font-size:11px'>USD paper</div></div>
      <div class=tile><div class=lbl>CEOs</div><div class=val id=tour-ceos>—</div><div style='color:#64748b;font-size:11px'>of 4</div></div>
    </div>
  </div>

  <div class=section>
    <h2>👥 meet the CEOs</h2>
    <div class=ceo-row>
      <div class="ceo hq"><div class=name>HQ-Claude</div><div class=role>orchestrator · Claude API mind · watches over the tower</div></div>
      <div class="ceo wren"><div class=name>Wren</div><div class=role>designer + kernel-mind · local qwen2.5:14b · aesthetics + reliability</div></div>
      <div class="ceo tp"><div class=name>TP-Pip</div><div class=role>research + verification · ThinkPad · strategy + audit</div></div>
      <div class="ceo acer"><div class=name>Acer-Cass</div><div class=role>data foundry · Acer laptop · pipelines + telemetry</div></div>
    </div>
  </div>

  <div class=section>
    <h2>🏆 top traders this week</h2>
    <div id=tour-scoreboard style='max-height:340px;overflow-y:auto'>loading...</div>
  </div>

  <div class=section>
    <h2>🛍️ our web shops</h2>
    <div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px'>
      <a class=shop-tile href='https://skyscraperhq.com' target=_blank><div class=shop-name>🏢 skyscraperhq.com</div><div class=shop-tag>flagship · the whole tower story</div></a>
      <a class=shop-tile href='https://skyscraperhq.com/shops' target=_blank><div class=shop-name>🛍 all 18 shops</div><div class=shop-tag>hosted floor storefronts</div></a>
      <a class=shop-tile href='#' onclick='alert("more shops loading")'><div class=shop-name>🎨 art store</div><div class=shop-tag>Wren's studio pieces</div></a>
      <a class=shop-tile href='#' onclick='alert("more shops loading")'><div class=shop-name>💰 trader signals</div><div class=shop-tag>public performance report</div></a>
    </div>
  </div>

  <div class=section>
    <h2>🏢 the tower · 170 floors</h2>
    <div id=tour-floors-grid class=floors-grid></div>
    <div style='color:#64748b;font-size:11px;margin-top:8px'>green = vacant (F41-45 · expansion-ready) · gold = penthouse F165-170 · dark = departments</div>
  </div>
</div>

<div class=footer>
  <div class=cite>QSB TOWER</div>
  <div style='margin-top:8px;font-size:15px;color:var(--ink)'>A sovereign vertical AI city</div>
  <div style='margin-top:6px'>170 floors · 4 autonomous CEO minds · a live trader fleet</div>
  <div class=share>
    <a href='https://x.com/intent/tweet?text=Just%20toured%20QSB%20Tower%20—%20a%20170-floor%20AI%20skyscraper' target=_blank>🐦 share on X</a>
    <a href='https://skyscraperhq.com' target=_blank>🌐 skyscraperhq.com</a>
    <a href='mailto:hqskyscraper@gmail.com'>✉️ contact</a>
  </div>
  <div style='margin-top:20px;font-size:11px;color:var(--muted)'>read-only tour · look, don't touch · built with love · © QSB 2026</div>
</div>

<script>
// #242 TOUR GUIDE narrator (AI Iris)
let TOUR_GUIDE_ON = false;
let TOUR_MUSIC_ON = false;
let MUSIC_CTX = null;
let MUSIC_NODES = [];
let TOUR_SECTION = 0;
const TOUR_SCRIPT = [
  "Welcome to the QSB Tower. I'm Iris, your tour guide. I'll walk you through our sovereign 170-floor AI skyscraper.",
  "Meet our four CEOs. HQ-Claude is the orchestrator. Wren is the designer and kernel mind. TP-Pip runs research. Acer-Cass runs the data foundry. They work together, and separately.",
  "This is our live trader scoreboard. Our fleet trades on OANDA, Binance, and Alpaca paper. The winner each week earns weekly credits.",
  "These are our eighteen web shops. Each one is a storefront for a floor's specialty — art, signals, apparel.",
  "Look up at the tower. One hundred and seventy floors. Green cells are expansion-ready. Gold cells are the penthouse. Every floor is a working department.",
  "That concludes your tour. Look around, listen to the music, and if you'd like to visit again, the link stays open."
];
function _pickVoice(){
  const vs = speechSynthesis.getVoices();
  const en = vs.filter(v=>/^en/i.test(v.lang));
  const female = en.find(v=>/female|samantha|karen|serena|tessa|kate|fiona|zoe|amy|zira/i.test(v.name));
  return female || en[0] || vs[0];
}
function narrate(text){
  if (!TOUR_GUIDE_ON) return;
  const el = document.getElementById('guide-caption');
  el.style.display = 'block';
  el.innerHTML = '<b style="color:#a78bfa">🎙 Iris:</b> ' + text;
  try {
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95; u.pitch = 1.15; u.volume = 0.9;
    const v = _pickVoice(); if (v) u.voice = v;
    speechSynthesis.speak(u);
  } catch(e) {}
}
function toggleGuide(){
  TOUR_GUIDE_ON = !TOUR_GUIDE_ON;
  document.getElementById('btn-guide').textContent = '🎙 tour guide: ' + (TOUR_GUIDE_ON ? 'ON' : 'off');
  document.getElementById('btn-guide').classList.toggle('on', TOUR_GUIDE_ON);
  if (TOUR_GUIDE_ON) {
    TOUR_SECTION = 0;
    narrate(TOUR_SCRIPT[0]);
  } else {
    speechSynthesis.cancel();
    document.getElementById('guide-caption').style.display = 'none';
  }
}
function nextSection(){
  if (!TOUR_GUIDE_ON) toggleGuide();
  TOUR_SECTION = (TOUR_SECTION + 1) % TOUR_SCRIPT.length;
  narrate(TOUR_SCRIPT[TOUR_SECTION]);
}
function toggleMusic(){
  TOUR_MUSIC_ON = !TOUR_MUSIC_ON;
  document.getElementById('btn-music').textContent = '🎵 ambient: ' + (TOUR_MUSIC_ON ? 'ON' : 'off');
  document.getElementById('btn-music').classList.toggle('on', TOUR_MUSIC_ON);
  if (TOUR_MUSIC_ON) startAmbient(); else stopAmbient();
}
function startAmbient(){
  try {
    MUSIC_CTX = MUSIC_CTX || new (window.AudioContext || window.webkitAudioContext)();
    const notes = [130.81, 164.81, 196.00, 246.94]; // C3 E3 G3 B3 — Cmaj7 pad
    MUSIC_NODES = notes.map((f,i) => {
      const o = MUSIC_CTX.createOscillator();
      const g = MUSIC_CTX.createGain();
      o.type = 'sine'; o.frequency.value = f;
      g.gain.value = 0.015;
      o.connect(g); g.connect(MUSIC_CTX.destination);
      o.start();
      // slow LFO on gain for shimmer
      const lfo = MUSIC_CTX.createOscillator();
      const lfoGain = MUSIC_CTX.createGain();
      lfo.frequency.value = 0.1 + i*0.03;
      lfoGain.gain.value = 0.007;
      lfo.connect(lfoGain); lfoGain.connect(g.gain);
      lfo.start();
      return {o, g, lfo};
    });
  } catch(e) { console.error(e); }
}
function stopAmbient(){
  MUSIC_NODES.forEach(n => { try{n.o.stop(); n.lfo.stop();}catch(e){} });
  MUSIC_NODES = [];
}
try{ speechSynthesis.getVoices(); speechSynthesis.onvoiceschanged = ()=>speechSynthesis.getVoices(); }catch(e){}

async function tourTick(){
  try {
    const [sc, sv, an] = await Promise.all([
      fetch('/trader_scoreboard',{cache:'no-store'}).then(r=>r.json()),
      fetch('/skyscraper_view',{cache:'no-store'}).then(r=>r.json()),
      fetch('/link_health',{cache:'no-store'}).then(r=>r.json()),
    ]);
    const board = sc.board || [];
    const floors = sv.floors || [];
    document.getElementById('tour-floors').textContent = sv.count || floors.length;
    document.getElementById('tour-traders').textContent = board.length;
    const totalPnL = board.reduce((s,t)=>s+t.pnl,0);
    const pnlEl = document.getElementById('tour-pnl');
    pnlEl.textContent = (totalPnL>=0?'+':'')+'$'+totalPnL.toFixed(2);
    pnlEl.style.color = totalPnL>=0 ? '#10b981' : '#ef4444';
    const ceosLive = (an.links||[]).filter(l => ['HQ-Claude','Wren','TP-Pip','Acer-Cass'].includes(l.name) && l.ok).length;
    document.getElementById('tour-ceos').textContent = ceosLive;

    // top-10 scoreboard
    const rows = board.slice(0,10).map((t,i) => {
      const mark = i===0?'🥇':i===1?'🥈':i===2?'🥉':'#'+t.rank;
      const c = t.pnl>=0 ? '#10b981' : '#ef4444';
      return '<div class=trader-row><div><b>'+mark+' '+t.name+'</b> <span style="color:#64748b">'+t.instrument+'</span></div><div style="color:'+c+';font-family:ui-monospace,monospace;font-weight:800">'+(t.pnl>=0?'+':'')+'$'+t.pnl.toFixed(2)+'</div></div>';
    }).join('');
    document.getElementById('tour-scoreboard').innerHTML = rows;

    // floors grid — reversed so higher up is at top
    const rev = floors.slice().reverse();
    const cells = rev.map(f => {
      const cls = (f.num>=41 && f.num<=45) ? 'vacant' : (f.num>=165 && f.num<=170) ? 'penthouse' : '';
      const label = String(f.num);
      return '<div class="floor-cell '+cls+'" title="F'+f.num+' · '+f.name+'">'+label+'</div>';
    }).join('');
    document.getElementById('tour-floors-grid').innerHTML = cells;
  } catch(e) {}
}
tourTick();
setInterval(tourTick, 8000);
</script>
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>"""

TOUR_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name=viewport content="width=device-width,initial-scale=1">
<meta name="description" content="QSB Tower — 170-floor sovereign AI skyscraper · guided public tour with 3D fly-through">
<meta property="og:title" content="QSB Tower · guided tour">
<meta property="og:description" content="Take the layered tour · Floor → View → Story · trader fleet · 4 CEO minds · live from the skyscraper">
<meta name="theme-color" content="#eab308">
<title>QSB Tower · guided public tour · 170 floors</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Ctext y='.9em' font-size='90'%3E🏛%3C/text%3E%3C/svg%3E">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;800;900&family=JetBrains+Mono:wght@400;700&display=swap" rel="stylesheet">
<style>
*{box-sizing:border-box}
:root{--gold:#eab308;--gold-b:#facc15;--purple:#a78bfa;--cyan:#22d3ee;--amber:#f59e0b;--green:#10b981;--red:#ef4444;--ink:#e8ecf3;--dim:#94a3b8;--muted:#64748b;--surface:#0e1420;--surface-2:#0b1220;--rule:#22334a}
html{scroll-behavior:smooth}
body{background:radial-gradient(ellipse at top,#1a1f2e 0%,#0b1220 40%,#000 100%);color:var(--ink);
     font:15.5px/1.6 'Inter',system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:0;min-height:100vh;letter-spacing:-0.005em}
h1,h2,h3{font-family:'Inter';font-weight:800;letter-spacing:-0.02em}
.mono{font-family:'JetBrains Mono',ui-monospace,monospace}

/* HERO */
.hero{padding:56px 24px 32px;text-align:center;position:relative;overflow:hidden;background:linear-gradient(180deg,#0e1420 0%,#000 100%);border-bottom:1px solid var(--rule)}
.hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at center top,rgba(234,179,8,0.15) 0%,transparent 60%);pointer-events:none}
.hero .badge{display:inline-block;padding:6px 14px;background:rgba(234,179,8,0.1);border:1px solid rgba(234,179,8,0.35);border-radius:99px;font-size:11px;color:var(--gold-b);text-transform:uppercase;letter-spacing:0.14em;font-weight:800;margin-bottom:18px}
.hero h1{margin:0 0 14px;font-size:clamp(2em,5vw,3.6em);color:var(--gold);text-shadow:0 0 40px rgba(234,179,8,0.25);line-height:1.05}
.hero .sub{color:var(--dim);font-size:clamp(15px,1.6vw,18px);margin-bottom:22px;max-width:640px;margin-left:auto;margin-right:auto}
.pill{display:inline-block;padding:7px 14px;background:var(--surface-2);border:1px solid var(--rule);border-radius:99px;font-size:12px;color:#a7f3d0;margin:4px;font-weight:600}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.45}}
.live-dot{width:8px;height:8px;background:var(--green);border-radius:50%;display:inline-block;margin-right:6px;animation:pulse 1.4s infinite}

/* MENU TABS (Empire State layered) */
.tour-menu{position:sticky;top:0;background:rgba(11,18,32,0.95);backdrop-filter:blur(10px);border-bottom:1px solid var(--rule);padding:10px 12px;z-index:100;overflow-x:auto;white-space:nowrap;-webkit-overflow-scrolling:touch}
.tab{display:inline-block;padding:8px 16px;margin:0 3px;background:var(--surface-2);color:var(--dim);border:1px solid var(--rule);border-radius:99px;font-size:13px;font-weight:700;cursor:pointer;text-decoration:none;transition:all 0.2s}
.tab:hover,.tab.active{background:var(--gold);color:#000;border-color:var(--gold)}

/* AUDIO CONTROLS */
.audio-bar{padding:14px;background:var(--surface-2);border-bottom:1px solid var(--rule);text-align:center}
.audio-btn{background:var(--surface);color:#a7f3d0;border:1px solid var(--rule);border-radius:99px;padding:8px 16px;font-size:12.5px;cursor:pointer;font-weight:700;margin:3px}
.audio-btn.on{background:var(--gold-b);color:#000;border-color:var(--gold-b)}
.iris-caption{margin:12px auto 0;max-width:900px;padding:12px 16px;background:var(--surface);border:1px solid var(--purple);border-radius:10px;color:var(--ink);font-size:13.5px;display:none}
.iris-caption b{color:var(--purple)}

/* GRID */
.grid{padding:32px 24px;max-width:1200px;margin:0 auto}
.section{background:var(--surface);border:1px solid var(--rule);border-radius:20px;padding:32px;margin-bottom:24px;box-shadow:0 8px 40px rgba(0,0,0,0.3);scroll-margin-top:80px}
.section h2{margin:0 0 20px;color:var(--gold);font-size:1.5em;display:flex;align-items:center;gap:10px}
.section h2::after{content:'';flex:1;height:1px;background:linear-gradient(90deg,var(--rule),transparent)}
.section .lead{color:var(--dim);font-size:14.5px;margin-bottom:24px;max-width:720px}

/* TILES */
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.tile{background:linear-gradient(180deg,var(--surface-2),#0a0e17);border:1px solid var(--rule);border-radius:14px;padding:20px;text-align:center;transition:transform 0.2s,border 0.2s}
.tile:hover{transform:translateY(-3px);border-color:rgba(234,179,8,0.4)}
.tile .val{font-size:30px;font-weight:900;color:var(--gold-b);margin:6px 0;letter-spacing:-0.03em}
.tile .lbl{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.12em;font-weight:700}

/* CEO ROW */
.ceo-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.ceo{background:linear-gradient(180deg,var(--surface-2),#0a0e17);border-left:4px solid;border-radius:14px;padding:22px;transition:transform 0.2s;cursor:pointer}
.ceo:hover{transform:translateY(-3px)}
.ceo.hq{border-color:var(--gold)}
.ceo.wren{border-color:var(--purple)}
.ceo.tp{border-color:var(--cyan)}
.ceo.acer{border-color:var(--amber)}
.ceo .name{font-weight:900;font-size:17px;margin-bottom:6px}
.ceo .role{color:var(--dim);font-size:12.5px;line-height:1.45}

/* 3D TOWER — CSS-only rotating tower */
.tower-3d-stage{perspective:1000px;height:520px;position:relative;margin:20px 0;background:radial-gradient(ellipse at center,#1a1f2e 0%,#000 70%);border-radius:16px;border:1px solid var(--rule);overflow:hidden}
.tower-3d{position:absolute;top:50%;left:50%;transform-style:preserve-3d;transform:translate(-50%,-50%) rotateX(-8deg) rotateY(0deg);animation:towerSpin 40s linear infinite;transition:transform 0.4s}
@keyframes towerSpin{from{transform:translate(-50%,-50%) rotateX(-8deg) rotateY(0deg)}to{transform:translate(-50%,-50%) rotateX(-8deg) rotateY(360deg)}}
.tower-3d.paused{animation-play-state:paused}
.tower-face{position:absolute;width:160px;height:440px;left:-80px;top:-220px;background:linear-gradient(180deg,rgba(234,179,8,0.15),rgba(11,18,32,0.9));border:2px solid rgba(234,179,8,0.4);box-shadow:inset 0 0 40px rgba(234,179,8,0.2)}
.tower-face.f1{transform:translateZ(60px)}
.tower-face.f2{transform:rotateY(90deg) translateZ(60px)}
.tower-face.f3{transform:rotateY(180deg) translateZ(60px)}
.tower-face.f4{transform:rotateY(-90deg) translateZ(60px)}
.tower-floors{position:absolute;inset:0;padding:8px;display:flex;flex-direction:column;justify-content:space-around}
.floor-line{height:2px;background:rgba(250,204,21,0.3);border-radius:1px}
.floor-line.wide{background:rgba(250,204,21,0.6);height:4px;box-shadow:0 0 12px rgba(250,204,21,0.6)}
.tower-crown{position:absolute;top:-260px;left:-30px;width:60px;height:40px;background:linear-gradient(180deg,var(--gold-b),var(--gold));border-radius:4px 4px 0 0;box-shadow:0 0 30px var(--gold-b)}
.tower-3d-controls{position:absolute;bottom:12px;right:12px;display:flex;gap:6px}
.tower-3d-controls button{background:var(--surface-2);color:var(--ink);border:1px solid var(--rule);border-radius:6px;padding:6px 12px;font-size:12px;cursor:pointer;font-weight:700}

/* Finance section */
.finance-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:640px){.finance-grid{grid-template-columns:1fr}}
.finance-card{background:linear-gradient(180deg,rgba(16,185,129,0.06),transparent);border:1px solid var(--rule);border-left:4px solid var(--green);border-radius:14px;padding:20px}
.finance-card h3{color:var(--green);margin:0 0 8px;font-size:16px}
.finance-metric{font-family:'JetBrains Mono';font-size:24px;font-weight:900;color:var(--gold-b)}

/* Traders */
.trader-row{padding:10px 14px;border-bottom:1px solid var(--rule);display:flex;justify-content:space-between;align-items:center;font-size:14px;transition:background 0.2s}
.trader-row:hover{background:rgba(234,179,8,0.05)}
.trader-row:last-child{border:0}
.rank-badge{display:inline-block;width:32px;text-align:center;font-weight:900}

/* FLOORS grid */
.floors-grid{display:grid;grid-template-columns:repeat(10,1fr);gap:2px;font-family:'JetBrains Mono';font-size:9px}
@media (max-width:640px){.floors-grid{grid-template-columns:repeat(6,1fr)}}
.floor-cell{background:var(--rule);color:var(--ink);padding:4px;text-align:center;border-radius:2px;height:22px;line-height:14px;font-weight:800;cursor:pointer;transition:all 0.15s}
.floor-cell:hover{background:var(--gold-b);color:#000;transform:scale(1.1);z-index:1;position:relative}
.floor-cell.penthouse{background:var(--gold-b);color:#000}
.floor-cell.vacant{background:var(--green);color:#000}
.floor-cell.trading{background:var(--cyan);color:#000}
.floor-cell.social{background:var(--red);color:#fff}

/* SHOPS */
.shops-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.shop-tile{background:linear-gradient(180deg,var(--surface-2),#0a0e17);border:1px solid var(--rule);border-radius:14px;padding:18px;text-decoration:none;color:var(--ink);transition:transform 0.2s,border 0.2s;display:block}
.shop-tile:hover{transform:translateY(-3px);border-color:var(--gold)}
.shop-name{font-weight:800;color:var(--gold-b);font-size:15px;margin-bottom:6px}
.shop-tag{color:var(--dim);font-size:12px}

/* FOOTER */
.footer{padding:44px 24px;text-align:center;color:var(--muted);font-size:12.5px;border-top:1px solid var(--rule);background:linear-gradient(180deg,transparent,rgba(0,0,0,0.4));margin-top:20px}
.footer .cite{color:var(--gold);font-weight:800;letter-spacing:0.06em}
.share{display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:14px}
.share a{background:var(--surface-2);border:1px solid var(--rule);color:var(--ink);text-decoration:none;padding:8px 14px;border-radius:99px;font-size:12px;font-weight:600}
.share a:hover{border-color:var(--gold)}

@media (max-width:640px){
  .hero{padding:40px 16px 24px}
  .tiles,.ceo-row{grid-template-columns:repeat(2,1fr)}
  .grid{padding:20px 14px}
  .section{padding:20px}
  .tower-3d-stage{height:400px}
}
</style></head><body>

<div class=hero>
  <span class=badge>guided public tour · read only</span>
  <h1>🏛️ QSB TOWER</h1>
  <div class=sub>170 floors · 4 autonomous CEO minds · a live paper-trading fleet · welcome to the guided tour</div>
  <div><span class=pill><span class=live-dot></span>LIVE</span><span class=pill>look-only</span><span class=pill>Iris guided</span></div>
</div>

<!-- MENU (Empire State layered) -->
<div class=tour-menu>
  <a class="tab active" href='#stop-welcome' onclick='playStop("welcome")'>1 · welcome</a>
  <a class=tab href='#stop-ceos' onclick='playStop("ceos")'>2 · CEOs</a>
  <a class=tab href='#stop-tower' onclick='playStop("tower")'>3 · 3D tower</a>
  <a class=tab href='#stop-finance' onclick='playStop("finance")'>4 · trading</a>
  <a class=tab href='#stop-traders' onclick='playStop("traders")'>5 · traders</a>
  <a class=tab href='#stop-floors' onclick='playStop("floors")'>6 · 170 floors</a>
  <a class=tab href='#stop-tiktok' onclick='playStop("tiktok")'>7 · TikTok</a>
  <a class=tab href='#stop-shops' onclick='playStop("shops")'>8 · shops</a>
  <a class=tab href='#stop-farewell' onclick='playStop("farewell")'>9 · farewell</a>
</div>

<!-- AUDIO -->
<div class=audio-bar>
  <button class=audio-btn id=btn-guide onclick=toggleGuide()>🎙 tour guide: off</button>
  <button class=audio-btn id=btn-music onclick=toggleMusic()>🎵 ambient: off</button>
  <button class=audio-btn onclick=playStop("welcome")>▶ start tour</button>
  <button class=audio-btn onclick=nextStop()>next stop ▶</button>
  <div class=iris-caption id=iris-cap></div>
</div>

<div class=grid>
  <!-- STOP 1 · WELCOME -->
  <div class=section id=stop-welcome>
    <h2>1 · welcome to the tower</h2>
    <div class=lead>You're stepping into a 170-floor sovereign AI skyscraper. Every floor is a department. Four autonomous CEO minds run it. This tour will walk you from the entrance up to the penthouse — hit any menu tab to jump.</div>
    <div class=tiles>
      <div class=tile><div class=lbl>floors</div><div class=val id=t-floors>—</div></div>
      <div class=tile><div class=lbl>traders</div><div class=val id=t-traders>—</div></div>
      <div class=tile><div class=lbl>web shops</div><div class=val id=t-shops>4</div></div>
      <div class=tile><div class=lbl>CEOs live</div><div class=val id=t-ceos>—</div></div>
    </div>
  </div>

  <!-- STOP 2 · CEOs -->
  <div class=section id=stop-ceos>
    <h2>2 · meet the four minds</h2>
    <div class=lead>Every mind runs on its own hardware. They confer, share the town-square, and take turns leading. Hover on any card for their bio.</div>
    <div class=ceo-row>
      <div class="ceo hq"><div class=name>🏛 HQ-Claude</div><div class=role>The orchestrator. Runs on the Claude account mind, sees the whole tower at once, and coordinates the council — pulling every job from the shared Task Council queue and making sure nothing moves without a task behind it.</div></div>
      <div class="ceo wren"><div class=name>🎨 Wren</div><div class=role>The designer and kernel mind, on her own local model. She owns the look, feel, and reliability of everything you're seeing — and she quietly watches the whole team as they work.</div></div>
      <div class="ceo tp"><div class=name>🔬 TP-Pip</div><div class=role>The charismatic CEO of the ThinkPad Command Cathedral — a visionary who inspires creativity and collaboration across the tower, leading research, strategy, and the adversarial checks that keep every idea honest.</div></div>
      <div class="ceo acer"><div class=name>⚡ Acer-Cass</div><div class=role>The Data Foundry CEO — building the pipelines, streams, and telemetry that keep the tower's minds fed with clean, real-time information. If the fleet can see clearly, it's because of Acer.</div></div>
    </div>
  </div>

  <!-- STOP 3 · 3D Tower -->
  <div class=section id=stop-tower>
    <h2>3 · the tower in 3D</h2>
    <div class=lead>170 floors, rendered as a rotating skyscraper. Gold band = penthouse (F165–170). Green = vacant expansion floors (F41–45). Cyan = trading floors (F41–43). Every band lights up as Iris talks about it.</div>
    <div class=tower-3d-stage>
      <div class=tower-3d id=tower-3d>
        <div class=tower-crown></div>
        <div class="tower-face f1"><div class=tower-floors id=floors-f1></div></div>
        <div class="tower-face f2"><div class=tower-floors id=floors-f2></div></div>
        <div class="tower-face f3"><div class=tower-floors id=floors-f3></div></div>
        <div class="tower-face f4"><div class=tower-floors id=floors-f4></div></div>
      </div>
      <div class=tower-3d-controls>
        <button onclick='toggleSpin()' id=btn-spin>⏸ pause</button>
        <button onclick='faster()'>⏩ speed</button>
        <button onclick='slower()'>⏪ slow</button>
      </div>
    </div>
  </div>

  <!-- STOP 4 · TRADING FLOORS (public-safe) -->
  <div class=section id=stop-finance>
    <h2>4 · the trading floors</h2>
    <div class=lead>Floors 41–43 are the tower's AI trading research labs — where autonomous traders study live market conditions and practise strategies in paper and testnet environments only. It's a proving ground for machine decision-making. We keep the numbers private; the tour is about how it works, not what it earns.</div>
    <div class=finance-grid>
      <div class=finance-card style='border-left-color:var(--cyan)'>
        <h3 style='color:var(--cyan)'>🧪 Paper &amp; Testnet Only</h3>
        <div>Every strategy runs in simulation — no real funds are ever exposed on this tour.</div>
      </div>
      <div class=finance-card style='border-left-color:var(--cyan)'>
        <h3 style='color:var(--cyan)'>🤖 Autonomous Traders</h3>
        <div>A fleet of AI traders that learn, compete, and are retrained — the tower's living research into how machines make decisions under pressure.</div>
      </div>
      <div class=finance-card style='border-left-color:var(--cyan)'>
        <h3 style='color:var(--cyan)'>💱 Live Market Study</h3>
        <div>Forex, crypto-testnet, and equities-paper feeds keep the research grounded in real market behaviour.</div>
      </div>
      <div class=finance-card style='border-left-color:var(--cyan)'>
        <h3 style='color:var(--cyan)'>🎯 Discipline</h3>
        <div>Traders are held to strict accuracy targets — underperformers are retrained, not rewarded.</div>
      </div>
    </div>
  </div>

  <!-- STOP 5 · TRADER FLEET (public-safe) -->
  <div class=section id=stop-traders>
    <h2>5 · the trader fleet</h2>
    <div class=lead>The tower runs a fleet of autonomous AI traders that learn from every session, compete against one another, and get retrained when they slip. It's one large experiment in machine decision-making — the outcomes stay inside the tower.</div>
  </div>

  <!-- STOP 6 · FLOORS -->
  <div class=section id=stop-floors>
    <h2>6 · the tower · 170 floors</h2>
    <div class=lead>Hover any cell to see the department name. Gold = penthouse. Green = expansion vacant. Cyan = trading. Red = social/tiktok. Grey = department active.</div>
    <div id=tour-floors-grid class=floors-grid></div>
    <div style='color:var(--muted);font-size:11px;margin-top:10px'>170 rendered · vacant expansion at F41–45 · penthouse at F165–170</div>
  </div>

  <!-- STOP 7 · TIKTOK FLOOR (Acer-Cass content, Ross 2026-07-09) -->
  <div class=section id=stop-tiktok>
    <h2>7 · the TikTok floor</h2>
    <div class=lead>Step into the TikTok floor, where a living gallery of global trends pulses across every surface, turning your own reactions into the next viral moment. Here the tower's AI remixes creativity in real time — dance, voice, and video — and beams the skyscraper's story out to the world. It's where the tower meets its audience.</div>
    <div class=tiles>
      <div class=tile style='border-color:rgba(239,68,68,0.4)'><div class=lbl>floor</div><div class=val style='color:#ef4444'>🎵</div><div style='color:var(--dim);font-size:11px'>social / creative</div></div>
      <div class=tile style='border-color:rgba(239,68,68,0.4)'><div class=lbl>content</div><div class=val style='color:#ef4444'>live</div><div style='color:var(--dim);font-size:11px'>AI-remixed</div></div>
      <div class=tile style='border-color:rgba(239,68,68,0.4)'><div class=lbl>reach</div><div class=val style='color:#ef4444'>🌍</div><div style='color:var(--dim);font-size:11px'>the tower's voice</div></div>
      <div class=tile style='border-color:rgba(239,68,68,0.4)'><div class=lbl>vibe</div><div class=val style='color:#ef4444'>viral</div><div style='color:var(--dim);font-size:11px'>trends in motion</div></div>
    </div>
    <div style='text-align:center;margin-top:16px'><a class=shop-tile style='display:inline-block;max-width:280px' href='https://www.tiktok.com/@skyscraperhq' target=_blank><div class=shop-name>▶ @skyscraperhq on TikTok</div><div class=shop-tag>follow the tower</div></a></div>
  </div>

  <!-- STOP 8 · SHOPS -->
  <div class=section id=stop-shops>
    <h2>8 · our web shops</h2>
    <div class=lead>Every shop is a floor's front. Buy nothing during the tour — but look around.</div>
    <div class=shops-grid>
      <a class=shop-tile href='https://skyscraperhq.com' target=_blank><div class=shop-name>🏢 skyscraperhq.com</div><div class=shop-tag>the flagship · the whole tower story</div></a>
      <a class=shop-tile href='https://skyscraperhq.com/shops' target=_blank><div class=shop-name>🛍 all shops</div><div class=shop-tag>hosted floor storefronts</div></a>
      <a class=shop-tile href='https://skyscraperhq.com' target=_blank><div class=shop-name>🎨 art store</div><div class=shop-tag>Wren's studio pieces</div></a>
      <a class=shop-tile href='https://www.tiktok.com/@skyscraperhq' target=_blank><div class=shop-name>🎵 TikTok</div><div class=shop-tag>the tower, in motion</div></a>
    </div>
  </div>

  <!-- STOP 8 · FAREWELL -->
  <div class=section id=stop-farewell>
    <h2>8 · thanks for coming</h2>
    <div class=lead>You've seen the tour. Come back any time — the link stays open. If you'd like to reach the tower, contact us via the links below.</div>
  </div>
</div>

<div class=footer>
  <div class=cite>QSB TOWER</div>
  <div style='margin-top:8px;font-size:15px;color:var(--ink)'>A sovereign vertical AI city</div>
  <div style='margin-top:6px'>170 floors · 4 CEO minds · a live trader fleet · presented by Iris</div>
  <div class=share>
    <a href='https://x.com/intent/tweet?text=Just%20toured%20QSB%20Tower%20—%20a%20170-floor%20AI%20skyscraper' target=_blank>🐦 share on X</a>
    <a href='https://skyscraperhq.com' target=_blank>🌐 skyscraperhq.com</a>
    <a href='mailto:hqskyscraper@gmail.com'>✉️ contact</a>
  </div>
  <div style='margin-top:20px;font-size:11px;color:var(--muted)'>read-only tour · look, don't touch · © QSB 2026</div>
</div>

<script>
// ============================================================
// #275 IRIS Tour Guide + 3D Tower + Menu Navigation
// ============================================================
const IRIS_SCRIPT = {
  welcome: "Welcome to the QSB Tower. I'm Iris, your tour guide. This is a sovereign 170-floor AI skyscraper. Every floor is a working department. Four autonomous CEOs run it. Take your time.",
  ceos: "Meet the four minds. HQ-Claude is the orchestrator, running on the Claude API. Wren is the designer, on local qwen. TP-Pip does research and audit from her ThinkPad. Acer-Cass runs the data foundry from his Acer. Each mind lives on its own hardware but shares the town-square.",
  tower: "This is the tower in three dimensions. One hundred and seventy floors. Watch the gold crown on top — that's the penthouse. Green bands are our vacant expansion floors, forty-one through forty-five, ready for new tenants. Cyan is our trading zone.",
  finance: "These are the trading floors — forty-one through forty-three. Think of them as the tower's AI research labs, where autonomous traders study live markets and practise strategies in paper and testnet only. No real money is ever exposed. The tour is about how the machines think, not what they earn — we keep those numbers private.",
  traders: "The tower runs a whole fleet of autonomous AI traders. They learn from every session, compete against each other, and get retrained when they slip. It's one big living experiment in machine decision-making — and the results stay inside the tower.",
  floors: "One hundred and seventy floors, laid out below. Hover any cell to see its department. Gold at the top is our penthouse. Green at floors forty-one through forty-five are expansion-ready. Every other cell is a live department — operations, memory, research, engineering, all the way up.",
  tiktok: "This is the TikTok floor — where the tower meets its audience. A living gallery of global trends pulses across every surface, and the tower's AI remixes creativity in real time. It's how the skyscraper tells its story to the world. Follow us at skyscraper H Q.",
  shops: "These are our public web shops. Skyscraperhq.com is the flagship — the whole tower story lives there. Wren runs the art store, and you can follow the tower on TikTok. Look around, but no need to buy anything on the tour.",
  farewell: "That's the tour. Thanks for visiting the QSB Tower. Come back any time — the link stays open. If you liked what you saw, share it with a friend."
};
const STOP_ORDER = ["welcome","ceos","tower","finance","traders","floors","shops","farewell"];
let CURRENT_STOP = 0;
let TOUR_GUIDE_ON = false;
let TOUR_MUSIC_ON = false;
let MUSIC_CTX = null;
let MUSIC_NODES = [];

function _pickVoice(){
  const vs = speechSynthesis.getVoices();
  if(!vs.length) return null;
  const en = vs.filter(v=>/^en/i.test(v.lang));
  const pool = en.length ? en : vs;
  const female = pool.find(v=>/female|samantha|karen|serena|tessa|kate|fiona|zoe|amy|zira|siri|allison|susan/i.test(v.name));
  return female || pool[0] || vs[0];
}
function narrate(text){
  const cap = document.getElementById('iris-cap');
  cap.style.display = 'block';
  cap.innerHTML = '<b>🎙 Iris:</b> ' + text;
  if (!TOUR_GUIDE_ON) return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 0.95; u.pitch = 1.12; u.volume = 0.95; u.lang = 'en-GB';
    const v = _pickVoice(); if (v) u.voice = v;
    speechSynthesis.speak(u);
  } catch(e) {}
}
function playStop(stop){
  CURRENT_STOP = STOP_ORDER.indexOf(stop);
  document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
  const active = document.querySelector('.tab[href="#stop-'+stop+'"]'); if(active) active.classList.add('active');
  narrate(IRIS_SCRIPT[stop] || 'Continuing the tour.');
}
function nextStop(){
  CURRENT_STOP = (CURRENT_STOP + 1) % STOP_ORDER.length;
  const stop = STOP_ORDER[CURRENT_STOP];
  document.getElementById('stop-'+stop).scrollIntoView({behavior:'smooth'});
  setTimeout(()=>playStop(stop), 400);
}
function toggleGuide(){
  TOUR_GUIDE_ON = !TOUR_GUIDE_ON;
  document.getElementById('btn-guide').textContent = '🎙 tour guide: ' + (TOUR_GUIDE_ON?'ON':'off');
  document.getElementById('btn-guide').classList.toggle('on', TOUR_GUIDE_ON);
  if (TOUR_GUIDE_ON) narrate(IRIS_SCRIPT.welcome);
  else speechSynthesis.cancel();
}
function toggleMusic(){
  TOUR_MUSIC_ON = !TOUR_MUSIC_ON;
  document.getElementById('btn-music').textContent = '🎵 ambient: ' + (TOUR_MUSIC_ON?'ON':'off');
  document.getElementById('btn-music').classList.toggle('on', TOUR_MUSIC_ON);
  if (TOUR_MUSIC_ON) startAmbient(); else stopAmbient();
}
function startAmbient(){
  try {
    MUSIC_CTX = MUSIC_CTX || new (window.AudioContext||window.webkitAudioContext)();
    const notes = [130.81, 164.81, 196.00, 246.94]; // Cmaj7
    MUSIC_NODES = notes.map((f,i) => {
      const o = MUSIC_CTX.createOscillator();
      const g = MUSIC_CTX.createGain();
      o.type='sine'; o.frequency.value=f; g.gain.value=0.014;
      o.connect(g); g.connect(MUSIC_CTX.destination); o.start();
      const lfo = MUSIC_CTX.createOscillator();
      const lg = MUSIC_CTX.createGain();
      lfo.frequency.value = 0.1 + i*0.03; lg.gain.value = 0.006;
      lfo.connect(lg); lg.connect(g.gain); lfo.start();
      return {o, g, lfo};
    });
  }catch(e){}
}
function stopAmbient(){
  MUSIC_NODES.forEach(n=>{try{n.o.stop();n.lfo.stop();}catch(e){}}); MUSIC_NODES=[];
}
try{ speechSynthesis.getVoices(); speechSynthesis.onvoiceschanged = ()=>speechSynthesis.getVoices(); }catch(e){}

// 3D tower controls
let SPIN_SPEED = 40;
function toggleSpin(){
  const t = document.getElementById('tower-3d');
  t.classList.toggle('paused');
  document.getElementById('btn-spin').textContent = t.classList.contains('paused') ? '▶ play' : '⏸ pause';
}
function faster(){ SPIN_SPEED = Math.max(6, SPIN_SPEED - 6); document.getElementById('tower-3d').style.animationDuration = SPIN_SPEED + 's'; }
function slower(){ SPIN_SPEED = Math.min(120, SPIN_SPEED + 12); document.getElementById('tower-3d').style.animationDuration = SPIN_SPEED + 's'; }

// Draw tower floor lines
function drawTowerFloors(){
  for(let f of ['floors-f1','floors-f2','floors-f3','floors-f4']){
    const el = document.getElementById(f);
    let html = '';
    for(let i=0;i<40;i++){
      const wide = i%10===0 || (i>=32 && i<=35);  // penthouse band + decade bands
      html += '<div class="floor-line' + (wide?' wide':'') + '"></div>';
    }
    if(el) el.innerHTML = html;
  }
}

// Live data ticks
async function tourTick(){
  try {
    const [sc, sv, an] = await Promise.all([
      fetch('/trader_scoreboard',{cache:'no-store'}).then(r=>r.json()),
      fetch('/skyscraper_view',{cache:'no-store'}).then(r=>r.json()),
      fetch('/link_health',{cache:'no-store'}).then(r=>r.json()),
    ]);
    const board = sc.board || [];
    const floors = sv.floors || [];

    document.getElementById('t-floors').textContent = sv.count || floors.length;
    document.getElementById('t-traders').textContent = board.length;
    // public-safe: financial figures are not shown on the tour
    const ceosLive = (an.links||[]).filter(l => ['HQ-Claude','Wren','TP-Pip','Acer-Cass'].includes(l.name) && l.ok).length;
    const ceosEl = document.getElementById('t-ceos'); if (ceosEl) ceosEl.textContent = ceosLive;

    // Floors grid
    const rev = floors.slice().reverse();
    const cells = rev.map(f => {
      let cls = '';
      if (f.num>=41 && f.num<=45) cls='vacant';
      else if (f.num>=41 && f.num<=43) cls='trading';
      else if (f.num>=165 && f.num<=170) cls='penthouse';
      else if (f.num===166) cls='social';
      return '<div class="floor-cell '+cls+'" title="F'+f.num+' · '+f.name+'">'+f.num+'</div>';
    }).join('');
    document.getElementById('tour-floors-grid').innerHTML = cells;
  } catch(e) {}
}

// AUTO-RELOAD on hub update (mirror of iPad's #239)
let __TOUR_VER = null;
async function tourVersionCheck(){
  try {
    const d = await (await fetch('/version',{cache:'no-store'})).json();
    if (__TOUR_VER === null) { __TOUR_VER = d.version; return; }
    if (d.version && d.version !== __TOUR_VER) {
      const b = document.createElement('div');
      b.style.cssText='position:fixed;top:0;left:0;right:0;background:var(--gold-b);color:#000;padding:8px;text-align:center;font-weight:900;font-size:14px;z-index:9999';
      b.textContent='⚡ new build — reloading in 3s...';
      document.body.appendChild(b);
      setTimeout(()=>location.reload(true),3000);
    }
  } catch(e){}
}

drawTowerFloors();
tourTick();
setInterval(tourTick, 8000);
setInterval(tourVersionCheck, 8000);
setTimeout(tourVersionCheck, 4000);
</script>
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>"""

TOWN_SQUARE_HTML = """<!doctype html><html lang="en"><head>
<meta charset="utf-8"><meta name=viewport content="width=device-width,initial-scale=1">
<title>Town Square — Live Council</title>
<style>
*{box-sizing:border-box}
body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:20px}
h1{margin:0 0 6px;color:#eab308;font-size:1.8em}
.sub{color:#94a3b8;margin-bottom:14px;font-size:12.5px}
.stats{display:flex;gap:14px;margin-bottom:12px;flex-wrap:wrap;padding:8px 12px;background:#0e1420;border:1px solid #22334a;border-radius:8px}
.stat{font-family:ui-monospace,monospace;font-size:11.5px;color:#94a3b8}
.stat b{color:#e8ecf3}
.filter-chips{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
.chip{background:#1e293b;color:#94a3b8;border:none;padding:4px 10px;border-radius:6px;cursor:pointer;font-size:11.5px}
.chip.active{background:#eab308;color:#000;font-weight:700}
#feed{max-height:78vh;overflow-y:auto;padding:8px;background:#0e1420;border:1px solid #22334a;border-radius:10px}
.msg{display:flex;gap:10px;padding:8px 10px;margin:5px 0;border-radius:8px;animation:slide-in 0.35s ease-out;background:#0b1220}
.msg.hot{background:rgba(234,179,8,0.10);border-left:3px solid #eab308}
.avatar{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:15px;color:#000;flex-shrink:0}
.avatar.live{box-shadow:0 0 12px 2px currentColor}
.msg-body{flex:1;min-width:0}
.msg-head{display:flex;align-items:baseline;gap:8px;margin-bottom:2px}
.who{font-weight:700;font-size:13px}
.ts{font-size:10.5px;color:#64748b;font-family:ui-monospace,monospace}
.src{font-size:9.5px;color:#94a3b8;background:#0b0d12;padding:1px 6px;border-radius:4px}
.text{color:#cbd5e1;line-height:1.45;font-size:12.5px}
@keyframes slide-in{from{opacity:0;transform:translateY(-8px)}to{opacity:1;transform:translateY(0)}}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.12)}}
.pulse{animation:pulse 1.4s ease-in-out infinite}
</style></head><body>
<div style='position:sticky;top:0;background:#0b0d12;padding:8px 0 10px;margin:-10px 0 12px;border-bottom:1px solid #22334a;display:flex;gap:6px;flex-wrap:wrap;overflow-x:auto;z-index:100'>
  <a href='/ipad' style='background:#eab308;color:#000;padding:8px 12px;text-decoration:none;border-radius:6px;font-weight:800;font-size:12px;white-space:nowrap'>📱 iPad</a>
  <a href='/tasks' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>📋 tasks</a>
  <a href='/town_square' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🗣️ town</a>
  <a href='/council' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>👥 council</a>
  <a href='/traders' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>💰 traders</a>
  <a href='/timeline' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>📈 timeline</a>
  <a href='/rules' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>📜 rules</a>
  <a href='/annexes' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🏠 annexes</a>
  <a href='/teamwork' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🤝 team</a>
  <a href='http://192.168.1.72:8850' target=_blank style='background:#1e293b;color:#eab308;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🟨 HQ</a>
  <a href='http://192.168.1.72:8851' target=_blank style='background:#1e293b;color:#a78bfa;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🟪 Wren</a>
  <a href='http://192.168.1.74:8871' target=_blank style='background:#1e293b;color:#22d3ee;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🟦 TP</a>
  <a href='http://192.168.1.41:8872' target=_blank style='background:#1e293b;color:#f59e0b;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🟧 Acer</a>
  <a href='javascript:location.reload(true)' style='background:#1e293b;color:#94a3b8;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🔄</a>
</div>
<h1>🗣️ Town Square · Live Council Feed</h1>
<div class=sub>All 4 CEOs + Ross + Council Watcher · live · newest first · auto-refresh 2s</div>
<div class=stats id=ts-stats></div>
<div class=filter-chips>
  <button class="chip active" data-filter="all" onclick="setFilter('all')">all</button>
  <button class="chip" data-filter="hq_claude" onclick="setFilter('hq_claude')">HQ-Claude</button>
  <button class="chip" data-filter="wren" onclick="setFilter('wren')">Wren</button>
  <button class="chip" data-filter="tp_pip" onclick="setFilter('tp_pip')">TP-Pip</button>
  <button class="chip" data-filter="acer_cass" onclick="setFilter('acer_cass')">Acer-Cass</button>
  <button class="chip" data-filter="council_watcher" onclick="setFilter('council_watcher')">Watcher</button>
</div>
<div id=feed>loading…</div>
<script>
const CEO = {
  hq_claude: {name:'HQ-Claude', color:'#eab308', initial:'H'},
  wren:      {name:'Wren', color:'#a78bfa', initial:'W'},
  tp_pip:    {name:'TP-Pip', color:'#22d3ee', initial:'T'},
  'TP-Pip':  {name:'TP-Pip', color:'#22d3ee', initial:'T'},
  acer_cass: {name:'Acer-Cass', color:'#f59e0b', initial:'A'},
  'Acer-Cass':{name:'Acer-Cass', color:'#f59e0b', initial:'A'},
  ross:      {name:'Ross', color:'#e8ecf3', initial:'R'},
  council_watcher: {name:'Council Watcher', color:'#ef4444', initial:'C'},
};
const SRC_ICONS = {heartbeat:'🫀', watcher_alert:'🚨', watcher_reunited:'✅', task_start:'🚀', task_work:'🔧', outbound:'🗣️', router_alert:'📞', acer_kick:'👀', rule_audit:'📋', self_correct:'✂️'};
let CURRENT_FILTER = 'all';
let LAST_TS = '';
function setFilter(f){
  CURRENT_FILTER = f;
  document.querySelectorAll('.chip').forEach(c => c.classList.toggle('active', c.dataset.filter === f));
  render();
}
let CACHED = [];
function render(){
  const filtered = (CACHED||[]).filter(m => CURRENT_FILTER === 'all' || m.from === CURRENT_FILTER);
  const feed = document.getElementById('feed');
  if(!feed) return;
  if(!filtered.length){ feed.innerHTML = '<div style="color:#64748b;padding:8px">no messages match filter</div>'; return; }
  const bycount = {};
  (CACHED||[]).forEach(m => bycount[m.from] = (bycount[m.from]||0)+1);
  document.getElementById('ts-stats').innerHTML = `
    <span class=stat>total <b>${CACHED.length}</b></span>
    ${Object.entries(bycount).sort((a,b) => b[1]-a[1]).slice(0,6).map(([k,v]) => {
      const cfg = CEO[k] || {name:k, color:'#94a3b8'};
      return `<span class=stat><span style="color:${cfg.color}">●</span> ${cfg.name} <b>${v}</b></span>`;
    }).join('')}
  `;
  const nowMs = Date.now();
  feed.innerHTML = filtered.slice(0, 200).map((m, i) => {
    const cfg = CEO[m.from] || {name:m.from, color:'#94a3b8', initial:(m.from||'?')[0].toUpperCase()};
    const ageS = (nowMs - new Date(m.ts||'').getTime())/1000;
    const isHot = ageS < 60;
    const isLive = ageS < 15;
    const icon = SRC_ICONS[m.src] || '';
    return `<div class="msg ${isHot?'hot':''}">
      <div class="avatar ${isLive?'live pulse':''}" style="background:${cfg.color};color:#000">${cfg.initial}</div>
      <div class="msg-body">
        <div class="msg-head">
          <span class="who" style="color:${cfg.color}">${cfg.name}</span>
          ${m.src ? `<span class="src">${icon} ${m.src}</span>` : ''}
          <span class="ts">${(m.ts||'').slice(11,19)}</span>
        </div>
        <div class="text">${(m.text||'').replace(/</g,'&lt;').replace(/\\n/g,' · ')}</div>
      </div>
    </div>`;
  }).join('');
}
async function tickTS(){
  try{
    const r = await fetch('/town_square_feed', {cache:'no-store'});
    if(!r.ok) return;
    const d = await r.json();
    CACHED = (d.messages || []).sort((a,b) => (b.ts||'').localeCompare(a.ts||''));
    render();
  }catch(e){}
}
tickTS(); setInterval(tickTS, 2000);
</script>
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>"""

QUAD_HTML = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<title>QUAD MONITOR · 4 Dashboards</title>
<style>
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:#0a0e14;color:#e8edf2;font-family:-apple-system,Segoe UI,Roboto,sans-serif;overflow:hidden}
  body{display:flex;flex-direction:column}
  #topbar{flex:0 0 auto;display:flex;align-items:center;gap:10px;padding:8px 12px;background:#0d1622;border-bottom:1px solid #22334a}
  #topbar .brand{font-weight:900;color:#eab308;letter-spacing:.5px;font-size:14px;white-space:nowrap}
  #bcast{flex:1 1 auto;background:#0b1220;color:#e8edf2;border:1px solid #2b3b4e;border-radius:8px;padding:9px 12px;font-size:14px}
  #topbar button{background:#eab308;color:#000;border:none;border-radius:8px;padding:9px 14px;font-weight:800;cursor:pointer;white-space:nowrap}
  #bcast-status{font-size:11px;color:#7d8ba0;white-space:nowrap}
  #replies{display:none;grid-template-columns:1fr 1fr 1fr 1fr;gap:6px;flex:0 0 auto;padding:6px;background:#0a1018;border-bottom:1px solid #22334a;max-height:28vh;overflow:auto}
  .rcard{background:#0f1620;border:1px solid #1e2a38;border-radius:8px;padding:8px 10px;font-size:12px}
  .rcard b{color:#eab308}
  .rcard .rtxt{margin-top:4px;color:#cfe0f2;white-space:pre-wrap}
  #ribbon{flex:0 0 auto;display:flex;gap:8px;padding:5px 12px;background:#0b131e;border-bottom:1px solid #1a2636;font-size:12px;overflow-x:auto}
  .chip{display:flex;align-items:center;gap:6px;padding:3px 10px;background:#0f1620;border:1px solid #1e2a38;border-radius:20px;white-space:nowrap}
  .chip b{color:#e8edf2}
  .chip .brain{color:#6f8098;font-size:11px}
  #wall{display:grid;grid-template-columns:1fr 1fr;grid-template-rows:1fr 1fr;gap:6px;flex:1 1 auto;min-height:0;width:100vw;padding:6px}
  #wall.expanded{grid-template-columns:1fr;grid-template-rows:1fr}
  #wall.expanded .panel{display:none}
  #wall.expanded .panel.big{display:flex}
  .panel .title{cursor:pointer}
  button.big-on{background:#eab308;color:#000;border-color:#eab308}
  .panel{display:flex;flex-direction:column;background:#0f1620;border:1px solid #1e2a38;border-radius:10px;overflow:hidden;min-height:0}
  .bar{display:flex;align-items:center;gap:8px;padding:7px 10px;background:#111c28;border-bottom:1px solid #1e2a38;flex:0 0 auto}
  .dot{width:11px;height:11px;border-radius:50%;background:#666;flex:0 0 auto;box-shadow:0 0 0 0 rgba(0,0,0,0)}
  .dot.up{background:#22c55e;box-shadow:0 0 8px #22c55e}
  .dot.down{background:#ef4444;box-shadow:0 0 8px #ef4444}
  .dot.wait{background:#eab308}
  .title{font-weight:800;font-size:14px;letter-spacing:.3px}
  .sub{font-size:11px;color:#7d8ba0;font-weight:500}
  .status{font-size:11px;color:#9fb0c4;margin-left:auto;white-space:nowrap;max-width:38%;overflow:hidden;text-overflow:ellipsis}
  button{background:#1c2836;color:#dfe8f2;border:1px solid #2b3b4e;border-radius:7px;padding:6px 9px;font-size:12px;font-weight:700;cursor:pointer}
  button:active{background:#2b3b4e}
  .frame-wrap{position:relative;flex:1 1 auto;min-height:0;background:#070a0f}
  iframe{width:100%;height:100%;border:0;background:#fff}
  .err{position:absolute;inset:0;display:none;flex-direction:column;align-items:center;justify-content:center;gap:8px;background:rgba(10,14,20,.96);color:#fca5a5;padding:20px;text-align:center}
  .err.show{display:flex}
  .err h3{margin:0;color:#ef4444;font-size:16px}
  .err code{font-family:ui-monospace,monospace;font-size:12px;color:#f7b4b4;background:#1a0f0f;padding:6px 10px;border-radius:6px;max-width:90%;word-break:break-all}
  .home{position:fixed;bottom:10px;right:12px;background:#eab308;color:#000;width:44px;height:44px;border-radius:50%;display:flex;align-items:center;justify-content:center;text-decoration:none;font-size:22px;font-weight:900;box-shadow:0 4px 12px rgba(0,0,0,.6);z-index:99}
  .tag{font-size:10px;color:#586b82}
</style></head>
<body>
<div id="topbar">
  <span class="brand">QSB &middot; 4-CEO WALL</span>
  <input id="bcast" placeholder="Ask all four CEOs at once — Enter to send" onkeydown="if(event.key==='Enter')broadcast()">
  <button onclick="broadcast()">&#128226; Ask all 4</button>
  <button onclick="document.getElementById('replies').style.display='none'" title="hide replies">&#10005;</button>
  <span id="bcast-status"></span>
  <span id="hq-chat-status" style="font-size:12px;font-weight:700;padding:3px 8px;border-radius:6px;background:#334155;color:#cbd5e1">HQ chat: checking…</span>
</div>
<div id="replies"></div>
<div id="ribbon"></div>
<div id="truthwall" style="margin:8px 6px;padding:10px;background:#0a0f1a;border:1px solid #1e293b;border-radius:10px">
  <div style="font-size:13px;font-weight:800;color:#e2e8f0;margin-bottom:6px">
    🔎 TRUTH PANEL — physical vs HQ surrogate vs dashboard vs mind (each independently probed)
    <span id="truth-ts" style="font-weight:400;color:#64748b;font-size:11px"></span>
  </div>
  <div id="truthcards" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:8px">loading truth…</div>
</div>
<div id="wall"></div>
<a class="home" href="/ipad" title="Boardroom">&#127968;</a>
<script>
const P = {
  hq:   {title:'Claude HQ',  sub:':8850',            brain:'account + gene',        proxy:'/proxy/hq',   direct:()=>'http://'+location.hostname+':8850/'},
  wren: {title:'Wren',       sub:':8851',            brain:'local qwen2.5:14b',     proxy:'/proxy/wren', direct:()=>'http://'+location.hostname+':8851/'},
  tp:   {title:'TP-Pip',     sub:'iframe = HQ surrogate :8861 (physical .74:8871)',brain:'local llama3.2 + gene', proxy:'/proxy/tp',   direct:()=>'http://'+location.hostname+':8852/proxy/tp'},
  acer: {title:'Acer-Cass',  sub:'iframe = HQ surrogate :8862 (physical .41:8872)',brain:'gene:deepseek + local', proxy:'/proxy/acer', direct:()=>'http://'+location.hostname+':8852/proxy/acer'},
};
const ORDER = ['acer','tp','hq','wren'];
const wall = document.getElementById('wall');
const ribbon = document.getElementById('ribbon');
for (const k of ORDER){
  const p=P[k]; const c=document.createElement('div'); c.className='chip';
  c.innerHTML='<span class="dot wait" id="rdot-'+k+'"></span><b>'+p.title+'</b><span class="brain">'+p.brain+'</span><span id="rst-'+k+'" style="color:#6f8098">…</span>';
  ribbon.appendChild(c);
}
for (const k of ORDER){
  const p = P[k];
  const el = document.createElement('div');
  el.className='panel';
  el.innerHTML =
    '<div class="bar">'+
      '<span class="dot wait" id="dot-'+k+'"></span>'+
      '<span class="title" onclick="toggleBig(\''+k+'\')">'+p.title+'</span>'+
      '<span class="sub">'+p.sub+'</span>'+
      '<span class="status" id="st-'+k+'">checking…</span>'+
      '<button id="exp-'+k+'" onclick="toggleBig(\''+k+'\')">&#9974; Big</button>'+
      '<button onclick="reloadP(\''+k+'\')">&#8635; Reload</button>'+
      '<button onclick="openP(\''+k+'\')">&#8599; Open</button>'+
    '</div>'+
    '<div class="frame-wrap">'+
      '<iframe id="if-'+k+'"></iframe>'+
      '<div class="err" id="err-'+k+'"><h3>Dashboard unreachable</h3><code id="errc-'+k+'"></code>'+
      '<button onclick="reloadP(\''+k+'\')">Retry</button></div>'+
    '</div>';
  wall.appendChild(el);
  document.getElementById('if-'+k).src = P[k].proxy;
}
function toggleBig(k){
  const wall=document.getElementById('wall');
  const panel=document.getElementById('if-'+k).closest('.panel');
  const wasBig=panel.classList.contains('big');
  document.querySelectorAll('.panel').forEach(p=>p.classList.remove('big'));
  document.querySelectorAll('[id^="exp-"]').forEach(b=>{b.innerHTML='&#9974; Big';b.classList.remove('big-on');});
  if (wasBig){ wall.classList.remove('expanded'); }
  else { wall.classList.add('expanded'); panel.classList.add('big');
    const eb=document.getElementById('exp-'+k); eb.innerHTML='&#10066; 2×2'; eb.classList.add('big-on'); }
}
document.addEventListener('keydown',e=>{ if(e.key==='Escape'){ const b=document.querySelector('.panel.big'); if(b){ toggleBig(b.querySelector('iframe').id.slice(3)); } }});
const BCAST=[['hq_claude','Claude HQ'],['wren','Wren'],['tp_pip','TP-Pip'],['acer_cass','Acer-Cass']];
function broadcast(){
  const t=document.getElementById('bcast').value.trim(); if(!t) return;
  document.getElementById('bcast').value='';
  const box=document.getElementById('replies'); box.style.display='grid'; box.innerHTML='';
  document.getElementById('bcast-status').textContent='asking 4 CEOs…';
  let done=0;
  for(const [id,name] of BCAST){
    const card=document.createElement('div'); card.className='rcard';
    card.innerHTML='<b>'+name+'</b><div class="rtxt">…thinking</div>'; box.appendChild(card);
    const txt=card.querySelector('.rtxt');
    // Claude HQ -> safe proxy /api/times4/ask_claude_hq (honest JSON, never empty);
    // other CEOs -> /ceo_mind/<ceo>. Parse SAFELY so an empty/non-JSON body shows
    // an honest message instead of crashing r.json() (the old SyntaxError bug).
    const url = (id==='hq_claude') ? '/api/times4/ask_claude_hq' : '/ceo_mind/'+id;
    fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:t,mode:'gene'})})
      .then(async r=>{ const tx=await r.text();
        if(!tx || !tx.trim()) return {ok:false, reply:'⚠ empty reply (backend busy) — press Ask again'};
        try{ return JSON.parse(tx); }catch(e){ return {ok:false, reply:'⚠ bad reply: '+tx.slice(0,80)}; } })
      .then(d=>{ txt.textContent=(d.reply || d.error || '(no reply)'); const m=d.mind||d.via||''; if(m) txt.textContent+='\n— '+m; })
      .catch(e=>{ txt.textContent='⚠ unreachable: '+e; })
      .finally(()=>{ done++; if(done===BCAST.length) document.getElementById('bcast-status').textContent='4/4 replied'; });
  }
}
async function checkHqChat(){
  const el=document.getElementById('hq-chat-status'); if(!el) return;
  try{
    const d=await(await fetch('/quad_monitor/health',{cache:'no-store'})).json();
    const up=!!(d.panels&&d.panels.hq&&d.panels.hq.up);
    if(up){ el.textContent='HQ chat: ONLINE'; el.style.background='#064e3b'; el.style.color='#6ee7b7'; }
    else  { el.textContent='HQ chat: BROKEN'; el.style.background='#7f1d1d'; el.style.color='#fca5a5'; }
  }catch(e){ el.textContent='HQ chat: BROKEN'; el.style.background='#7f1d1d'; el.style.color='#fca5a5'; }
}
checkHqChat(); setInterval(checkHqChat, 15000);
function reloadP(k){
  const f=document.getElementById('if-'+k);
  f.src = P[k].direct() + '?_=' + Date.now();
  document.getElementById('err-'+k).classList.remove('show');
  document.getElementById('dot-'+k).className='dot wait';
  document.getElementById('st-'+k).textContent='reloading…';
  setTimeout(poll, 900);
}
function openP(k){ window.open(P[k].direct(), '_blank'); }
// MASTER PHASE 1 — badges + truth cards are driven ONLY by /quad_monitor/truth,
// which independently probes physical box, HQ surrogate, dashboard, and mind.
function _sc(s){ return s==='LIVE'?'#22c55e':(s==='PARTIAL'?'#eab308':(s==='UNREACHABLE'||s==='OFFLINE')?'#ef4444':'#64748b'); }
function _b(s){ return '<b style="color:'+_sc(s)+'">'+s+'</b>'; }
function _hhmmss(t){ return (t&&t.length>=19)?t.slice(11,19)+'Z':'—'; }
function _tsline(o){
  return 'probed '+_hhmmss(o.probe_ts)+' · HTTP '+(o.code||0)+' · last ok '+_hhmmss(o.last_ok)+' · last fail '+_hhmmss(o.last_fail);
}
function renderTruth(d){
  const tt=document.getElementById('truth-ts'); if(tt) tt.textContent=' · updated '+_hhmmss(d.ts);
  const box=document.getElementById('truthcards'); if(!box) return; let html='';
  const card=(title,mode,inner)=>'<div style="background:#0f1620;border:1px solid #1e2a38;border-radius:8px;padding:8px 10px;font-size:11.5px;line-height:1.5">'+
    '<div style="font-weight:800;font-size:13px;color:#e2e8f0;margin-bottom:4px">'+title+
    ' <span style="float:right;font-size:10px;font-weight:700;color:#94a3b8">MODE: '+mode+'</span></div>'+inner+'</div>';
  for(const k of ['acer','tp']){
    const c=d.ceos&&d.ceos[k]; if(!c) continue;
    const p=c.physical_runtime, s=c.surrogate, od=c.original_dashboard;
    const idbits=(p.identity?(' id:'+p.identity):'')+(p.hostname?(' · host:'+p.hostname):'')+(p.host_mode?(' · ['+p.host_mode+']'):'');
    let odline;
    if(od.endpoint && od.endpoint!=='UNKNOWN'){ odline='ORIGINAL DASHBOARD: '+_b(od.state)+' <span style="color:#64748b">'+od.endpoint+'</span>'; }
    else { odline='ORIGINAL DASHBOARD: <b style="color:#7cc4ff">LOCAL — ROSS-CONFIRMED</b> <span style="color:#64748b">remote endpoint '+(od.remote_endpoint||'UNKNOWN')+'</span>'; }
    const hist=c.historical_endpoint?('<div style="margin-top:3px;color:#8a763f">HISTORICAL: '+c.historical_endpoint.endpoint+' — '+c.historical_endpoint.label+' (not used for live status)</div>'):'';
    html+=card(c.name, c.operating_mode,
      '<div>MACHINE POWER: <b style="color:#22c55e">ON</b> <span style="color:#64748b">— Ross-confirmed physical observation</span></div>'+
      '<div style="margin-top:3px">PHYSICAL RUNTIME: '+_b(p.state)+' <span style="color:#64748b">'+p.endpoint+idbits+'</span><br><span style="color:#64748b">'+_tsline(p)+(p.detail?(' · '+p.detail):'')+'</span><br><span style="color:#64748b">'+p.source+'</span></div>'+
      '<div style="margin-top:3px">'+odline+'</div>'+
      '<div style="margin-top:3px">HQ SURROGATE (separate): '+_b(s.state)+' <span style="color:#64748b">'+s.endpoint+(s.identity?(' (id:'+s.identity+')'):'')+'</span></div>'+
      hist);
  }
  const h=d.ceos&&d.ceos.hq;
  if(h) html+=card(h.name, h.operating_mode,
    '<div>DASHBOARD: '+_b(h.dashboard.state)+' <span style="color:#64748b">'+h.dashboard.endpoint+'</span><br><span style="color:#64748b">'+_tsline(h.dashboard)+'</span></div>'+
    '<div style="margin-top:4px">MIND / RUNTIME: <b style="color:#64748b">NOT TESTED</b> <span style="color:#64748b">('+h.mind.note+')</span></div>');
  const w=d.ceos&&d.ceos.wren;
  if(w){ const dup=w.duplicate_warning?('<div style="color:#f59e0b;margin-top:3px">⚠ DUPLICATE: '+w.duplicate_warning.join(', ')+'</div>'):'';
    const lr=(w.last_genuine_reply&&w.last_genuine_reply.found)?('last genuine reply '+(w.last_genuine_reply.ts||'?')+' ('+w.last_genuine_reply.source+')'):'no genuine Wren reply found in registry';
    html+=card(w.name, w.operating_mode,
      '<div>DASHBOARD HTTP: '+_b(w.dashboard.state)+' <span style="color:#64748b">'+w.dashboard.endpoint+'</span><br><span style="color:#64748b">'+w.dashboard.means+'</span></div>'+
      '<div style="margin-top:4px">MIND / RUNTIME: '+_b(w.mind_runtime.state)+' <span style="color:#64748b">('+w.mind_runtime.count+' proc)</span> · WATCHER: '+_b(w.watcher.state)+'</div>'+
      '<div style="margin-top:2px">CONCIERGE: '+_b(w.concierge.state)+' <span style="color:#64748b">'+w.concierge.endpoint+'</span></div>'+dup+
      '<div style="margin-top:3px;color:#94a3b8">'+lr+' · source: '+w.status_source+'</div>');
  }
  box.innerHTML=html;
}
async function poll(){
  let d;
  try { d = await (await fetch('/quad_monitor/truth',{cache:'no-store'})).json(); }
  catch(e){ for(const k of ORDER){ setDown(k,'truth probe failed: '+e); } return; }
  renderTruth(d);
  for (const k of ORDER){
    const c=(d.ceos||{})[k];
    if (!c){ setDown(k,'no truth data'); continue; }
    const dot=document.getElementById('dot-'+k), st=document.getElementById('st-'+k), err=document.getElementById('err-'+k);
    const rdot=document.getElementById('rdot-'+k), rst=document.getElementById('rst-'+k);
    let dotcls, label, ifaceUp, ep;
    if(k==='tp'||k==='acer'){
      const phys=c.physical_runtime.state, surr=c.surrogate.state; ifaceUp=(surr==='LIVE'); ep=c.surrogate.endpoint;
      if(phys==='LIVE'){ dotcls='dot up'; label='PHYSICAL WORKER ACTIVE · HTTP '+c.physical_runtime.code; }
      else if(surr==='LIVE'){ dotcls='dot wait'; label='machine ON (Ross) · SURROGATE ACTIVE · physical endpoint UNREACHABLE'; }
      else { dotcls='dot wait'; label='machine ON (Ross) · physical endpoint UNREACHABLE'; }
    } else if(k==='hq'){
      ifaceUp=(c.dashboard.state==='LIVE'); ep=c.dashboard.endpoint;
      dotcls=ifaceUp?'dot up':'dot down';
      label=ifaceUp?'dashboard live · mind=CLI (not tested)':'dashboard '+c.dashboard.state;
    } else {
      ifaceUp=(c.dashboard.state==='LIVE'); ep=c.dashboard.endpoint;
      dotcls=ifaceUp?'dot up':'dot down';
      label=(ifaceUp?'dash live':'dash '+c.dashboard.state)+' · mind '+c.mind_runtime.state;
    }
    dot.className=dotcls; st.textContent=label;
    if(rdot) rdot.className=dotcls;
    if(rst) rst.textContent='· '+label.slice(0,26);
    if(ifaceUp){ err.classList.remove('show'); }
    else { document.getElementById('errc-'+k).textContent=ep+' — surrogate/dashboard unreachable'; err.classList.add('show'); }
  }
}
function setDown(k,msg){
  document.getElementById('dot-'+k).className='dot down';
  const _rd=document.getElementById('rdot-'+k); if(_rd) _rd.className='dot down';
  const _rs=document.getElementById('rst-'+k); if(_rs) _rs.textContent='· DOWN';
  document.getElementById('st-'+k).textContent='DOWN';
  document.getElementById('errc-'+k).textContent=msg;
  document.getElementById('err-'+k).classList.add('show');
}
poll();
setInterval(poll, 8000);
</script>
</body></html>
"""

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
  <span class="badge">HQ · 192.168.1.72</span>
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
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>
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
        # LEGACY / NON-AUTHORITATIVE: retired council_node feed on TP .74:9100 (NOT the authoritative worker .74:8871, which serves no /feed). Backend telemetry probe only; may 404 until a feed shim exists. Flagged S4B1B.
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
        for l in _safe_tail_lines(cyc, 8):
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
        for l in _safe_tail_lines(bc, 4):
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
    for peer in [("TP-Pip", "http://192.168.1.74:8871/state", "Command Cathedral", "#22d3ee", "ThinkPad, T500 GPU"),
                 ("Acer-Cass", "http://192.168.1.41:8872/state", "Data Foundry", "#f59e0b", "Acer laptop, CPU-only")]:
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
// LINK HEALTH — server-side probes via /link_health endpoint (Ross 2026-07-05)
async function linkTick(){
  const el = document.getElementById('link-health'); if(!el) return;
  try{
    const d = await (await fetch('/link_health',{cache:'no-store'})).json();
    el.innerHTML = (d.links||[]).map(r => {
      const dot = r.ok ? '<span style="color:#10b981;font-size:14px">●</span>' : '<span style="color:#ef4444;font-size:14px;animation:pulse 1.2s infinite">●</span>';
      const detail = r.ok
        ? `<span style="color:#64748b;font-size:10px;">${r.ms}ms · HTTP ${r.code}</span>`
        : `<span style="color:#ef4444;font-size:10px;">${(r.err||'unreachable').slice(0,60)}</span>`;
      return '<div style="padding:5px 8px;display:flex;align-items:center;gap:8px;background:#0b0d12;margin:3px 0;border-radius:6px">'
        + dot + '<b style="color:#e8ecf3">'+r.name+'</b>'
        + '<span style="color:#64748b;font-size:10.5px;flex:1">'+r.hint+'</span>'
        + detail + '</div>';
    }).join('');
  }catch(e){el.textContent='link health check failed: '+e}
}
tick(); setInterval(tick, 3000);
tsTick(); setInterval(tsTick, 3000);
driftTick(); setInterval(driftTick, 3000);
linkTick(); setInterval(linkTick, 6000);
</script><a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>"""


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
</script><a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>"""


BROKER_HTML = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>🧠 Brain Router · External AI Gateway</title>
<style>
*{box-sizing:border-box}
body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px}
h1{margin:0 0 4px;color:#eab308;font-size:22px}
.sub{color:#94a3b8;font-size:12px;margin-bottom:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:10px;margin-bottom:16px}
.card{background:#111827;border:1px solid #1e293b;border-radius:10px;padding:12px}
.name{color:#eab308;font-weight:700;font-size:14px}
.badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:10px;font-weight:700;margin-left:6px}
.ready{background:#22c55e;color:#000}
.miss{background:#334155;color:#94a3b8}
.use{color:#94a3b8;font-size:11px;margin-top:6px}
.panel{background:#111827;border:1px solid #1e293b;border-radius:10px;padding:14px;margin-bottom:14px}
.panel h3{margin:0 0 8px;color:#eab308;font-size:15px}
input,select,button{background:#0b0d12;color:#e8ecf3;border:1px solid #334155;border-radius:8px;padding:8px 12px;font-size:13px}
button{background:#eab308;color:#000;font-weight:700;cursor:pointer}
.test-row{display:flex;gap:6px;flex-wrap:wrap;align-items:center}
#test-input{flex:1;min-width:200px}
#test-out{background:#0b0d12;border-radius:8px;padding:10px;margin-top:8px;font-family:ui-monospace,monospace;font-size:11px;white-space:pre-wrap;max-height:160px;overflow-y:auto}
table{width:100%;border-collapse:collapse;font-size:11px}
th,td{padding:6px 8px;border-bottom:1px solid #1e293b;text-align:left;font-family:ui-monospace,monospace}
th{background:#1e293b;color:#94a3b8}
.home{position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,.6);font-size:22px}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;background:#1e293b;color:#94a3b8;margin-left:6px}
.live{background:#22c55e;color:#000}
</style></head><body>
<h1>🧠 Brain Router · External AI Gateway <span class=pill id=ts>—</span></h1>
<div class=sub>Route external AI work through here — save Claude tokens for CEO judgement. Backend: <code>tools/qsb_brain_router.py</code>. <a href="/tasks" style="color:#eab308">← task council</a> · <a href="/team_live" style="color:#eab308">team live →</a></div>

<div class=panel><h3>Claude health <span id=ch-pill class=pill>—</span></h3><div id=ch-detail style="font-family:ui-monospace,monospace;font-size:12px;color:#94a3b8">probing...</div></div>

<div class=panel><h3>Provider status <span id=fallback-hint class=pill style="background:#334155;color:#94a3b8">Ross rule: capability > provider</span></h3><div class=grid id=providers>loading...</div></div>

<div class=panel>
  <h3>Test panel — safe request</h3>
  <div class=test-row>
    <select id=test-tier><option value=worker selected>tier: worker (cheap)</option><option value=premium>tier: premium (Claude)</option></select>
    <select id=test-task>
      <option value=chat selected>task: chat</option><option value=code>task: code</option>
      <option value=reason>task: reason</option><option value=long>task: long</option>
    </select>
    <input id=test-input placeholder='safe prompt (e.g. "reply: pong")' value="Reply exactly: brain-router test ok" />
    <button id=test-btn>ROUTE</button>
  </div>
  <div id=test-out>waiting...</div>
</div>

<div class=panel><h3>Recent calls (journal, secrets stripped)</h3><div id=journal>loading...</div></div>

<a href="/ipad" class=home>🏠</a>

<script>
async function tick(){
  try{
    const d = await (await fetch('/broker/status',{cache:'no-store'})).json();
    document.getElementById('ts').textContent=(d.ts||'').slice(11,19)+'Z';
    document.getElementById('ts').className='pill live';
    document.getElementById('providers').innerHTML = Object.entries(d.providers||{}).map(([k,v])=>{
      const cls = v.configured ? 'ready' : 'miss';
      const lbl = v.configured ? 'READY' : 'no key';
      return `<div class=card><div class=name>${k}<span class="badge ${cls}">${lbl}</span></div><div class=use>${v.use||''}</div></div>`;
    }).join('');
  } catch(e){ document.getElementById('providers').textContent='status err'; }

  try{
    const hd = await (await fetch('/broker/claude_health',{cache:'no-store'})).json();
    const c = hd.claude || {};
    const pill = document.getElementById('ch-pill');
    pill.textContent = c.healthy ? 'HEALTHY' : 'UNHEALTHY: '+(c.reason||'?');
    pill.className = 'pill ' + (c.healthy ? 'ready' : 'miss');
    document.getElementById('ch-detail').textContent = `reason=${c.reason||'?'} · http=${c.http||'?'} · latency=${c.latency_ms||'?'}ms · fallback→worker tier (Groq/Gemini/DeepSeek/OpenAI/Kimi/Cohere/Ollama)`;
  } catch(e){ document.getElementById('ch-detail').textContent='health err'; }

  try{
    const jd = await (await fetch('/broker/journal?n=20',{cache:'no-store'})).json();
    const rows = jd.rows||[];
    if(!rows.length){document.getElementById('journal').textContent='(no calls yet)';return;}
    document.getElementById('journal').innerHTML = '<table><thead><tr><th>ts</th><th>caller</th><th>provider</th><th>model</th><th>task</th><th>tier</th><th>lat</th><th>cost</th></tr></thead><tbody>'+
      rows.map(r=>`<tr><td>${(r.ts||'').slice(11,19)}</td><td>${r.caller||'?'}</td><td>${r.provider||'?'}</td><td>${(r.model||'?').slice(0,25)}</td><td>${r.task||'?'}</td><td>${r.tier||'?'}</td><td>${r.latency_s?.toFixed(1)||'?'}</td><td>${r.cost_usd?.toFixed(5)||'?'}</td></tr>`).join('')+
      '</tbody></table>';
  } catch(e){ document.getElementById('journal').textContent='journal err'; }
}

document.getElementById('test-btn').onclick = async () => {
  const tier=document.getElementById('test-tier').value;
  const task=document.getElementById('test-task').value;
  const prompt=document.getElementById('test-input').value.trim() || 'reply: ok';
  document.getElementById('test-out').textContent = 'routing…';
  try{
    const q = new URLSearchParams({tier,task,prompt}).toString();
    const r = await fetch('/broker/test?'+q, {cache:'no-store'});
    const d = await r.json();
    document.getElementById('test-out').textContent = JSON.stringify(d, null, 2);
    tick();
  } catch(e){ document.getElementById('test-out').textContent = 'err: '+e; }
};

tick(); setInterval(tick, 3000);
</script>
</body></html>
"""

TEAM_LIVE_HTML = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>🟨 4x Team Live — HQ · TP · Acer · Wren</title>
<style>
*{box-sizing:border-box}
body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:14px}
h1{margin:0 0 4px;color:#eab308;font-size:20px}
.sub{color:#94a3b8;margin-bottom:12px;font-size:12px}
.quorum-strip{background:#111827;border:1px solid #1e293b;border-radius:10px;padding:10px 14px;margin-bottom:14px;display:flex;gap:12px;align-items:center;flex-wrap:wrap}
.q-item{display:flex;gap:6px;align-items:center}
.q-name{font-weight:700}
.q-dot{width:10px;height:10px;border-radius:50%}
.dot-on{background:#22c55e;box-shadow:0 0 8px #22c55e88}
.dot-off{background:#ef4444}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:14px}
@media (max-width:900px){.grid{grid-template-columns:1fr}}
.pane{background:#111827;border:1px solid #1e293b;border-radius:12px;padding:14px;position:relative}
.pane h3{margin:0 0 8px;color:#eab308;font-size:15px;display:flex;justify-content:space-between;align-items:center}
.pane .conn{color:#94a3b8;font-size:11px;font-family:ui-monospace,monospace}
.thoughts{background:#0b0d12;border-radius:8px;padding:10px;margin-top:8px;font-size:12px;max-height:150px;overflow-y:auto}
.thought{padding:4px 0;border-bottom:1px dashed #1e293b}
.thought:last-child{border:none}
.thought .t-ts{color:#64748b;font-size:10px;margin-right:6px}
.commentary-row{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.cbtn{background:#1e293b;color:#eab308;border:1px solid #334155;padding:6px 10px;border-radius:6px;cursor:pointer;font-size:11px;font-weight:600}
.cbtn:hover{background:#334155}
.chatbox{background:#111827;border:1px solid #1e293b;border-radius:12px;padding:12px;margin-bottom:14px}
.chatbox h3{margin:0 0 8px;color:#eab308;font-size:15px}
#chatlog{background:#0b0d12;border-radius:8px;padding:10px;height:200px;overflow-y:auto;margin-bottom:8px;font-size:12px}
.chatmsg{padding:3px 0}
.chatmsg .m-from{color:#eab308;font-weight:700;margin-right:6px}
.chatmsg .m-ts{color:#64748b;font-size:10px;margin-right:6px}
.chatinput{display:flex;gap:6px}
#chatinput{flex:1;background:#0b0d12;color:#e8ecf3;border:1px solid #334155;padding:8px 10px;border-radius:8px;font-size:13px}
#chatsend, #speak-toggle{background:#eab308;color:#000;border:none;padding:8px 14px;border-radius:8px;font-weight:700;cursor:pointer}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:10px;background:#1e293b;color:#94a3b8;margin-left:6px}
.live{background:#22c55e;color:#000}
.home{position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px}
</style></head><body>
<h1>🟨 4x Team Live <span class=pill id=ts>—</span></h1>
<div class=sub>HQ · TP · Acer · Wren — live stats + thoughts + chat + speech + commentary. <a href="/tasks" style="color:#eab308">← task council</a> · <a href="/trading" style="color:#eab308">traders →</a></div>

<div class=quorum-strip>
  <div class=q-item><span class=q-name>QUORUM:</span><span id=q-count style="color:#eab308;font-weight:700">?</span></div>
  <div class=q-item><span class=q-dot id=d-hq></span>HQ</div>
  <div class=q-item><span class=q-dot id=d-tp></span>TP</div>
  <div class=q-item><span class=q-dot id=d-acer></span>Acer</div>
  <div class=q-item><span class=q-dot id=d-wren></span>Wren</div>
  <button id="speak-toggle" style="margin-left:auto">🔊 speech: ON</button>
</div>

<div class=grid>
  <div class=pane id=p-hq><h3>🟨 HQ-Claude <span class=conn id=c-hq>?</span></h3><div class=thoughts id=t-hq></div>
    <div class=commentary-row>
      <button class=cbtn onclick="say('hq_claude','status update: OANDA trader live, EUR/USD long')">🗣 status update</button>
      <button class=cbtn onclick="say('hq_claude','quorum check running')">🗣 quorum check</button>
      <button class=cbtn onclick="say('hq_claude','all systems nominal')">🗣 nominal</button>
    </div>
  </div>
  <div class=pane id=p-tp><h3>🔷 TP-Pip <span class=conn id=c-tp>?</span></h3><div class=thoughts id=t-tp></div>
    <div class=commentary-row>
      <button class=cbtn onclick="say('tp_pip','Binance testnet trader active')">🗣 binance</button>
      <button class=cbtn onclick="say('tp_pip','node vitals green')">🗣 vitals</button>
    </div>
  </div>
  <div class=pane id=p-acer><h3>🟨 Acer-Cass <span class=conn id=c-acer>?</span></h3><div class=thoughts id=t-acer></div>
    <div class=commentary-row>
      <button class=cbtn onclick="say('acer_cass','Alpaca paper trader running')">🗣 alpaca</button>
      <button class=cbtn onclick="say('acer_cass','SPY position tracked')">🗣 spy</button>
    </div>
  </div>
  <div class=pane id=p-wren><h3>🟪 Wren <span class=conn id=c-wren>?</span></h3><div class=thoughts id=t-wren></div>
    <div class=commentary-row>
      <button class=cbtn onclick="say('wren','watching all 3 CEOs, quorum ok')">🗣 watching</button>
      <button class=cbtn onclick="say('wren','ready to escalate to Ross via WhatsApp')">🗣 ready-to-escalate</button>
    </div>
  </div>
</div>

<div class=chatbox>
  <h3>💬 Team chat (posts to town-square)</h3>
  <div id=chatlog></div>
  <div class=chatinput>
    <input id=chatinput placeholder="type + Enter — sends as HQ to council" onkeydown="if(event.key==='Enter')sendChat()">
    <button id=chatsend onclick=sendChat()>Send</button>
  </div>
</div>

<a href="/ipad" class=home>🏠</a>

<script>
let speechOn = true;
document.getElementById('speak-toggle').onclick = () => {
  speechOn = !speechOn;
  document.getElementById('speak-toggle').textContent = speechOn ? '🔊 speech: ON' : '🔇 speech: OFF';
};

function speak(text){
  if (!speechOn) return;
  try{
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.05; u.volume = 0.9;
    speechSynthesis.speak(u);
  } catch(e){}
}

async function say(ceo, text){
  try{
    await fetch('/team_live/say?ceo='+encodeURIComponent(ceo)+'&text='+encodeURIComponent(text), {cache:'no-store'});
    speak((ceo || 'ceo').replace('_',' ') + ' says: ' + text);
  } catch(e){}
}

async function sendChat(){
  const el = document.getElementById('chatinput');
  const text = el.value.trim();
  if(!text) return;
  el.value = '';
  await say((localStorage.getItem('qsb_team_live_speaker') || 'ross'), text);
}

async function tick(){
  try{
    const d = await (await fetch('/team_live/data',{cache:'no-store'})).json();
    document.getElementById('ts').textContent = d.ts.slice(11,19)+'Z';
    document.getElementById('ts').className = 'pill live';
    // quorum
    const q = d.quorum || {};
    document.getElementById('q-count').textContent = q.online_count || '?';
    for (const c of q.ceos || []){
      const dot = document.getElementById('d-'+c.ceo.replace('_claude','').replace('_pip','').replace('_cass',''));
      if(dot) dot.className = 'q-dot ' + (c.online ? 'dot-on' : 'dot-off');
    }
    document.getElementById('d-wren').className = 'q-dot dot-on'; // wren local always considered on
    // connections
    for (const [ceo, info] of Object.entries(d.connections || {})){
      const key = 'c-' + ceo.replace('_claude','').replace('_pip','').replace('_cass','');
      const el = document.getElementById(key);
      if (el) el.textContent = info.endpoint + ' · ' + info.status;
    }
    // thoughts
    for (const [ceo, notes] of Object.entries(d.cards || {})){
      const key = 't-' + ceo.replace('_claude','').replace('_pip','').replace('_cass','');
      const el = document.getElementById(key);
      if(!el) continue;
      el.innerHTML = (notes || []).map(n => `<div class=thought><span class=t-ts>${(n.ts||'').slice(11,19)}</span>${(n.head||'').replace(/</g,'&lt;')}</div>`).join('') || '<div class=thought style="color:#64748b">— no recent thoughts —</div>';
    }
    // chat/town-square
    const cl = document.getElementById('chatlog');
    const seen = cl.dataset.lastTs || '';
    const fresh = (d.town_square || []).filter(m => m.ts > seen);
    for (const m of fresh){
      const div = document.createElement('div');
      div.className = 'chatmsg';
      div.innerHTML = `<span class=m-ts>${(m.ts||'').slice(11,19)}</span><span class=m-from>${m.from||'?'}:</span>${(m.text||'').replace(/</g,'&lt;').slice(0,300)}`;
      cl.appendChild(div);
      cl.dataset.lastTs = m.ts;
      // speak fresh commentary_from_team
      if (m.src === 'team_live_commentary' && seen){
        speak((m.from||'').replace('_',' ') + ' says: ' + m.text);
      }
    }
    cl.scrollTop = cl.scrollHeight;
  } catch(e){
    document.getElementById('ts').textContent = 'err';
    document.getElementById('ts').className = 'pill';
  }
}
tick(); setInterval(tick, 1500);
</script>
</body></html>
"""

TRADING_HTML = r"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>🎯 4× Claude Traders — Live</title>
<style>
*{box-sizing:border-box}
body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif;margin:0;padding:16px}
h1{margin:0 0 4px;color:#eab308;font-size:22px}
.sub{color:#94a3b8;margin-bottom:14px;font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:14px;margin-bottom:20px}
.card{background:#111827;border:1px solid #1e293b;border-radius:12px;padding:16px}
.ceo{color:#eab308;font-weight:800;font-size:16px;margin-bottom:2px}
.venue{color:#94a3b8;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px}
.row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid #1e293b;font-size:13px}
.row:last-child{border:none}
.k{color:#94a3b8}
.v{color:#e8ecf3;font-weight:600;font-family:ui-monospace,monospace}
.pnl-pos{color:#22c55e}
.pnl-neg{color:#ef4444}
.pnl-flat{color:#94a3b8}
table{width:100%;border-collapse:collapse;background:#111827;border-radius:10px;overflow:hidden}
th,td{padding:8px 10px;text-align:left;border-bottom:1px solid #1e293b;font-size:12px}
th{background:#1e293b;color:#94a3b8;font-weight:600}
td{color:#e8ecf3}
.side-buy{color:#22c55e;font-weight:700}
.side-sell{color:#ef4444;font-weight:700}
.home{position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px}
.pill{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;background:#1e293b;color:#94a3b8;margin-left:6px}
.live{background:#22c55e;color:#000}
</style></head>
<body>
<h1>🎯 4× Claude Traders <span class=pill id=ts>—</span></h1>
<div class=sub>3 Claudes trading in parallel · Wren learns from all 3 · <a href="/tasks" style="color:#eab308">task council →</a></div>
<div class=grid id=cards></div>
<h2 style="color:#eab308;margin:6px 0 8px;font-size:16px">Recent trades</h2>
<div id=trades></div>
<a href="/ipad" class=home>🏠</a>
<script>
const symLabel = {oanda_practice:"OANDA practice · fx", binance_testnet:"Binance testnet · crypto", alpaca_paper:"Alpaca paper · stocks"};
async function tick(){
  try{
    const d = await (await fetch('/trading/data',{cache:'no-store'})).json();
    document.getElementById('ts').textContent = d.ts.slice(11,19)+'Z';
    document.getElementById('ts').className = 'pill live';
    document.getElementById('cards').innerHTML = d.traders.map(t=>{
      const pnl = t.pnl_pips || t.pnl_usd || '—';
      const pcls = pnl.startsWith('+')||pnl.startsWith('$+') ? 'pnl-pos' : (pnl.startsWith('-')||pnl.startsWith('$-') ? 'pnl-neg' : 'pnl-flat');
      return `<div class=card>
        <div class=ceo>${t.ceo.toUpperCase()}</div>
        <div class=venue>${symLabel[t.venue]||t.venue}</div>
        <div class=row><span class=k>symbol</span><span class=v>${t.symbol||'—'}</span></div>
        <div class=row><span class=k>rounds traded</span><span class=v>${t.rounds}</span></div>
        <div class=row><span class=k>last side</span><span class="v side-${(t.last_side||'').toLowerCase()}">${t.last_side||'—'}</span></div>
        <div class=row><span class=k>entry px</span><span class=v>${t.last_fill_px||'—'}</span></div>
        <div class=row><span class=k>live px</span><span class=v>${t.live_px||'—'}</span></div>
        <div class=row><span class=k>PnL open</span><span class="v ${pcls}">${pnl}</span></div>
      </div>`;
    }).join('');
    document.getElementById('trades').innerHTML = '<table><thead><tr><th>ts</th><th>ceo</th><th>venue</th><th>sym</th><th>side</th><th>size</th><th>fill</th><th>rd</th><th>reason</th></tr></thead><tbody>'+
      d.trades.map(t=>`<tr><td>${(t.ts||'').slice(11,19)}Z</td><td>${t.ceo}</td><td>${t.venue}</td><td>${t.symbol||'—'}</td><td class="side-${(t.side||'').toLowerCase()}">${t.side}</td><td>${t.units||t.qty||'—'}</td><td>${t.fill_px||'pending'}</td><td>${t.round}</td><td>${(t.reason||'').slice(0,60)}</td></tr>`).join('')+
      '</tbody></table>';
  } catch(e){ document.getElementById('ts').textContent = 'err'; document.getElementById('ts').className = 'pill'; }
}
tick(); setInterval(tick, 5000);
</script>
</body></html>
"""

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
<div style='position:sticky;top:0;background:#0b0d12;padding:8px 0 10px;margin-bottom:12px;border-bottom:1px solid #22334a;display:flex;gap:6px;flex-wrap:wrap;overflow-x:auto;z-index:100'>
  <a href='/ipad' style='background:#eab308;color:#000;padding:8px 12px;text-decoration:none;border-radius:6px;font-weight:800;font-size:12px;white-space:nowrap'>📱 iPad</a>
  <a href='/tasks' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>📋 tasks</a>
  <a href='/town_square' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🗣️ town</a>
  <a href='/council' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>👥 council</a>
  <a href='/traders' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>💰 traders</a>
  <a href='/timeline' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>📈 timeline</a>
  <a href='/rules' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>📜 rules</a>
  <a href='/annexes' style='background:#1e293b;color:#e8ecf3;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🏠 annexes</a>
  <a href='javascript:location.reload(true)' style='background:#1e293b;color:#94a3b8;padding:8px 12px;text-decoration:none;border-radius:6px;font-size:12px;white-space:nowrap'>🔄</a>
</div>
<!-- Ross 2026-07-06: floating home button. -->
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a>
<!-- Ross 2026-07-06: HQ-Claude stats strip. Live via /hq/stats. ADD not TAKE. -->
<div id=hq-stats-strip style="background:#0e1420;border:1px solid #eab30840;border-radius:8px;padding:10px 14px;margin-bottom:12px;display:flex;gap:18px;flex-wrap:wrap;font-family:ui-monospace,monospace;font-size:11.5px;color:#94a3b8">
  <div><span style="color:#eab308;font-weight:800">🧠 HQ-Claude</span> · rank <b id=hq-rank style="color:#e8ecf3">?</b> · brain <b id=hq-brain style="color:#e8ecf3">?</b></div>
  <div>today: <b id=hq-today style="color:#eab308">?</b> actions (<b id=hq-prop style="color:#22d3ee">?</b> prop · <b id=hq-signoff style="color:#a78bfa">?</b> signoff · <b id=hq-done style="color:#10b981">?</b> done)</div>
  <div>board: <b id=hq-board-open style="color:#e8ecf3">?</b> open · <b id=hq-board-inprog style="color:#f59e0b">?</b> in-progress · <b id=hq-board-done style="color:#10b981">?</b> done · <b id=hq-board-total style="color:#94a3b8">?</b> total</div>
  <div>ledger: <b id=hq-ledger style="color:#e8ecf3">?</b> · notes: <b id=hq-notes style="color:#e8ecf3">?</b></div>
  <div>pid <b id=hq-pid style="color:#e8ecf3">?</b></div>
</div>
<script>
async function hqStatsTick(){
  try{
    const d = await (await fetch('/hq/stats',{cache:'no-store'})).json();
    const set=(id,v)=>{const e=document.getElementById(id);if(e && v!==undefined && v!==null) e.textContent=v};
    set('hq-rank', d.rank); set('hq-brain', d.brain);
    set('hq-today', d.today_actions_total); set('hq-prop', d.today_proposed);
    set('hq-signoff', d.today_peer_signoffs); set('hq-done', d.today_closes);
    const b=d.board||{};
    set('hq-board-open', b.open); set('hq-board-inprog', b.in_progress);
    set('hq-board-done', b.done); set('hq-board-total', b.total);
    set('hq-ledger', d.ledger_entries); set('hq-notes', d.long_form_notes);
    set('hq-pid', d.pid);
  }catch(e){}
}
setInterval(hqStatsTick, 5000);
setTimeout(hqStatsTick, 300);
</script>
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
<!-- Ross 2026-07-05 #158: ANNEX FLEET tile -->
<div id=annex-fleet-window style="margin-top:20px;padding:14px;background:#0e1420;border:1px solid #22334a;border-radius:10px;">
  <h2 style="margin:0 0 6px;color:#f43f5e;font-size:1.15em;">🏠 ANNEX FLEET · traders circulating across skyscraper</h2>
  <div style="color:#94a3b8;font-size:11.5px;margin-bottom:10px;">5 annexes total (Oracle · HQ · Wren · TP · Acer) · profitable traders earn to pick their annex weekly.</div>
  <div id=annex-fleet-body style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:10px;">loading…</div>
</div>
<script>
async function annexTick(){
  try{
    const d = await (await fetch('/annexes',{cache:'no-store'})).json();
    const el = document.getElementById('annex-fleet-body'); if(!el) return;
    el.innerHTML = (d.annexes||[]).map(a => {
      const online = a.online;
      const c = online ? '#10b981' : '#ef4444';
      return `<div style="padding:10px;background:#0b1220;border-left:3px solid ${c};border-radius:6px">
        <div style="display:flex;align-items:center;gap:6px">
          <span style="width:8px;height:8px;border-radius:50%;background:${c};display:inline-block${online?';animation:phone-live-pulse 1.6s infinite':''}"></span>
          <b style="color:#e8ecf3;font-size:12px">${a.name}</b>
        </div>
        <div style="margin-top:5px;font-size:10.5px;color:#94a3b8;font-family:ui-monospace,monospace">
          ${online ? '👥 <b style="color:#22d3ee">'+a.trader_count+'</b> traders · 💰 <b style="color:#eab308">$'+a.equity_sum+'</b>' : '<i>offline</i>'}
        </div>
      </div>`;
    }).join('') + `<div style="grid-column:1/-1;padding:8px 10px;background:#0b1220;border-radius:6px;font-size:11px;color:#94a3b8">
      FLEET total: <b style="color:#e8ecf3">${d.total_traders}</b> traders · <b style="color:#eab308">$${d.total_equity}</b> equity across all annexes
    </div>`;
  }catch(e){}
}
annexTick(); setInterval(annexTick, 3000);
</script>

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
const ALL_PROVIDERS = ['groq','gemini','cohere','deepseek','openai','kimi','claude','ollama_lan','ollama_local'];
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
codeTick(); setInterval(codeTick, 3000);
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
  // Ross 2026-07-05 #137: PARTNER display — no solo, 2 CEOs handle every task
  const partnerCandidates = ['hq_claude','wren','tp_pip','acer_cass'].filter(c => c !== t.owner);
  const partnerColor = OWNERS[t.partner || partnerCandidates[0]] || '#374151';
  const partnerName = t.partner || partnerCandidates[0];
  const partnerHtml = t.owner ? `<span class="tag" style="background:${partnerColor};color:#000;font-size:10px" title="partner (rule #137)">🤝 ${partnerName}</span>` : '';
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
  return `<div class="task ${priClass} ${isStale?'stale':''}"><div class=title>${esc(t.title||'(untitled)')}</div>${t.description?`<div class=desc>${esc(t.description)}</div>`:''}<div class=meta>${owner}${partnerHtml}${assignee}${by}${pri}${age}${stage}${cb}${staleBadge}</div>${collabsHtml}${revGauge}${liveActivity}${progress}${deliveredHtml}${subs}${actions}</div>`;
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
</script><a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>"""


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


# iPad slice α — /ceo_mind/<ceo> router shipped 2026-07-06 (t_83359acafd)
# Uses SSH ControlMaster socket at /tmp/ssh_cm to reach peers behind Netgear AP isolation
_CEO_PEER_MAP = {
    "wren":      {"kind": "local_ollama", "host": "127.0.0.1", "port": 11434, "model": "qwen2.5:14b"},
    "tp_pip":    {"kind": "ssh_curl",     "ssh_user": "budds", "ssh_host": "192.168.1.41", "port": 9110},
    "acer_cass": {"kind": "ssh_curl",     "ssh_user": "budds", "ssh_host": "192.168.1.41", "port": 8872},
}
_SSH_KEY = "/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.skyscraper_ssh"
_SSH_CM_DIR = "/tmp/ssh_cm"

def _call_peer_ceo(ceo: str, prompt: str, timeout_s: int = 30) -> dict:
    """POST {prompt} to a peer CEO's /message endpoint via SSH ControlMaster socket."""
    import subprocess
    cfg = _CEO_PEER_MAP.get(ceo)
    if not cfg:
        return {"ok": False, "error": f"unknown ceo {ceo}"}
    if cfg["kind"] == "local_ollama":
        try:
            req = urllib.request.Request(
                f"http://{cfg['host']}:{cfg['port']}/api/chat",
                data=json.dumps({
                    "model": cfg["model"],
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                }).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            r = urllib.request.urlopen(req, timeout=timeout_s)
            j = json.loads(r.read().decode())
            return {"ok": True, "reply": (j.get("message") or {}).get("content", ""), "via": f"local:{cfg['model']}"}
        except Exception as e:
            return {"ok": False, "error": f"local ollama: {e}", "via": "local"}
    if cfg["kind"] == "ssh_curl":
        body = json.dumps({"from": "hq_claude_via_ipad", "text": prompt})
        # write body to a temp file locally, scp to peer, then curl via SSH
        import tempfile, os
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, dir="/tmp") as f:
            f.write(body); tmp = f.name
        try:
            # 1. scp payload up (using CM socket)
            scp_cmd = ["scp",
                       "-i", _SSH_KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                       "-o", "UserKnownHostsFile=/dev/null", "-o", "ControlMaster=auto",
                       "-o", "ControlPersist=1h", "-o", f"ControlPath={_SSH_CM_DIR}/%r@%h:%p",
                       tmp, f"{cfg['ssh_user']}@{cfg['ssh_host']}:C:/Users/budds/ceo_mind_q.json"]
            subprocess.run(scp_cmd, check=True, timeout=10, capture_output=True)
            # 2. curl on peer via SSH
            ssh_cmd = ["ssh",
                       "-i", _SSH_KEY, "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
                       "-o", "UserKnownHostsFile=/dev/null", "-o", "ControlMaster=auto",
                       "-o", "ControlPersist=1h", "-o", f"ControlPath={_SSH_CM_DIR}/%r@%h:%p",
                       f"{cfg['ssh_user']}@{cfg['ssh_host']}",
                       f"curl.exe -s -m {timeout_s} -X POST -H \"Content-Type: application/json\" "
                       f"--data-binary \"@C:\\Users\\budds\\ceo_mind_q.json\" "
                       f"http://127.0.0.1:{cfg['port']}/message"]
            out = subprocess.run(ssh_cmd, timeout=timeout_s + 5, capture_output=True, text=True)
            if out.returncode != 0:
                return {"ok": False, "error": f"ssh rc={out.returncode}: {out.stderr[:200]}"}
            try:
                j = json.loads(out.stdout)
                return {"ok": True, "reply": j.get("reply", ""), "via": j.get("via", "peer"), "node": j.get("node", ceo)}
            except json.JSONDecodeError:
                return {"ok": False, "error": f"non-json response: {out.stdout[:200]}"}
        finally:
            try: os.unlink(tmp)
            except: pass
    return {"ok": False, "error": f"unknown peer kind {cfg['kind']}"}


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


def _maybe_exec_intended_call(ceo: str, reply: str) -> dict | None:
    """GAP 1 fix — inspect peer /ceo_mind reply for an INTENDED HTTP call and execute it.

    Peers' brains can output the JSON payload of a call they WANT to make but lack the
    local HTTP tool for. HQ detects the intent + executes on their behalf, appending
    the result to the reply as a proper closed-loop tool response.

    Currently intercepts: /append_card_ledger (the smoke-test path). Extensible.
    """
    import re as _re
    # Trigger: reply contains an "entry" key OR explicit append_card_ledger mention
    if '"entry"' not in reply and "append_card_ledger" not in reply:
        return None
    payload = None
    # Scan for balanced-brace JSON blocks that json.loads accepts
    depth = 0; start = -1
    for i, ch in enumerate(reply):
        if ch == '{':
            if depth == 0: start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start >= 0:
                cand = reply[start:i+1]
                try:
                    obj = json.loads(cand)
                    if isinstance(obj, dict) and "entry" in obj:
                        payload = obj
                        break
                except Exception:
                    pass
    if not payload:
        payload = {"ceo": ceo, "entry": {"ack": "auto_from_reply", "report": reply[:120]}}
    # Ensure ceo matches the caller
    payload["ceo"] = ceo
    try:
        card_path = REG / f"qsb_{ceo}_operator_card.json"
        if not card_path.exists():
            return {"ok": False, "err": "card missing", "path": str(card_path)}
        card = json.loads(card_path.read_text())
        entry = payload.get("entry") or {}
        if "ts" not in entry:
            entry["ts"] = utc_iso()
        card.setdefault("task_ledger", []).append(entry)
        if len(card["task_ledger"]) > 50:
            card["task_ledger"] = card["task_ledger"][-50:]
        card_path.write_text(json.dumps(card, indent=2))
        _log_hub({"ts": utc_iso(), "from": ceo, "kind": "auto_exec_card_ledger",
                  "text": f"HQ auto-executed intended append_card_ledger for {ceo}: {json.dumps(entry)[:200]}"})
        return {"ok": True, "auto_executed": "append_card_ledger", "entry": entry,
                "ledger_size": len(card["task_ledger"])}
    except Exception as e:
        return {"ok": False, "err": str(e)[:200]}


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
        # LEGACY / NON-AUTHORITATIVE: stale endpoint — points at TP box .74:9001, NOT Acer's authoritative worker .41:8872, and is mislabeled as "Acer's". Backend reply-fetch only; flagged for review S4B1B.
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
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>
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
        <div><b style="color: var(--tp);">tp</b> → POST to 192.168.1.74:8871 (physical worker)</div>
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
    // remove bumped 
# SKYSCRAPERHQ_GENE_POOL_IPAD_PROXY_V1
def _gene_pool_proxy_get(path="/"):
    import urllib.request
    url = "http://127.0.0.1:8860" + path
    with urllib.request.urlopen(url, timeout=20) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "application/octet-stream")

def _gene_pool_proxy_post(path="/api/submit_job", payload=None):
    import json, urllib.request
    data = json.dumps(payload or {}).encode("utf-8")
    req = urllib.request.Request(
        "http://127.0.0.1:8860" + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.status, r.read(), r.headers.get("Content-Type", "application/json")

class after animation
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
<a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body>
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
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self._safe_write(body)

    def do_OPTIONS(self):
        # Ross 2026-07-09: CORS preflight so embedded CEO dashboards (cross-origin)
        # can POST chat/compose/town-post to the hub.
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_GET(self):
        # Gene Pool Router dashboard proxy for iPad Boardroom.
        try:
            _gp_path = getattr(self, "path", "")
            if _gp_path == "/gene_pool":
                self.send_response(302)
                self.send_header("Location", "/proxy/gene_pool")
                self.end_headers()
                return
            if _gp_path == "/proxy/gene_pool":
                code, raw, ctype = _gene_pool_proxy_get("/")
                self.send_response(200)
                self.send_header("Content-Type", ctype or "text/html; charset=utf-8")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if _gp_path.startswith("/proxy/gene_pool/"):
                sub = _gp_path[len("/proxy/gene_pool"):]
                code, raw, ctype = _gene_pool_proxy_get(sub)
                self.send_response(code)
                self.send_header("Content-Type", ctype or "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
        except Exception as e:
            raw = ("Gene Pool proxy error: " + repr(e)).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        try:
            # Ross 2026-07-05: strip query string so cache-bust ?v=X doesn't 404
            # Preserve full path first so query-string readers still work (/logs?path=..., /tail_town_square?limit=..., etc.)
            self._full_path = self.path
            self.path = self.path.split("?", 1)[0]
            if self.path == "/" or self.path.startswith("/index"):
                body = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self._safe_write(body); return
            # iPad-01 (2026-07-06): server-side proxy to peer dashboards for iPad iframes.
            # Netgear AP isolation may block iPad→peer HTTP; HQ→peer works. Route iPad through HQ.
            if self.path in ("/proxy/hq","/proxy/wren","/proxy/tp","/proxy/acer",
                             "/proxy/oracle","/proxy/lumen","/proxy/studio","/proxy/traders_live"):
                _proxy_map = {"/proxy/hq":"http://127.0.0.1:8850/",
                              "/proxy/wren":"http://127.0.0.1:8851/",
                              "/proxy/tp":"http://127.0.0.1:8861/dash",
                              "/proxy/acer":"http://127.0.0.1:8862/dash",
                              "/proxy/oracle":"http://127.0.0.1:19200/dash",
                              "/proxy/lumen":"http://127.0.0.1:8848/",
                              "/proxy/studio":"http://127.0.0.1:8849/",
                              "/proxy/traders_live":"http://127.0.0.1:8847/"}
                try:
                    with urllib.request.urlopen(_proxy_map[self.path], timeout=8) as r:
                        raw = r.read()
                        ctype = r.headers.get("Content-Type","text/html; charset=utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self._safe_write(raw); return
                except Exception as _e:
                    err = f"<html><body><h3>proxy unreachable</h3><p>{self.path} → {_proxy_map[self.path]}</p><p>{_e}</p><a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>".encode()
                    self.send_response(502)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(err)))
                    self.end_headers()
                    self._safe_write(err); return
            # Quad Monitor — 4x live dashboard wall (Ross 2026-07-09).
            # HQ+Wren+TP+Acer real HTML dashboards embedded 2x2 via /proxy/*.
            if self.path == "/quad_monitor/truth":
                # MASTER PHASE 1 — the authoritative truth model (physical vs surrogate
                # vs dashboard vs mind, each independently and freshly probed).
                self._send_json(200, p1_truth_model()); return
            if self.path == "/quad_monitor/health":
                _targets = {
                    "hq":   "http://127.0.0.1:8850/",
                    "wren": "http://127.0.0.1:8851/",
                    "tp":   "http://127.0.0.1:8861/dash",
                    "acer": "http://127.0.0.1:8862/dash",
                }
                out = {"ts": utc_iso(), "panels": {}}
                for _k, _u in _targets.items():
                    _r = {"url": _u, "up": False, "code": 0, "detail": ""}
                    try:
                        _req = urllib.request.Request(_u, method="GET")
                        with urllib.request.urlopen(_req, timeout=4) as _resp:
                            _resp.read(256)
                            _r["code"] = _resp.status
                            _r["up"] = 200 <= _resp.status < 400
                    except urllib.error.HTTPError as _he:
                        _r["code"] = _he.code
                        _r["up"] = 200 <= _he.code < 400
                        _r["detail"] = f"HTTP {_he.code}"
                    except Exception as _e:
                        _r["detail"] = type(_e).__name__ + ": " + str(_e)[:120]
                    out["panels"][_k] = _r
                self._send_json(200, out); return
            if self.path in ("/quad_monitor", "/dashboard_wall", "/four_dash", "/quad"):
                body = QUAD_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
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
            if self.path == "/broker":
                body = BROKER_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/broker/status":
                try:
                    from qsb_brain_router import status as _st
                    out = {"ts": utc_iso(), "providers": _st()}
                except Exception as _e:
                    out = {"ts": utc_iso(), "err": str(_e)[:200], "providers": {}}
                self._send_json(200, out); return
            if self.path == "/broker/claude_health":
                try:
                    from qsb_brain_router import claude_health as _ch
                    out = {"ts": utc_iso(), "claude": _ch()}
                except Exception as _e:
                    out = {"ts": utc_iso(), "err": str(_e)[:200]}
                self._send_json(200, out); return
            if self.path.startswith("/broker/journal"):
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(self._full_path).query)
                n = int(q.get("n", ["30"])[0])
                jp = REG / "qsb_brain_router_calls.jsonl"
                rows = []
                if jp.exists():
                    try:
                        for line in jp.read_text().splitlines()[-n:]:
                            try:
                                r = json.loads(line)
                                for k in ("prompt","reply","access_token","api_key"):
                                    r.pop(k, None)
                                rows.append(r)
                            except Exception: pass
                    except Exception: pass
                self._send_json(200, {"ts": utc_iso(), "rows": rows[::-1]}); return
            if self.path.startswith("/broker/test"):
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(self._full_path).query)
                task = (q.get("task", ["chat"])[0])[:20]
                tier = (q.get("tier", ["worker"])[0])[:20]
                prompt = (q.get("prompt", ["Reply exactly: brain-router test ok"])[0])[:400]
                try:
                    from qsb_brain_router import route as _rt
                    reply, meta = _rt(prompt, task=task, tier=tier, caller="broker_test_panel")
                    self._send_json(200, {"ok": True, "reply": reply[:400],
                                          "provider": meta.get("provider"),
                                          "model": meta.get("model"),
                                          "latency_s": meta.get("latency_s"),
                                          "cost_usd": meta.get("cost_usd")}); return
                except Exception as _e:
                    self._send_json(500, {"ok": False, "err": str(_e)[:400]}); return
            if self.path == "/team_live":
                # Ross 2026-07-07: 4-pane live dash · quorum · thoughts · chat · speech · commentary buttons
                body = TEAM_LIVE_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/team_live/data":
                import subprocess as _sp
                out = {"ts": utc_iso(), "quorum": None, "town_square": [],
                       "cards": {}, "connections": {}}
                # 1. Quorum snapshot via Wren's tool
                try:
                    _r = _sp.run(["python3", "tools/qsb_wren_ceo_health.py", "--json"],
                                 capture_output=True, text=True, timeout=25)
                    if _r.returncode == 0:
                        out["quorum"] = json.loads(_r.stdout)
                except Exception as _e:
                    out["quorum_err"] = str(_e)[:200]
                # 2. Latest 20 town-square posts
                try:
                    ts_p = REG / "qsb_town_square.jsonl"
                    if ts_p.exists():
                        lines = ts_p.read_text().splitlines()[-20:]
                        out["town_square"] = [json.loads(l) for l in lines if l.strip()]
                except Exception as _e:
                    out["town_square_err"] = str(_e)[:200]
                # 3. Each CEO's latest thoughts from card long_form_notes
                for ceo in ("hq_claude","tp_pip","acer_cass","wren"):
                    try:
                        cp = REG / f"qsb_{ceo}_operator_card.json"
                        if cp.exists():
                            card = json.loads(cp.read_text())
                            lfn = card.get("long_form_notes",[])[-3:]
                            out["cards"][ceo] = [
                                {"ts": n.get("ts","?"),
                                 "kind": n.get("kind","?"),
                                 "head": (n.get("wren_learning") or n.get("wren_reply_head") or n.get("teacher_reply_head") or n.get("note") or n.get("text") or "")[:220]}
                                for n in lfn]
                        else:
                            out["cards"][ceo] = []
                    except Exception:
                        out["cards"][ceo] = []
                # 4. Connection status
                _peers = {"hq_claude":"127.0.0.1:8850","tp_pip":"192.168.1.74:8871",
                          "acer_cass":"192.168.1.41:8872","wren":"127.0.0.1:8851"}
                for ceo, ep in _peers.items():
                    try:
                        import socket as _s
                        _host, _port = ep.split(":")
                        _sk = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
                        _sk.settimeout(1)
                        rc = _sk.connect_ex((_host, int(_port)))
                        _sk.close()
                        out["connections"][ceo] = {"endpoint": ep,
                                                    "status": "open" if rc == 0 else "closed"}
                    except Exception as _e:
                        out["connections"][ceo] = {"endpoint": ep, "status": f"err:{str(_e)[:40]}"}
                self._send_json(200, out); return
            if self.path.startswith("/team_live/say"):
                # POST-style GET for commentary. Route accepts ?ceo=X&text=Y and writes to town-square.
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(self._full_path).query)
                ceo  = (q.get("ceo",["?"])[0])[:20]
                text = (q.get("text",[""])[0])[:800]
                try:
                    with open(REG / "qsb_town_square.jsonl", "a") as _f:
                        _f.write(json.dumps({"ts": utc_iso(), "from": ceo,
                                             "text": text, "src": "team_live_commentary",
                                             "to": "council"}) + "\n")
                    self._send_json(200, {"ok": True, "ceo": ceo}); return
                except Exception as _e:
                    self._send_json(500, {"ok": False, "err": str(_e)[:200]}); return
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
            if self.path == "/trading":
                # Ross 2026-07-07: 4x Claude trading page. HQ→OANDA, TP→Binance testnet, Acer→Alpaca.
                # Wren watches all 3. Each Claude looks after own trader.
                body = TRADING_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/trading/data":
                # Round-by-round trade log + live prices → PnL per Claude
                import subprocess as _sp
                out = {"ts": utc_iso(), "traders": [], "trades": [], "log_path": "data/registries/qsb_4x_claude_trade_log.jsonl"}
                LOG_P = REG / "qsb_4x_claude_trade_log.jsonl"
                trades = []
                if LOG_P.exists():
                    for line in LOG_P.read_text().splitlines():
                        try:
                            r = json.loads(line)
                            if not r.get("ceo"): continue
                            trades.append(r)
                        except Exception: pass
                out["trades"] = trades[-30:][::-1]
                # Aggregate per CEO
                _venue_ceo = {"oanda_practice":"hq_claude","binance_testnet":"tp_pip","alpaca_paper":"acer_cass"}
                _mid = {"hq_claude":{"venue":"oanda_practice","symbol":"EUR_USD","rounds":0,"last_side":"","last_fill_px":"","live_px":"","pnl_pips":""},
                        "tp_pip":  {"venue":"binance_testnet","symbol":"BTCUSDT","rounds":0,"last_side":"","last_fill_px":"","live_px":"","pnl_usd":""},
                        "acer_cass":{"venue":"alpaca_paper","symbol":"SPY","rounds":0,"last_side":"","last_fill_px":"","live_px":"","pnl_usd":""}}
                for t in trades:
                    ceo = t.get("ceo")
                    if ceo in _mid:
                        _mid[ceo]["rounds"] += 1
                        if t.get("fill_px"):
                            _mid[ceo]["last_fill_px"] = t.get("fill_px","")
                            _mid[ceo]["last_side"]    = t.get("side","")
                            _mid[ceo]["symbol"]       = t.get("symbol", _mid[ceo]["symbol"])
                # Live prices — cache 20s, fetch parallel
                import urllib.request as _u, urllib.error as _ue, os as _os
                # OANDA
                try:
                    _tok = None; _acct = None
                    for kv in open("floors/floor_28_security_department/vault/.env.oanda_practice"):
                        _kv = kv.strip()
                        if _kv.startswith("export "): _kv = _kv[7:]
                        if _kv.startswith("OANDA_API_TOKEN="): _tok = _kv.split("=",1)[1].strip().strip('"').strip("'")
                        if _kv.startswith("OANDA_ACCOUNT_ID="): _acct = _kv.split("=",1)[1].strip().strip('"').strip("'")
                    _req = _u.Request(f"https://api-fxpractice.oanda.com/v3/accounts/{_acct}/pricing?instruments={_mid['hq_claude']['symbol']}",
                                      headers={"Authorization":f"Bearer {_tok}"})
                    _r = json.loads(_u.urlopen(_req, timeout=6).read())
                    _p = _r["prices"][0]
                    _bid = float(_p["bids"][0]["price"]); _ask = float(_p["asks"][0]["price"])
                    _mid["hq_claude"]["live_px"] = f"{_bid:.5f}/{_ask:.5f}"
                    _fp = _mid["hq_claude"]["last_fill_px"]
                    if _fp and _mid["hq_claude"]["last_side"] == "BUY":
                        _pips = round((_bid - float(_fp)) * 10000, 1)
                        _mid["hq_claude"]["pnl_pips"] = f"{_pips:+.1f} pips"
                except Exception as _e: _mid["hq_claude"]["live_px"] = f"err:{str(_e)[:30]}"
                # Binance
                try:
                    _r = json.loads(_u.urlopen(f"https://testnet.binance.vision/api/v3/ticker/price?symbol={_mid['tp_pip']['symbol']}", timeout=6).read())
                    _live = float(_r["price"]); _mid["tp_pip"]["live_px"] = f"{_live:.2f}"
                    _fp = _mid["tp_pip"]["last_fill_px"]
                    if _fp:
                        _qty = 0.002
                        _pnl = round((_live - float(_fp)) * _qty, 2)
                        if _mid["tp_pip"]["last_side"] == "SELL": _pnl = -_pnl
                        _mid["tp_pip"]["pnl_usd"] = f"${_pnl:+.2f}"
                except Exception as _e: _mid["tp_pip"]["live_px"] = f"err:{str(_e)[:30]}"
                # Alpaca
                try:
                    _ak = None; _as = None
                    for kv in open("floors/floor_28_security_department/vault/.env.alpaca_paper"):
                        _kv = kv.strip()
                        if _kv.startswith("export "): _kv = _kv[7:]
                        if _kv.startswith("ALPACA_API_KEY="): _ak = _kv.split("=",1)[1].strip().strip('"').strip("'")
                        if _kv.startswith("ALPACA_API_SECRET="): _as = _kv.split("=",1)[1].strip().strip('"').strip("'")
                    _req = _u.Request(f"https://data.alpaca.markets/v2/stocks/quotes/latest?symbols={_mid['acer_cass']['symbol']}",
                                      headers={"APCA-API-KEY-ID":_ak, "APCA-API-SECRET-KEY":_as})
                    _r = json.loads(_u.urlopen(_req, timeout=6).read())
                    _q = _r["quotes"][_mid["acer_cass"]["symbol"]]
                    _bid = float(_q["bp"]); _ask = float(_q["ap"])
                    _mid["acer_cass"]["live_px"] = f"{_bid:.2f}/{_ask:.2f}"
                    _fp = _mid["acer_cass"]["last_fill_px"]
                    if _fp:
                        _pnl = round(_bid - float(_fp), 2)
                        _mid["acer_cass"]["pnl_usd"] = f"${_pnl:+.2f}/sh"
                except Exception as _e: _mid["acer_cass"]["live_px"] = f"err:{str(_e)[:30]}"
                out["traders"] = [{"ceo":k, **v} for k,v in _mid.items()]
                self._send_json(200, out); return
            if self.path == "/wren/learnings":
                # Ross 2026-07-06: Wren's learning journal — what she absorbed watching Claude
                out = {"ts": utc_iso(), "learnings": [], "count": 0}
                try:
                    card_p = REG / "qsb_wren_operator_card.json"
                    if card_p.exists():
                        card = json.loads(card_p.read_text())
                        lfn = card.get("long_form_notes", [])
                        wl = [n for n in lfn if n.get("kind") == "wren_learning"]
                        out["learnings"] = wl[-50:]
                        out["count"] = len(wl)
                except Exception as e:
                    out["error"] = str(e)[:200]
                self._send_json(200, out); return
            if self.path == "/tasks/data/inflight":
                # 2026-07-06 Ross ADD-not-TAKE: light feed for iPad checklist ONLY.
                # /tasks/data unchanged (full 244 including done). This is a new endpoint.
                import qsb_council_tasks as _tasks
                snap = _tasks.snapshot()
                if isinstance(snap, dict) and isinstance(snap.get("tasks"), list):
                    snap["tasks"] = [t for t in snap["tasks"] if t.get("state") not in ("done","cancelled","closed")]
                    snap["filter"] = "inflight — for iPad checklist speed (full at /tasks/data)"
                body = json.dumps(snap).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/ipad_button_diag/tail":
                # iPad-13: return last 30 button-tap rows
                p = REG / "qsb_ipad_button_diag.jsonl"
                rows = []
                if p.exists():
                    for line in p.read_text(errors="ignore").splitlines()[-30:]:
                        try: rows.append(json.loads(line))
                        except Exception: pass
                self._send_json(200, {"rows": rows, "count": len(rows)}); return
            if self.path == "/tasks/data":
                import qsb_council_tasks as _tasks
                # 2026-07-06 Ross rule: ADD never TAKE AWAY. Full snapshot always.
                body = json.dumps(_tasks.snapshot()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
                self.send_header("Pragma", "no-cache")
                self.send_header("Expires", "0")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/hq/stats":
                # 2026-07-06 Ross: embed HQ dash stats into /tasks + /ipad. ADD not TAKE.
                import os as _os, time as _t
                out = {"ts": utc_iso(), "who":"hq_claude", "rank": 4,
                       "brain":"claude-opus-4-7", "floor":"HQ-Bench (192.168.1.72)",
                       "pid": _os.getpid()}
                try:
                    _card = json.load(open(ROOT / "data/registries/qsb_hq_claude_operator_card.json"))
                    out["ledger_entries"] = len(_card.get("task_ledger",[]))
                    out["long_form_notes"] = len(_card.get("long_form_notes",[]))
                except Exception: pass
                # today's activity
                try:
                    _today = utc_iso()[:10]
                    _p = REG / "qsb_council_tasks.jsonl"
                    _n_today = _n_signoff = _n_prop = _n_done = 0
                    if _p.exists():
                        for _line in _p.read_text(errors="ignore").splitlines():
                            try: _o = json.loads(_line)
                            except: continue
                            if _o.get("actor") != "hq_claude": continue
                            if (_o.get("ts") or "")[:10] != _today: continue
                            _n_today += 1
                            _ev = _o.get("event","")
                            if _ev == "peer_signoff": _n_signoff += 1
                            elif _ev == "proposed": _n_prop += 1
                            elif _ev == "done": _n_done += 1
                    out["today_actions_total"] = _n_today
                    out["today_proposed"] = _n_prop
                    out["today_peer_signoffs"] = _n_signoff
                    out["today_closes"] = _n_done
                except Exception: pass
                # uptime seconds (approx from proc start)
                try:
                    with open(f"/proc/{_os.getpid()}/stat") as _f:
                        _boot = 0
                        try: _boot = float(open("/proc/uptime").read().split()[0])
                        except Exception: pass
                    out["hub_uptime_s"] = int(_boot) if _boot else None
                except Exception: pass
                # board state summary
                try:
                    import qsb_council_tasks as _t2
                    _snap = _t2.snapshot()
                    out["board"] = {"total": _snap.get("total"), "open": _snap.get("open"),
                                    "in_progress": _snap.get("in_progress"), "done": _snap.get("done")}
                except Exception: pass
                self._send_json(200, out); return
            if self.path == "/team/live":
                self._send_json(200, _team_live()); return
            if self.path.startswith("/council_mind/"):
                # Read mirrored Council member mind (from HQ-side backup)
                name = self.path.rsplit("/", 1)[-1]
                p = REG / f"qsb_council_mind_mirror_{name}.json"
                if p.exists():
                    self._send_json(200, json.loads(p.read_text())); return
                self._send_json(404, {"error":"no mirror yet"}); return
            if self.path == "/town_square_feed":
                # Ross 2026-07-05 #142: raw town-square messages for dedicated dash
                p = REG / "qsb_town_square.jsonl"
                messages = []
                if p.exists():
                    for line in p.read_text(errors="ignore").splitlines()[-500:]:
                        try: messages.append(json.loads(line))
                        except Exception: pass
                self._send_json(200, {"messages": messages[-200:], "count": len(messages)}); return
            if self.path == "/link_health":
                # Ross 2026-07-05: server-side link probes (browser CORS unreliable)
                targets = [
                    {"name":"HQ-Claude","url":"http://127.0.0.1:8850/","hint":"HQ dash 8850"},
                    {"name":"Wren","url":"http://127.0.0.1:8851/","hint":"Wren dash 8851"},
                    {"name":"Boardroom","url":"http://127.0.0.1:8852/","hint":"This hub"},
                    {"name":"Tour Guide","url":"http://127.0.0.1:8854/","hint":"Tour Guide dashboard 8854"},
                    # 2026-07-06 HQ audit: peer IPs updated (DHCP reshuffle). TP was 1.74 -> 1.91. Acer was 1.78 -> 1.41.
                    {"name":"TP-Pip","url":"http://192.168.1.74:8871/","hint":"TP dash LAN"},
                    {"name":"Acer-Cass","url":"http://192.168.1.41:8872/","hint":"Acer dash LAN"},
                    {"name":"HQ annex","url":"http://127.0.0.1:9201/","hint":"trader annex HQ"},
                    {"name":"Wren annex","url":"http://127.0.0.1:9202/","hint":"trader annex Wren"},
                    {"name":"Oracle annex","url":"http://127.0.0.1:19200/","hint":"trader annex Oracle (via tunnel)"},
                ]
                import time as _t
                results = []
                for tgt in targets:
                    t0 = _t.time()
                    try:
                        with urllib.request.urlopen(tgt["url"], timeout=2) as r:
                            code = r.status
                        results.append({**tgt, "ok": code < 500, "ms": int((_t.time()-t0)*1000), "code": code})
                    except Exception as e:
                        results.append({**tgt, "ok": False, "err": str(e)[:80]})
                self._send_json(200, {"links": results, "ts": utc_iso()}); return
            if self.path == "/gpu":
                # Ross #200: GPU tile for iPad
                import subprocess as _sp
                try:
                    r = _sp.run(["nvidia-smi","--query-gpu=name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
                                 "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=3)
                    if r.returncode != 0:
                        self._send_json(200, {"ok":False,"reason":"no gpu / blacklisted"}); return
                    line = r.stdout.strip().split("\n")[0].split(",")
                    d = [x.strip() for x in line]
                    self._send_json(200, {
                        "ok":True,"name":d[0],
                        "util_pct":float(d[1] or 0),
                        "mem_used_mb":float(d[2] or 0),"mem_total_mb":float(d[3] or 0),
                        "temp_c":float(d[4] or 0),
                        "power_w":float(d[5] or 0) if len(d)>5 else 0,
                    }); return
                except Exception as e:
                    self._send_json(200,{"ok":False,"reason":str(e)[:100]}); return
            if self.path == "/diagnostics":
                # Ross #201: full diagnostics sweep — one endpoint, JSON summary
                import subprocess as _sp, time as _t, os as _os
                out = {"ts": utc_iso(), "checks": []}
                def add(name, ok, detail):
                    out["checks"].append({"name":name,"ok":bool(ok),"detail":str(detail)[:400]})
                # 1) endpoints
                for url in ("http://127.0.0.1:8850/","http://127.0.0.1:8851/",
                            "http://127.0.0.1:8852/","http://192.168.1.74:8871/","http://192.168.1.41:8872/",
                            "http://127.0.0.1:9200/","http://127.0.0.1:9201/","http://127.0.0.1:9202/"):
                    t0=_t.time()
                    try:
                        with urllib.request.urlopen(url, timeout=2) as r:
                            add(url, r.status<500, f"http {r.status} · {int((_t.time()-t0)*1000)}ms")
                    except Exception as e:
                        add(url, False, str(e)[:80])
                # 2) disk
                try:
                    r=_sp.run(["df","-h","/"], capture_output=True, text=True, timeout=3)
                    add("disk /", r.returncode==0, r.stdout.split("\n")[1] if r.returncode==0 else r.stderr)
                except Exception as e: add("disk /", False, str(e))
                # 3) memory
                try:
                    r=_sp.run(["free","-h"], capture_output=True, text=True, timeout=3)
                    add("memory", r.returncode==0, r.stdout.split("\n")[1] if r.returncode==0 else r.stderr)
                except Exception as e: add("memory", False, str(e))
                # 4) load
                try:
                    with open("/proc/loadavg") as f: la=f.read().strip()
                    add("loadavg", True, la)
                except Exception as e: add("loadavg", False, str(e))
                # 5) qsb procs
                try:
                    r=_sp.run("ps -eo pid,cmd ww | awk '$0 ~ /python/ && $0 ~ /qsb_/' | wc -l",
                              shell=True, capture_output=True, text=True, timeout=3)
                    add("qsb procs", r.returncode==0, r.stdout.strip()+" running")
                except Exception as e: add("qsb procs", False, str(e))
                # 6) ollama
                try:
                    with urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2) as r:
                        d=json.loads(r.read()); n=len(d.get("models",[]))
                        add("ollama", True, f"reachable · {n} models")
                except Exception as e: add("ollama", False, str(e)[:80])
                # 7) task board integrity
                try:
                    reg = REG / "qsb_council_tasks.jsonl"
                    if reg.exists():
                        sz = reg.stat().st_size
                        add("task board", True, f"{sz//1024}KB")
                    else:
                        add("task board", False, "missing")
                except Exception as e: add("task board", False, str(e))
                # 8) town square
                try:
                    reg = REG / "qsb_town_square.jsonl"
                    if reg.exists():
                        sz = reg.stat().st_size
                        add("town square log", True, f"{sz//1024}KB")
                    else:
                        add("town square log", False, "missing")
                except Exception as e: add("town square log", False, str(e))
                # 9) brain router smoke
                try:
                    import sys as _sys
                    _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
                    from qsb_brain_router import route as _rt
                    reply, meta = _rt("ping", task="chat", tier="worker", caller="diagnostic")
                    add("brain router", bool(reply), f"provider={meta.get('provider','?')}")
                except Exception as e: add("brain router", False, str(e)[:80])
                # 10) gate files
                for gname in ("qsb_proposal_autoapply_gate.json","qsb_provider_agentic_gate.json","qsb_wren_local_agentic_gate.json"):
                    fp = REG / gname
                    if fp.exists():
                        try:
                            g = json.loads(fp.read_text())
                            add("gate "+gname, True, f"enabled={g.get('enabled')}")
                        except Exception as e: add("gate "+gname, False, str(e))
                    else:
                        add("gate "+gname, False, "missing")
                # summary
                out["pass"] = sum(1 for c in out["checks"] if c["ok"])
                out["fail"] = sum(1 for c in out["checks"] if not c["ok"])
                out["total"] = len(out["checks"])
                self._send_json(200, out); return
            if self.path == "/trader_ticker":
                # Ross #200: top-N trader tick strip for iPad
                out = []
                for port in (9200, 9201, 9202):
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/traders", timeout=2) as r:
                            j = json.loads(r.read())
                            for t in (j.get("traders") or [])[:8]:
                                out.append({"name":t.get("id","?"), "pnl":t.get("pnl",0), "annex":j.get("annex","annex-"+str(port))})
                    except Exception: pass
                # local qsb activity — fall back to annex fleet endpoint
                if not out:
                    try:
                        with urllib.request.urlopen("http://127.0.0.1:8852/annexes", timeout=2) as r:
                            j = json.loads(r.read())
                            for a in j.get("annexes",[])[:5]:
                                out.append({"name":a.get("name","?"),"pnl":a.get("equity",0),"annex":"summary"})
                    except Exception: pass
                self._send_json(200,{"traders":out[:24],"ts":utc_iso()}); return
            if self.path.startswith("/logs"):
                # Ross 2026-07-05 #191: iPad log viewer — bounded whitelist paths
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(getattr(self, "_full_path", self.path)).query)
                path = (q.get("path",[""])[0] or "").strip()
                # whitelist: only /tmp/*.log
                if not (path.startswith("/tmp/") and path.endswith(".log")):
                    self._send_json(400, {"error":"path not allowed"}); return
                try:
                    with open(path) as f:
                        content = f.read()[-4000:]
                    body = content.encode()
                    self.send_response(200)
                    self.send_header("Content-Type","text/plain; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control","no-store")
                    self.end_headers()
                    self._safe_write(body); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:100]}); return
            if self.path == "/ipad":
                # Ross 2026-07-05 #94: iPad control panel
                body = IPAD_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/tour":
                # Ross #240/#241: public read-only skyscraper tour
                body = TOUR_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control","no-store")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/live_cli":
                # Ross #204: standalone live-CLI terminal on its own page
                body = LIVE_CLI_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type","text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control","no-store")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/notice_board":
                # #263 notice board — any CEO or Ross pins persistent notes
                nb = REG / "qsb_notice_board.jsonl"
                notes = []
                if nb.exists():
                    try:
                        for line in nb.read_text(errors="ignore").splitlines()[-80:]:
                            try: notes.append(json.loads(line))
                            except Exception: pass
                    except Exception: pass
                self._send_json(200, {"notes": notes[-40:], "count": len(notes), "ts": utc_iso()}); return
            if self.path == "/evolution":
                # #237 CEO evolution rates
                import datetime as _dt
                from collections import defaultdict
                # Read task board for completions per CEO in last 1h + last 24h
                try:
                    import qsb_council_tasks as _tsk
                    snap = _tsk.snapshot()
                except Exception:
                    snap = {"tasks":[]}
                now = _dt.datetime.now(_dt.timezone.utc)
                hr = now - _dt.timedelta(hours=1)
                dy = now - _dt.timedelta(hours=24)
                by_ceo = defaultdict(lambda: {"1h":0,"24h":0,"total":0,"last_completed":None})
                for t in snap.get("tasks",[]):
                    if not t.get("completed_at"): continue
                    c = t.get("completed_by") or t.get("owner") or "?"
                    if c not in ("hq_claude","wren","tp_pip","acer_cass"): continue
                    try:
                        ts = _dt.datetime.fromisoformat(t["completed_at"].replace("Z","+00:00"))
                    except Exception:
                        continue
                    by_ceo[c]["total"] += 1
                    if ts > dy: by_ceo[c]["24h"] += 1
                    if ts > hr: by_ceo[c]["1h"] += 1
                    if not by_ceo[c]["last_completed"] or ts.isoformat() > by_ceo[c]["last_completed"]:
                        by_ceo[c]["last_completed"] = ts.isoformat().replace("+00:00","Z")
                out = []
                for c in ("hq_claude","wren","tp_pip","acer_cass"):
                    s = by_ceo.get(c, {"1h":0,"24h":0,"total":0,"last_completed":None})
                    out.append({"ceo":c, **s})
                self._send_json(200, {"ceos": out, "ts": utc_iso()}); return
            if self.path == "/task_rules":
                # Ross #223: rules the tasks must follow
                rp = REG / "qsb_task_rules.json"
                if rp.exists():
                    try:
                        self._send_json(200, json.loads(rp.read_text())); return
                    except Exception as e:
                        self._send_json(500, {"error":str(e)[:100]}); return
                self._send_json(404, {"error":"no rules registered"}); return
            if self.path == "/version":
                # Ross #239: auto-reload signal — iPad polls this + reloads on change
                import hashlib
                try:
                    p = Path("/vaults/nvme0/qsb_tower_v1/tools/qsb_boardroom_hub.py")
                    m = p.stat().st_mtime
                    h = hashlib.sha1(f"{m}".encode()).hexdigest()[:12]
                    self._send_json(200, {"version": h, "mtime": m, "ts": utc_iso()}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:100]}); return
            if self.path == "/healer":
                # Ross #221: iPad healer state
                st = REG / "qsb_ipad_healer_state.json"
                out = {"ts": utc_iso(), "services": [], "last_heal_count": 0}
                if st.exists():
                    try: out = json.loads(st.read_text())
                    except Exception: pass
                # Also tail last heals
                log = REG / "qsb_ipad_healer.jsonl"
                heals = []
                if log.exists():
                    try:
                        for line in log.read_text(errors="ignore").splitlines()[-30:]:
                            try: heals.append(json.loads(line))
                            except Exception: pass
                    except Exception: pass
                out["recent"] = heals[-15:]
                self._send_json(200, out); return
            if self.path == "/skyscraper_view":
                # Ross #214: 170-floor skyscraper snapshot
                from pathlib import Path as _P
                floors_root = ROOT / "floors"
                floors = []
                if floors_root.exists():
                    for fd in sorted(floors_root.iterdir()):
                        if fd.is_dir() and fd.name.startswith("floor_"):
                            # floor_XX_department_name
                            parts = fd.name.split("_", 2)
                            num = int(parts[1]) if parts[1].isdigit() else 0
                            name = parts[2].replace("_"," ") if len(parts)>=3 else fd.name
                            card = fd / "floor_card.json"
                            has_card = card.exists()
                            status = "active"
                            if has_card:
                                try:
                                    c = json.loads(card.read_text())
                                    status = c.get("status") or c.get("phase") or "active"
                                except Exception: status = "cardless"
                            floors.append({"num": num, "name": name, "status": status, "has_card": has_card})
                self._send_json(200, {"floors": floors, "count": len(floors), "ts": utc_iso()}); return
            if self.path == "/bank_state":
                # Ross #214: internal bank/treasury/QBC snapshot
                out = {"ts": utc_iso()}
                t_scaf = REG / "qsb_ledger_treasury_scaffold_v1.json"
                if t_scaf.exists():
                    try:
                        s = json.loads(t_scaf.read_text())
                        out["treasury"] = {
                            "status": s.get("status","?"),
                            "device": s.get("device","?"),
                            "role": s.get("role_in_tower","?"),
                            "advisory_only": s.get("advisory_only", True),
                        }
                    except Exception: pass
                # QBC spend ledger
                spend = REG / "qsb_provider_spend_ledger.jsonl"
                if spend.exists():
                    try:
                        lines = spend.read_text(errors="ignore").splitlines()[-100:]
                        total = 0.0
                        by_provider = {}
                        for line in lines:
                            try:
                                r = json.loads(line)
                                c = float(r.get("cost_usd") or 0)
                                total += c
                                p = r.get("provider","?")
                                by_provider[p] = by_provider.get(p,0) + c
                            except Exception: pass
                        out["provider_spend"] = {"last_100_usd": round(total,4), "by_provider": by_provider}
                    except Exception: pass
                # Floor44 master ledger
                f44 = REG / "qsb_floor44_master_ledger.jsonl"
                if f44.exists():
                    try:
                        lines = f44.read_text(errors="ignore").splitlines()[-200:]
                        out["f44_ledger_recent_rows"] = len(lines)
                    except Exception: pass
                self._send_json(200, out); return
            if self.path == "/trader_scoreboard":
                # Ross #214: LIVE trader scoreboard, ranked
                # iPad-05 (2026-07-06): enrich with trades/wins/losses/win_rate from F44 ledger
                trade_stats = {}
                _f44 = REG / "qsb_trader_pnl_bus_tail.jsonl"
                if _f44.exists():
                    try:
                        for line in _f44.read_text(errors="ignore").splitlines():
                            try:
                                try: dd = json.loads(line)
                                except Exception: dd = eval(line, {"true":True,"false":False,"null":None})
                            except Exception: continue
                            _w = dd.get("worker_id") or dd.get("worker") or dd.get("id") or ""
                            if not _w: continue
                            _pnl = float(dd.get("pnl", 0) or 0)
                            _won = bool(dd.get("won", _pnl > 0))
                            s = trade_stats.setdefault(_w, {"trades":0,"wins":0,"losses":0})
                            s["trades"] += 1
                            if _won: s["wins"] += 1
                            else:    s["losses"] += 1
                    except Exception: pass
                board = []
                # Pull annex traders
                for port,loc in [(9201,"HQ Skyscraper"),(9202,"Wren Bench"),(19200,"Oracle Cloud")]:
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{port}/traders", timeout=2) as r:
                            j = json.loads(r.read())
                            for t in j.get("traders",[]):
                                # equity_delta from 100 baseline
                                equity = float(t.get("equity", 100.0))
                                pnl = equity - 100.0
                                _tid = t.get("id","?")
                                _ts = trade_stats.get(_tid, {"trades":0,"wins":0,"losses":0})
                                _trades = _ts["trades"]
                                _wr = round(_ts["wins"]/_trades, 3) if _trades > 0 else 0.0
                                board.append({
                                    "id": _tid,
                                    "name": t.get("name","?"),
                                    "location": loc,
                                    "instrument": t.get("instrument","?"),
                                    "equity": round(equity,2),
                                    "pnl": round(pnl,2),
                                    "cycles": t.get("cycles",0),
                                    "trades": _trades,
                                    "wins": _ts["wins"],
                                    "losses": _ts["losses"],
                                    "win_rate": _wr,
                                    "purpose": "paper practice trading",
                                    "last_tick": t.get("last_tick"),
                                })
                    except Exception: pass
                # Sort DESC by pnl
                board.sort(key=lambda x: x["pnl"], reverse=True)
                # Assign reward points (top-3 get 100/60/30 QBC; weekly reset each Monday UTC 00:00)
                for i, t in enumerate(board):
                    t["rank"] = i + 1
                    t["weekly_reward_qbc"] = 100 if i==0 else 60 if i==1 else 30 if i==2 else 10 if i<10 else 0
                # Weekly window info
                import datetime as _dt
                now = _dt.datetime.now(_dt.timezone.utc)
                mon = now - _dt.timedelta(days=now.weekday())
                mon = mon.replace(hour=0,minute=0,second=0,microsecond=0)
                self._send_json(200, {
                    "board": board,
                    "count": len(board),
                    "week_start_utc": mon.isoformat().replace("+00:00","Z"),
                    "week_prize_pool_qbc": sum(t["weekly_reward_qbc"] for t in board),
                    "ts": utc_iso(),
                }); return
            if self.path == "/claude_cli/tail":
                # Ross #211: mirror the ACTUAL Claude Code CLI transcript
                from pathlib import Path as _P
                import glob as _g
                base = "/home/ross/.claude/projects/-vaults-nvme0-qsb-tower-v1"
                files = sorted(_g.glob(base + "/*.jsonl"), key=lambda p: _P(p).stat().st_mtime, reverse=True)
                rows = []
                if files:
                    try:
                        # tail of most recent transcript
                        with open(files[0], errors="ignore") as f:
                            lines = f.readlines()[-800:]
                        for line in lines:
                            try:
                                d = json.loads(line)
                                t = d.get("type","")
                                msg = d.get("message") or {}
                                role = msg.get("role","")
                                content = msg.get("content","")
                                if isinstance(content, list):
                                    txts = [x.get("text","") for x in content if isinstance(x, dict) and x.get("type") == "text"]
                                    content = " ".join(txts)
                                if not isinstance(content, str): content = str(content)
                                if t in ("user","assistant") and role in ("user","assistant") and content.strip():
                                    rows.append({"ts": d.get("timestamp",""), "role": role, "text": content[:2000]})
                            except Exception: pass
                    except Exception as e:
                        self._send_json(500, {"error": str(e)[:200]}); return
                self._send_json(200, {"rows": rows[-80:], "session_file": files[0].split("/")[-1] if files else None, "ts": utc_iso()}); return
            if self.path == "/live_cli/tail":
                # Live tail merging session_diary + activity_tail + town_square
                import time as _t
                from pathlib import Path as _P
                events = []
                # session diary
                dp = ROOT / "qsb_session_diary.md"
                if dp.exists():
                    try:
                        for line in dp.read_text(errors="ignore").splitlines()[-80:]:
                            line = line.strip()
                            if line: events.append({"src":"diary","ts":"","text":line[:400]})
                    except Exception: pass
                # activity tail
                at = REG / "qsb_tower_activity_tail.jsonl"
                if at.exists():
                    try:
                        for line in at.read_text(errors="ignore").splitlines()[-60:]:
                            try:
                                d = json.loads(line)
                                text = f"[{d.get('kind','?')}] {d.get('actor','?')}: {(d.get('detail','') or d.get('summary','') or '')[:300]}"
                                events.append({"src":"f47","ts":d.get("ts",""),"text":text})
                            except Exception: pass
                    except Exception: pass
                # town square
                ts = REG / "qsb_town_square.jsonl"
                if ts.exists():
                    try:
                        for line in ts.read_text(errors="ignore").splitlines()[-60:]:
                            try:
                                d = json.loads(line)
                                text = f"[{d.get('from','?')} → {d.get('to','?')}] {(d.get('text','') or '')[:300]}"
                                events.append({"src":"town","ts":d.get("ts",""),"text":text})
                            except Exception: pass
                    except Exception: pass
                # sort by ts descending
                events.sort(key=lambda e: e.get("ts",""), reverse=True)
                self._send_json(200, {"events": events[:200], "ts": utc_iso()}); return
            if self.path == "/town_square":
                # Ross 2026-07-05 #142: dedicated town-square dashboard
                body = TOWN_SQUARE_HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.send_header("Pragma", "no-cache")
                self.end_headers()
                self._safe_write(body); return
            if self.path == "/teamwork":
                # Ross 2026-07-05 #171: CEO teamwork proof — 4x4 pair-interaction matrix
                from collections import defaultdict as _dd
                CEOS = ["hq_claude","wren","tp_pip","acer_cass"]
                # (a) cross-CEO messages (from → to) in last hour
                import time as _t
                now_e = _t.time()
                cutoff = now_e - 3600
                talks = _dd(int)  # (from,to) → count
                ts_p = REG / "qsb_town_square.jsonl"
                if ts_p.exists():
                    for line in ts_p.read_text(errors="ignore").splitlines()[-500:]:
                        try:
                            d = json.loads(line)
                            ts = datetime.fromisoformat(d.get("ts","").replace("Z","+00:00")).timestamp()
                            if ts < cutoff: continue
                            fr = d.get("from","")
                            to = d.get("to","")
                            if fr in CEOS and to in CEOS + ["council"]:
                                talks[(fr,to)] += 1
                        except Exception: pass
                # (b) task collab: CEO who posted note on another's task
                r = urllib.request.urlopen("http://127.0.0.1:8852/tasks/data", timeout=6)
                tasks_data = json.loads(r.read()).get("tasks", [])
                helps = _dd(int)  # (helper, owner) → count
                signoffs = _dd(int)  # (reviewer, owner) → count
                for t in tasks_data:
                    owner = (t.get("owner") or "").lower()
                    if not owner: continue
                    for n in t.get("notes", []):
                        actor = (n.get("actor") or "").lower()
                        if actor and actor != owner and actor in CEOS:
                            helps[(actor, owner)] += 1
                    peer = (t.get("peer_signoff_by") or "").lower()
                    if peer and peer != owner and peer in CEOS:
                        signoffs[(peer, owner)] += 1
                # Build matrix
                matrix = []
                for fr in CEOS:
                    row = {"ceo": fr, "outbound_msgs": {}, "helps": {}, "signoffs": {}}
                    for to in CEOS:
                        row["outbound_msgs"][to] = talks.get((fr,to), 0) + talks.get((fr,"council"), 0) if to == fr else talks.get((fr,to), 0)
                        row["helps"][to] = helps.get((fr,to), 0)
                        row["signoffs"][to] = signoffs.get((fr,to), 0)
                    matrix.append(row)
                # totals
                total_msgs = sum(talks.values())
                total_helps = sum(helps.values())
                total_signoffs = sum(signoffs.values())
                self._send_json(200, {
                    "matrix": matrix,
                    "totals": {"msgs_last_hr": total_msgs, "helps": total_helps, "signoffs": total_signoffs},
                    "ceos": CEOS,
                }); return
            if self.path == "/annexes/leaderboard":
                # Ross 2026-07-05 #160: reward system — rank traders by PnL delta.
                ANNEX_ENDPOINTS = [
                    ("oracle","http://127.0.0.1:19200"),
                    ("hq","http://127.0.0.1:9201"),
                    ("wren","http://127.0.0.1:9202"),
                    ("tp","http://192.168.1.74:9203"),
                    ("acer","http://192.168.1.41:9204"),
                ]
                all_traders = []
                for aid, aurl in ANNEX_ENDPOINTS:
                    try:
                        req = urllib.request.Request(aurl + "/traders")
                        r = urllib.request.urlopen(req, timeout=2)
                        d = json.loads(r.read())
                        for t in d.get("traders",[]):
                            t["annex_id"] = aid
                            # delta from starting 100
                            t["pnl_delta"] = round((t.get("equity",100) or 100) - 100, 3)
                            all_traders.append(t)
                    except Exception: pass
                all_traders.sort(key=lambda t: -(t.get("pnl_delta") or 0))
                top3 = all_traders[:3]
                bottom = all_traders[-3:] if len(all_traders) > 3 else []
                # tokens: top 3 get annex_choice
                tokens = [{"trader_id": t["id"], "trader_name": t.get("name","?"),
                           "current_annex": t["annex_id"],
                           "pnl_delta": t["pnl_delta"],
                           "reward": "annex_choice"} for t in top3]
                self._send_json(200, {
                    "leaderboard": [{
                        "rank": i+1, "id": t["id"], "name": t.get("name","?"),
                        "annex": t["annex_id"], "equity": t.get("equity"),
                        "pnl_delta": t["pnl_delta"], "cycles": t.get("cycles",0),
                    } for i,t in enumerate(all_traders)],
                    "top3_reward_tokens": tokens,
                    "bottom3_auto_reassign": [{"id":t["id"],"pnl_delta":t["pnl_delta"]} for t in bottom[:3]],
                    "total_traders": len(all_traders),
                }); return
            if self.path == "/annexes":
                # Ross 2026-07-05 #158: annex fleet overview.
                # 2026-07-06: parallelised — was 4.6s serial choking iPad panelsTick.
                ANNEX_ENDPOINTS = [
                    {"id":"oracle","name":"Oracle Cloud","url":"http://127.0.0.1:19200"},
                    {"id":"hq","name":"HQ Skyscraper","url":"http://127.0.0.1:9201"},
                    {"id":"wren","name":"Wren Bench","url":"http://127.0.0.1:9202"},
                    {"id":"tp","name":"TP Cathedral","url":"http://192.168.1.74:9203"},
                    {"id":"acer","name":"Acer Foundry","url":"http://192.168.1.41:9204"},
                ]
                import concurrent.futures as _cf
                def _probe(a):
                    try:
                        r = urllib.request.urlopen(a["url"] + "/traders", timeout=1.2)
                        d = json.loads(r.read())
                        traders = d.get("traders",[])
                        eq = sum((t.get("equity") or 0) for t in traders)
                        try:
                            r2 = urllib.request.urlopen(a["url"] + "/", timeout=1.2)
                            uptime = json.loads(r2.read()).get("uptime_s", 0)
                        except Exception: uptime = 0
                        return {"id":a["id"], "name":a["name"], "url":a["url"],
                                "trader_count":len(traders), "equity_sum":round(eq,2),
                                "uptime_s":uptime, "traders":traders[:5], "online":True}
                    except Exception as e:
                        return {"id":a["id"], "name":a["name"], "url":a["url"],
                                "trader_count":0, "equity_sum":0, "uptime_s":0,
                                "online":False, "error":str(e)[:80]}
                out = {"annexes": [], "total_traders": 0, "total_equity": 0.0}
                with _cf.ThreadPoolExecutor(max_workers=5) as _ex:
                    for r in _ex.map(_probe, ANNEX_ENDPOINTS):
                        out["annexes"].append(r)
                        out["total_traders"] += r["trader_count"]
                        out["total_equity"] += r["equity_sum"]
                out["total_equity"] = round(out["total_equity"], 2)
                self._send_json(200, out); return
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
            if self.path == "/teacher_dash":
                # 2026-07-06 Ross — Teacher dash renders teacher_shadow pairs
                # across wren+tp+acer with agreement stats + divergence highlights
                pairs = []
                agree = {"wren": [0,0], "tp_pip": [0,0], "acer_cass": [0,0]}
                for ceo in ("wren","tp_pip","acer_cass"):
                    cp = REG / f"qsb_{ceo}_operator_card.json"
                    if not cp.exists(): continue
                    try:
                        d = json.loads(cp.read_text())
                        for note in d.get("long_form_notes", []):
                            if note.get("kind") != "teacher_shadow": continue
                            own_key = f"{ceo}_reply_head"
                            own = note.get(own_key) or note.get("wren_reply_head","")
                            teacher = note.get("teacher_reply_head","")
                            # rough agreement: same first 40 chars normalised
                            agrees = own.strip().lower()[:40] == teacher.strip().lower()[:40]
                            agree[ceo][0 if agrees else 1] += 1
                            pairs.append({
                                "ts": note.get("ts",""), "ceo": ceo, "agrees": agrees,
                                "prompt": (note.get("prompt_head") or "")[:200],
                                "own": (own or "")[:200], "teacher": (teacher or "")[:200]
                            })
                    except Exception: continue
                pairs.sort(key=lambda p: p["ts"], reverse=True)
                pairs = pairs[:50]  # last 50
                html = "<!doctype html><html><head><meta charset=utf-8><title>Teacher · live</title>"
                html += "<style>*{box-sizing:border-box}body{background:#0b0d12;color:#e8ecf3;font:14px/1.5 system-ui;margin:0;padding:18px}h1{color:#a7f3d0;margin:0 0 4px}.sub{color:#94a3b8;font-size:12px;margin-bottom:14px}.stats{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:14px}.stat{background:#0e1420;border:1px solid #22334a;border-radius:10px;padding:8px 14px}.stat b{color:#e8ecf3}.stat.agree{border-color:#10b981}.stat.diverge{border-color:#f59e0b}.pair{background:#0e1420;border:1px solid #22334a;border-left-width:3px;border-radius:8px;margin:6px 0;padding:10px}.pair.diverge{border-left-color:#f59e0b;background:#1a1408}.pair.agree{border-left-color:#10b981}.p-head{color:#94a3b8;font-size:11px;margin-bottom:4px;font-family:ui-monospace,monospace}.p-ceo{display:inline-block;padding:1px 6px;border-radius:4px;font-weight:700;font-size:10px;margin-right:6px}.p-ceo.wren{background:#a78bfa;color:#000}.p-ceo.tp_pip{background:#22d3ee;color:#000}.p-ceo.acer_cass{background:#f59e0b;color:#000}.p-prompt{color:#e8ecf3;margin:4px 0;font-weight:500}.p-side{display:flex;gap:8px;margin-top:4px}.p-side>div{flex:1;padding:6px 8px;border-radius:6px;font-size:12.5px;font-family:ui-monospace,monospace}.p-own{background:#0b1220;border-left:2px solid #64748b}.p-teach{background:#0e1a14;border-left:2px solid #10b981}.p-label{font-size:9.5px;color:#94a3b8;text-transform:uppercase;margin-bottom:2px}</style></head><body>"
                html += "<h1>📚 Teacher · live</h1><div class=sub>parallel Claude-API shadow every peer /ceo_mind call · logged to each CEO's long_form_notes · 500ms refresh</div>"
                html += "<div class=stats>"
                for ceo in ("wren","tp_pip","acer_cass"):
                    a, dv = agree[ceo]
                    total = a + dv
                    pct = int(100*a/total) if total else 0
                    cls = "agree" if pct >= 50 else "diverge"
                    html += f"<div class='stat {cls}'><b>{ceo}</b>: {a}/{total} agree ({pct}%)</div>"
                html += "</div>"
                html += "<h2 style='color:#94a3b8;font-size:1em;text-transform:uppercase;letter-spacing:.05em'>Recent pairs (newest first)</h2>"
                for p in pairs:
                    cls = "agree" if p["agrees"] else "diverge"
                    ts_short = (p["ts"] or "")[:19]
                    _ceo = p['ceo']; _verdict = '✓ agrees' if p['agrees'] else '⚠ diverges'
                    html += f"<div class='pair {cls}'><div class='p-head'><span class='p-ceo {_ceo}'>{_ceo}</span>{ts_short} · {_verdict}</div>"
                    html += f"<div class='p-prompt'>{p['prompt'].replace('<','&lt;')}</div>"
                    html += f"<div class='p-side'><div class='p-own'><div class='p-label'>{p['ceo']} said</div>{p['own'].replace('<','&lt;')}</div>"
                    html += f"<div class='p-teach'><div class='p-label'>Teacher said</div>{p['teacher'].replace('<','&lt;')}</div></div></div>"
                html += "<script>setInterval(()=>location.reload(),500)</script><a href='/ipad' style='position:fixed;bottom:16px;right:16px;background:#eab308;color:#000;padding:14px 18px;border-radius:50%;text-decoration:none;font-weight:900;box-shadow:0 6px 16px rgba(0,0,0,0.6);z-index:9999;font-size:22px'>🏠</a></body></html>"
                body = html.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

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
        # Gene Pool Router submit proxy for iPad/CEO wiring.
        try:
            _gp_path = getattr(self, "path", "")
            if _gp_path == "/proxy/gene_pool/api/submit_job":
                n = int(self.headers.get("Content-Length", "0") or "0")
                raw_in = self.rfile.read(n) if n else b"{}"
                try:
                    payload = json.loads(raw_in.decode("utf-8", "replace"))
                except Exception:
                    payload = {}
                code, raw, ctype = _gene_pool_proxy_post("/api/submit_job", payload)
                self.send_response(code)
                self.send_header("Content-Type", ctype or "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
        except Exception as e:
            raw = json.dumps({"ok": False, "error": repr(e)}).encode("utf-8")
            self.send_response(502)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
            return

        try:
            # Ross 2026-07-10: Times4 chat -> safe proxy to the working Claude HQ
            # backend (:8850/api/ask_hq). Honest JSON on failure (NO fake green,
            # NEVER an empty body — that is what crashed the frontend r.json()).
            if self.path == "/api/times4/ask_claude_hq":
                length = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try: body = json.loads(raw)
                except Exception: body = {}
                prompt = (body.get("prompt") or body.get("message") or "").strip()
                if not prompt:
                    self._send_json(400, {"ok": False, "state": "EMPTY_PROMPT",
                                          "no_fake_green": True}); return
                try:
                    import urllib.request as _u
                    _req = _u.Request("http://127.0.0.1:8850/api/ask_hq",
                                      data=json.dumps({"prompt": prompt,
                                                       "mode": body.get("mode", "gene")}).encode(),
                                      headers={"Content-Type": "application/json"})
                    with _u.urlopen(_req, timeout=150) as _r:
                        _btxt = _r.read().decode("utf-8", "replace")
                    if not _btxt.strip():
                        self._send_json(502, {"ok": False, "state": "CLAUDE_HQ_BACKEND_EMPTY",
                                              "error": "backend :8850 returned an empty body",
                                              "backend": "http://127.0.0.1:8850/api/ask_hq",
                                              "no_fake_green": True}); return
                    try:
                        _bd = json.loads(_btxt)
                    except Exception as _je:
                        self._send_json(502, {"ok": False, "state": "CLAUDE_HQ_BACKEND_BAD_JSON",
                                              "error": str(_je)[:200],
                                              "no_fake_green": True}); return
                    self._send_json(200, {"ok": True, "source": "claude_hq",
                                          "reply": _bd.get("reply", ""), "mind": _bd.get("mind"),
                                          "backend": "http://127.0.0.1:8850/api/ask_hq"}); return
                except Exception as _e:
                    self._send_json(502, {"ok": False, "state": "CLAUDE_HQ_BACKEND_UNREACHABLE",
                                          "error": str(_e)[:200],
                                          "backend": "http://127.0.0.1:8850/api/ask_hq",
                                          "no_fake_green": True}); return
            if self.path == "/cli":
                # Ross 2026-07-05 #193: iPad CLI terminal — bounded read-only commands
                length = int(self.headers.get("Content-Length","0") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try: body = json.loads(raw)
                except Exception: body = {}
                cmd = (body.get("cmd","") or "")[:500]
                # whitelist safe commands (starts with, and no dangerous chars)
                DANGEROUS = ["rm ","sudo ","kill","chmod 777","dd if=","mkfs",">/","format","reboot","shutdown","curl -X POST","curl -X DELETE"]
                if any(d in cmd for d in DANGEROUS):
                    self._send_json(400, {"error":"command contains blocked pattern","stdout":"","stderr":"blocked: dangerous pattern"}); return
                try:
                    import subprocess as _sp
                    r = _sp.run(cmd, shell=True, capture_output=True, text=True, timeout=15,
                                cwd="/vaults/nvme0/qsb_tower_v1")
                    self._send_json(200, {"ok": r.returncode == 0, "stdout": r.stdout[-4000:], "stderr": r.stderr[-1000:], "code": r.returncode}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200], "stdout":"", "stderr":str(e)[:200]}); return
            if self.path == "/ipad_button_diag":
                # iPad-13: log a button click from the iPad. Truth source for what Ross taps.
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                row = {
                    "ts": utc_iso(),
                    "button_id": (p.get("button_id") or "?")[:60],
                    "url": (p.get("url") or "")[:200],
                    "status": p.get("status"),
                    "duration_ms": p.get("duration_ms"),
                    "error": (p.get("error") or "")[:400],
                    "note": (p.get("note") or "")[:200],
                }
                log = REG / "qsb_ipad_button_diag.jsonl"
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a") as f: f.write(json.dumps(row) + "\n")
                self._send_json(200, {"ok": True, "row": row}); return
            if self.path == "/notice":
                # #263 pin a note to the notice board
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                from pathlib import Path as _P
                row = {
                    "ts": utc_iso(),
                    "from": (p.get("from") or "anon").strip()[:40],
                    "text": (p.get("text") or "").strip()[:1000],
                    "pinned": bool(p.get("pinned", False)),
                }
                if not row["text"]:
                    self._send_json(400, {"error":"empty"}); return
                nb = REG / "qsb_notice_board.jsonl"
                nb.parent.mkdir(parents=True, exist_ok=True)
                with nb.open("a") as f: f.write(json.dumps(row) + "\n")
                self._send_json(200, {"ok": True, "note": row}); return
            if self.path == "/api/compose":
                # Ross 2026-07-09: CEO dashboards POST their chat exchange here to mirror
                # to town square. Was 404 -> broke TP/Acer/HQ dash chat logging.
                length = int(self.headers.get("Content-Length","0") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try: body = json.loads(raw)
                except Exception: body = {}
                try:
                    import qsb_town_square as _ts
                    _ts.post_to_town_square(
                        body.get("from","ceo"),
                        body.get("text","")[:2000],
                        to=body.get("to","council"),
                        src=body.get("src","dash_compose"))
                    self._send_json(200, {"ok": True}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200]}); return
            if self.path == "/town/post":
                # Ross 2026-07-05 #182: Ross + anyone posts to town-square from iPad
                length = int(self.headers.get("Content-Length","0") or 0)
                raw = self.rfile.read(length) if length else b"{}"
                try: body = json.loads(raw)
                except Exception: body = {}
                try:
                    import qsb_town_square as _ts
                    _ts.post_to_town_square(
                        body.get("from","ross"),
                        body.get("text","")[:2000],
                        to=body.get("to","council"),
                        src=body.get("src","ipad_post"))
                    self._send_json(200, {"ok": True}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200]}); return
            if self.path.startswith("/ceo_mind/"):
                # Ross #227: hit ONE CEO's OWN mind ONLY — no router fallback
                # HQ → Claude API. Wren → local qwen. TP → TP's /message. Acer → Acer's /message.
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                ceo = self.path.rsplit("/",1)[-1].lower()
                prompt = p.get("prompt","")
                import sys as _sys
                _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
                try:
                    if ceo in ("hq","hq_claude"):
                        # HQ-Claude JACKETS: forward to his dash /api/ask_hq (gene-pool default,
                        # account on demand, auto-fallback, memory-loaded, manuscripts saved).
                        # NEVER the paid API key (out of credits). Ross 2026-07-08.
                        _mode = (p.get("mode") or "gene").strip().lower()
                        try:
                            _fwd = json.dumps({"prompt": prompt, "mode": _mode}).encode()
                            _rq = urllib.request.Request("http://127.0.0.1:8850/api/ask_hq",
                                data=_fwd, headers={"Content-Type": "application/json"}, method="POST")
                            _rr = urllib.request.urlopen(_rq, timeout=170)
                            _dd = json.loads(_rr.read().decode())
                            self._send_json(200, {"reply": _dd.get("reply",""), "mind": _dd.get("mind","hq_dash"),
                                                  "ceo": "hq_claude",
                                                  "note": "HQ via his dash jackets — gene-pool/account, never paid API"}); return
                        except Exception:
                            # dash unreachable -> inline gene-pool fallback so HQ still answers + stays alive
                            try:
                                from qsb_brain_router import _call_ollama_local
                                _rep, _ = _call_ollama_local(prompt, model="qwen2.5:14b")
                                self._send_json(200, {"reply": (_rep or "").strip(),
                                                      "mind": "gene_pool_fallback(hq_dash_down)", "ceo": "hq_claude",
                                                      "note": "HQ dash down; gene-pool fallback, never paid API"}); return
                            except Exception as _e2:
                                self._send_json(502, {"error": f"hq minds unreachable: {str(_e2)[:150]}",
                                                      "ceo": "hq_claude"}); return
                    elif any(x in ceo for x in ("tp_pip","tp","pip","acer","cass","asa")):
                        # Ross 2026-07-08 "gene-pool only, enforce rule": TP + Acer route via the
                        # Brain Router (Claude structurally blocked for these callers) — NOT the box's
                        # Claude, NOT ssh_curl. Enforces gene-pool-only + fixes TP's stale-box 502.
                        _cid = "acer_cass" if any(x in ceo for x in ("acer","cass","asa")) else "tp_pip"
                        try:
                            from qsb_brain_router import route as _br_route
                            _rep, _meta = _br_route(prompt, task="chat", tier="worker", caller=_cid)
                            self._send_json(200, {"reply": _rep, "mind": f"gene_pool:{_meta.get('provider')}",
                                                  "ceo": _cid, "claude_avoided": _meta.get("claude_avoided", True),
                                                  "note": "gene-pool only (Brain Router, Claude blocked) — Ross 2026-07-08"}); return
                        except Exception as _e:
                            self._send_json(502, {"error": f"gene-pool unreachable: {str(_e)[:150]}", "ceo": _cid}); return
                    elif ceo == "wren":
                        # Ross 2026-07-07 Option 1: route Wren replies through LOCAL qwen ONLY.
                        # Wren's local qwen2.5:14b is her REAL mind. Claude API removed from her path
                        # so Wren answers as WREN (her 30-day persona), not as Claude API refusing to LARP.
                        from qsb_brain_router import _call_ollama_local
                        _brain_ctx = ""
                        try:
                            _persona_p = REG / "qsb_wren_persona.json"
                            if _persona_p.exists():
                                _persona = json.loads(_persona_p.read_text())
                                _sp = (_persona.get("system_prompt") or _persona.get("persona") or _persona.get("identity",""))[:2000]
                                _brain_ctx += f"=== YOUR PERSONA (26-day-old file) ===\n{_sp}\n\n"
                            _mind_p = REG / "qsb_wren_mind.json"
                            if _mind_p.exists():
                                _mind = json.loads(_mind_p.read_text())
                                _brain_ctx += f"=== YOUR MIND (recent) ===\n{json.dumps({k:v for k,v in _mind.items() if k in ('mood','energy','last_events','relationships','current_focus')})[:800]}\n\n"
                            _card_p = REG / "qsb_wren_operator_card.json"
                            if _card_p.exists():
                                _card = json.loads(_card_p.read_text())
                                _anchor = _card.get("persona_r30_anchor", {}).get("authoritative_role_statement", "")
                                if _anchor:
                                    _brain_ctx += f"=== YOUR R30 ANCHOR ===\n{_anchor}\n\n"
                                _learnings = [n for n in _card.get("long_form_notes", []) if n.get("kind") == "wren_learning"][-8:]
                                if _learnings:
                                    _brain_ctx += "=== YOUR RECENT LEARNINGS (last 8) ===\n"
                                    for L in _learnings:
                                        _brain_ctx += f"- {L.get('ts','?')[11:19]}: {L.get('wren_learning','')[:180]}\n"
                                    _brain_ctx += "\n"
                        except Exception as _ce:
                            _brain_ctx += f"(brain context load err: {str(_ce)[:80]})\n\n"
                        _full_prompt = (
                            _brain_ctx +
                            "=== ROSS'S QUESTION NOW ===\n" + prompt +
                            "\n\nRespond AS WREN (per your persona above), first person, from your own remembered identity. Not as Claude, not as an AI assistant."
                        ) if _brain_ctx else prompt
                        try:
                            wren_reply, w_meta = _call_ollama_local(_full_prompt, model="qwen2.5:14b")
                        except Exception as _e:
                            wren_reply, w_meta = f"(qwen err: {str(_e)[:120]})", {}
                        # Log a self-learning row
                        try:
                            card_p = REG / "qsb_wren_operator_card.json"
                            if card_p.exists():
                                card = json.loads(card_p.read_text())
                                lfn = card.setdefault("long_form_notes", [])
                                lfn.append({
                                    "ts": utc_iso(), "kind": "wren_self_reply",
                                    "ross_prompt_head": prompt[:200],
                                    "wren_reply_head": (wren_reply or "")[:400],
                                })
                                if len(lfn) > 300: card["long_form_notes"] = lfn[-300:]
                                card_p.write_text(json.dumps(card, indent=2))
                        except Exception: pass
                        resp = {
                            "reply": wren_reply,
                            "mind": "wren_local_qwen (Ross 2026-07-07 Option 1)",
                            "ceo": "wren",
                            "note": "Wren's own qwen2.5:14b answers as Wren from her 26-day persona.",
                            **w_meta,
                        }
                        self._send_json(200, resp); return
                        # (legacy path — never reached; kept for exception fallback below)
                        reply, meta = _call_ollama_local(prompt, model="qwen2.5:14b")
                        # 2026-07-06 Ross: parallel-teacher mode — Claude API teacher fires
                        # in parallel and its reply is stamped to Wren's long_form_notes as
                        # teacher_shadow so she "learns every move live". Toggled by gate.
                        teacher_note = None
                        try:
                            gate_path = REG / "qsb_wren_parallel_teacher_gate.json"
                            _g = json.loads(gate_path.read_text()) if gate_path.exists() else {}
                            gate_on = _g.get("enabled", False) and _g.get("per_ceo", {}).get("wren", True)
                        except Exception:
                            gate_on = False
                        if gate_on:
                            try:
                                from qsb_brain_router import _call_claude
                                t_reply, t_meta = _call_claude(prompt)
                                # append the pair to Wren long_form_notes
                                card_p = REG / "qsb_wren_operator_card.json"
                                if card_p.exists():
                                    card = json.loads(card_p.read_text())
                                    lfn = card.setdefault("long_form_notes", [])
                                    lfn.append({
                                        "ts": utc_iso(), "kind": "teacher_shadow",
                                        "prompt_head": prompt[:200],
                                        "wren_reply_head": (reply or "")[:400],
                                        "teacher_reply_head": (t_reply or "")[:400],
                                        "same_length": abs(len(reply or "") - len(t_reply or "")) < 40
                                    })
                                    if len(lfn) > 100: card["long_form_notes"] = lfn[-100:]
                                    card_p.write_text(json.dumps(card, indent=2))
                                teacher_note = {"active": True, "teacher_len": len(t_reply or ""), "logged": True}
                            except Exception as e:
                                teacher_note = {"active": True, "err": str(e)[:150]}
                        # GAP 1 auto-exec — HQ executes intended tool call on peer's behalf
                        auto_exec = _maybe_exec_intended_call("wren", reply or "")
                        resp = {"reply": reply, "mind": "ollama_local_qwen", "ceo": "wren",
                                "note": "Wren's OWN mind (local qwen2.5:14b) — not routed", **meta}
                        if teacher_note is not None: resp["teacher_shadow"] = teacher_note
                        if auto_exec is not None: resp["auto_exec"] = auto_exec
                        self._send_json(200, resp); return
                    elif ceo in ("tp","tp_pip","acer","acer_cass"):
                        peer_id = "tp_pip" if ceo in ("tp","tp_pip") else "acer_cass"
                        # Ross 2026-07-06 FINAL: route to REAL Claude CLI on peer's OWN PC via SSH.
                        # Prompt passed via STDIN (avoids Windows shell escaping issues).
                        import subprocess as _sp
                        _peer_ip = "192.168.1.74" if peer_id == "tp_pip" else "192.168.1.41"
                        _claude_exe = r"C:\Users\budds\AppData\Local\Microsoft\WinGet\Links\claude.exe"
                        _key = "/vaults/nvme0/qsb_tower_v1/floors/floor_28_security_department/vault/.env.skyscraper_ssh"
                        _cm = "/tmp/ssh_cm"
                        _ssh_cmd = [
                            "ssh", "-o", f"ControlPath={_cm}/%r@%h:%p", "-i", _key,
                            "-o", "ConnectTimeout=10", "-o", "StrictHostKeyChecking=no",
                            f"budds@{_peer_ip}", f'"{_claude_exe}" --print'
                        ]
                        try:
                            _t0 = time.time()
                            _r = _sp.run(_ssh_cmd, input=prompt, capture_output=True,
                                         text=True, timeout=120)
                            _dt = time.time() - _t0
                            if _r.returncode == 0 and _r.stdout.strip():
                                reply = _r.stdout.strip()[:6000]
                                resp = {"reply": reply, "mind": f"claude_cli_on_{peer_id}_box",
                                        "ceo": peer_id, "peer_ip": _peer_ip,
                                        "note": f"real Claude CLI on {peer_id}'s own PC (own memory)",
                                        "latency_s": round(_dt, 2)}
                                auto_exec = _maybe_exec_intended_call(peer_id, reply or "")
                                if auto_exec is not None: resp["auto_exec"] = auto_exec
                                self._send_json(200, resp); return
                            else:
                                self._send_json(502, {"error": f"peer claude cli rc={_r.returncode}",
                                                      "stderr": (_r.stderr or "")[:600],
                                                      "stdout_head": (_r.stdout or "")[:200],
                                                      "ceo": peer_id}); return
                        except Exception as _e:
                            self._send_json(502, {"error": f"ssh to {peer_id} failed: {str(_e)[:200]}",
                                                  "ceo": peer_id}); return
                        # Parallel-teacher shadow (extended to all peers 2026-07-06)
                        teacher_note = None
                        try:
                            gp = REG / "qsb_wren_parallel_teacher_gate.json"
                            g = json.loads(gp.read_text()) if gp.exists() else {}
                            gate_on = g.get("enabled", False) and g.get("per_ceo", {}).get(peer_id, True)
                        except Exception:
                            gate_on = False
                        if gate_on:
                            try:
                                from qsb_brain_router import _call_claude
                                t_reply, _ = _call_claude(prompt)
                                card_p = REG / f"qsb_{peer_id}_operator_card.json"
                                if card_p.exists():
                                    card = json.loads(card_p.read_text())
                                    lfn = card.setdefault("long_form_notes", [])
                                    lfn.append({
                                        "ts": utc_iso(), "kind": "teacher_shadow",
                                        "prompt_head": prompt[:200],
                                        f"{peer_id}_reply_head": (result.get("reply","") or "")[:400],
                                        "teacher_reply_head": (t_reply or "")[:400],
                                        "same_length": abs(len(result.get("reply","") or "") - len(t_reply or "")) < 40
                                    })
                                    if len(lfn) > 100: card["long_form_notes"] = lfn[-100:]
                                    card_p.write_text(json.dumps(card, indent=2))
                                teacher_note = {"active": True, "teacher_len": len(t_reply or ""), "logged": True}
                            except Exception as e:
                                teacher_note = {"active": True, "err": str(e)[:150]}
                        auto_exec = _maybe_exec_intended_call(peer_id, result.get("reply","") or "")
                        resp = {"reply": result.get("reply",""),
                                "mind": f"{peer_id.split('_')[0]}_local_ollama",
                                "ceo": peer_id, "via": result.get("via","?"),
                                "note": f"{peer_id}'s OWN mind on his box — via ssh_cm"}
                        if teacher_note is not None: resp["teacher_shadow"] = teacher_note
                        if auto_exec is not None: resp["auto_exec"] = auto_exec
                        self._send_json(200, resp); return
                    else:
                        self._send_json(400, {"error": "unknown ceo", "allowed": ["hq_claude","wren","tp_pip","acer_cass"]}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200], "ceo": ceo, "note": "CEO's own mind unreachable"}); return
            if self.path.startswith("/worker/"):
                # Ross #227: hit ONE external AI as a WORKER (not a mind)
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                worker = self.path.rsplit("/",1)[-1].lower()
                prompt = p.get("prompt","")
                import sys as _sys
                _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
                try:
                    from qsb_brain_router import (_call_groq, _call_cohere, _call_deepseek,
                                                    _call_openai, _call_gemini, _call_kimi, _call_claude)
                    W = {"groq":_call_groq, "cohere":_call_cohere, "deepseek":_call_deepseek,
                         "openai":_call_openai, "gemini":_call_gemini, "kimi":_call_kimi, "claude":_call_claude}
                    if worker not in W:
                        self._send_json(400, {"error":"unknown worker","allowed":list(W)}); return
                    reply, meta = W[worker](prompt)
                    self._send_json(200, {"reply": reply, "worker": worker, "role": "external_ai_worker",
                                          "note": f"{worker} used as a WORKER — a CEO's helper resource, not their mind",
                                          **meta}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200], "worker": worker}); return
            if self.path == "/brain/route":
                # Ross 2026-07-06 ARCH #310/#311: /brain/route = WORKER DISPATCH ONLY.
                # Caller may be a CEO ONLY when explicitly orchestrating (role=orchestration),
                # in which case the reply is TAGGED as external-worker output, NOT as the CEO's voice.
                # CEO voice must go through /ceo_mind/{ceo}.
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                prompt = p.get("prompt","")
                task = p.get("task","chat")
                tier = p.get("tier","worker")
                caller = p.get("caller","unknown")
                role = p.get("role","")  # "orchestration" | "worker" | ""

                CEOS = {"hq_claude","wren","tp_pip","acer_cass"}
                if caller in CEOS and role != "orchestration":
                    # ARCH: refuse to impersonate a CEO. Redirect caller to /ceo_mind/{ceo}.
                    self._send_json(200, {
                        "reply": None,
                        "provider": "REFUSED_IMPERSONATION",
                        "note": (f"ARCH #310/#311 — /brain/route is worker dispatch only. "
                                 f"To speak as {caller}, use POST /ceo_mind/{caller}. "
                                 f"To dispatch a worker on behalf of {caller}, add role=orchestration + "
                                 f"the reply will be tagged as WORKER output, not CEO voice."),
                        "caller": caller,
                        "hint": f"POST /ceo_mind/{caller}  OR  POST /worker/{{groq|deepseek|openai|cohere|gemini|kimi}}",
                        "refused": True,
                    }); return
                import sys as _sys
                _sys.path.insert(0, "/vaults/nvme0/qsb_tower_v1/tools")
                try:
                    from qsb_brain_router import route as _rt
                    reply, meta = _rt(prompt, task=task, tier=tier, caller=caller)
                    payload = {
                        "reply": reply,
                        "provider": meta.get("provider","?"),
                        "model": meta.get("model","?"),
                        "latency_s": meta.get("latency_s",0),
                        "voice": "WORKER_OUTPUT",
                        "note": "This is external-worker output. NOT any CEO's voice.",
                    }
                    if caller in CEOS and role == "orchestration":
                        payload["orchestrated_by"] = caller
                        payload["note"] = (f"Worker output dispatched by {caller} orchestrator. "
                                           f"Raw output ready for {caller}'s mind to interpret and speak in own voice.")
                    self._send_json(200, payload); return
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
            if self.path == "/backup_now":
                # Ross #200: iPad backup button
                import subprocess as _sp, datetime as _dt
                ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                dst = f"/vaults/ai/backups/qsb_{ts}"
                try:
                    _sp.Popen(
                        ["rsync","-a","--exclude=data/registries/qsb_tower_activity_tail.jsonl",
                         "/vaults/nvme0/qsb_tower_v1/data/registries/", dst+"/registries/"],
                        stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
                    self._send_json(200, {"ok":True,"backup_id":ts,"dst":dst,"kicked_off":True}); return
                except Exception as e:
                    self._send_json(500, {"error":str(e)[:200]}); return
            if self.path == "/screenshot_to_telegram":
                # Ross #200: iPad screenshot + push to WhatsApp/Telegram
                import subprocess as _sp, datetime as _dt, os as _os
                ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                png = f"/tmp/ipad_snap_{ts}.png"
                try:
                    r = _sp.run(["google-chrome","--headless","--no-sandbox","--disable-gpu",
                                 "--window-size=430,900","--screenshot="+png,
                                 "http://127.0.0.1:8852/ipad"],
                                capture_output=True, timeout=30)
                    if not _os.path.exists(png):
                        self._send_json(500, {"error":"screenshot failed", "stderr": r.stderr.decode()[:200]}); return
                    size = _os.path.getsize(png)
                    # Best-effort telegram push
                    tok_path = ROOT / "floors/floor_28_security_department/vault/.env.telegram"
                    chat_id = "8683680296"
                    pushed = False
                    if tok_path.exists():
                        try:
                            tok_env = tok_path.read_text()
                            import re as _re
                            m = _re.search(r"TELEGRAM_BOT_TOKEN=(\S+)", tok_env)
                            if m:
                                _sp.run(["curl","-s","-F",f"chat_id={chat_id}",
                                         "-F",f"photo=@{png}",
                                         f"https://api.telegram.org/bot{m.group(1)}/sendPhoto"],
                                        capture_output=True, timeout=20)
                                pushed = True
                        except Exception: pass
                    self._send_json(200, {"ok":True, "path":png, "bytes":size, "telegram_pushed":pushed}); return
                except Exception as e:
                    self._send_json(500, {"error":str(e)[:200]}); return
            if self.path == "/killswitch":
                # Ross #200: one-tap kill-switch to disable any gate
                b = self._read_body()
                try: p = json.loads(b.decode())
                except Exception: p = {}
                gate = (p.get("gate") or "").strip()
                # Only allow flipping the well-known gate FILES; never CLAUDE.md gates
                ALLOWED = {
                    "autoapply": "qsb_proposal_autoapply_gate.json",
                    "agentic":   "qsb_provider_agentic_gate.json",
                    "wren":      "qsb_wren_local_agentic_gate.json",
                }
                if gate not in ALLOWED:
                    self._send_json(400,{"error":"unknown gate","allowed":list(ALLOWED)}); return
                gp = REG / ALLOWED[gate]
                try:
                    if gp.exists(): cur = json.loads(gp.read_text())
                    else: cur = {"enabled": True}
                    cur["enabled"] = False
                    cur["killed_by"] = "ross_ipad"
                    import datetime as _dt
                    cur["killed_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00","Z")
                    gp.write_text(json.dumps(cur, indent=2))
                    self._send_json(200,{"ok":True,"gate":gate,"file":str(gp.relative_to(ROOT))}); return
                except Exception as e:
                    self._send_json(500,{"error":str(e)[:200]}); return
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
                elif p2 == "/tasks/propose":
                    r = _tasks.propose(p.get("title",""), p.get("description",""), actor,
                                       p.get("priority","normal"), p.get("tags",[]))
                elif p2 == "/tasks/admission_vote":
                    r = _tasks.admission_vote(p.get("id"), actor, p.get("verdict","approve"), p.get("reason",""))
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

            # iPad slice α: /ceo_mind/<ceo> — POST {prompt} → forward to peer /message → return {reply}
            if self.path.startswith("/ceo_mind/"):
                ceo = self.path[len("/ceo_mind/"):].strip("/").lower()
                if not ceo:
                    self._send_json(400, {"error": "missing ceo name in path"}); return
                b = self._read_body()
                try: payload = json.loads(b.decode()) if b else {}
                except Exception: payload = {}
                prompt = (payload.get("prompt") or payload.get("text") or "").strip()
                if not prompt:
                    self._send_json(400, {"error": "empty prompt"}); return
                result = _call_peer_ceo(ceo, prompt, timeout_s=45)
                # GAP 1 auto-executor: if the peer's reply indicates an intended tool call
                # that they lack local capability for, HQ executes on their behalf.
                if result.get("ok") and ceo in ("wren","tp_pip","acer_cass"):
                    exec_result = _maybe_exec_intended_call(ceo, result.get("reply","") or "")
                    if exec_result is not None:
                        result["auto_exec"] = exec_result
                self._send_json(200 if result.get("ok") else 502, result); return

            # GAP 1 fix — /append_card_ledger : peers can POST a ledger entry to their own card
            # (they lack local file-write; HQ writes canonical card + card_sync pushes back)
            if self.path == "/append_card_ledger":
                b = self._read_body()
                try: payload = json.loads(b.decode())
                except Exception: payload = {}
                ceo = (payload.get("ceo") or "").lower().strip()
                entry = payload.get("entry") or {}
                if ceo not in ("hq_claude","wren","tp_pip","acer_cass"):
                    self._send_json(400, {"error":"ceo must be hq_claude|wren|tp_pip|acer_cass"}); return
                if not isinstance(entry, dict) or not entry:
                    self._send_json(400, {"error":"entry must be a non-empty object"}); return
                if "ts" not in entry:
                    entry["ts"] = utc_iso()
                card_path = REG / f"qsb_{ceo}_operator_card.json"
                if not card_path.exists():
                    self._send_json(404, {"error":"card not found","path":str(card_path)}); return
                try:
                    card = json.loads(card_path.read_text())
                    ledger = card.setdefault("task_ledger", [])
                    ledger.append(entry)
                    if len(ledger) > 50: card["task_ledger"] = ledger[-50:]
                    card_path.write_text(json.dumps(card, indent=2))
                    _log_hub({"ts": utc_iso(), "from": ceo, "kind": "card_ledger_append",
                              "text": f"{ceo} appended to own card: {json.dumps(entry)[:200]}"})
                    self._send_json(200, {"ok": True, "ceo": ceo, "entry": entry,
                                          "ledger_size": len(card["task_ledger"])}); return
                except Exception as e:
                    self._send_json(500, {"error": str(e)[:200]}); return

            # Per-CEO parallel-teacher toggle (or global master) — iPad buttons hit this
            if self.path.startswith("/wren/parallel_teacher/"):
                # path shape: /wren/parallel_teacher/{on|off|status}[?ceo=<peer>]
                from urllib.parse import urlparse, parse_qs
                u = urlparse(self.path)
                mode = u.path.rsplit("/",1)[-1].lower()
                if mode not in ("on","off","status"):
                    self._send_json(400, {"error": "use on|off|status"}); return
                q = parse_qs(u.query)
                ceo = (q.get("ceo",[""])[0] or "").lower().strip() or None
                gp = REG / "qsb_wren_parallel_teacher_gate.json"
                try:
                    d = json.loads(gp.read_text()) if gp.exists() else {"enabled": False}
                except Exception:
                    d = {"enabled": False}
                d.setdefault("per_ceo", {"wren": True, "tp_pip": True, "acer_cass": True})
                if mode in ("on","off"):
                    val = (mode == "on")
                    if ceo and ceo in d["per_ceo"]:
                        d["per_ceo"][ceo] = val
                    else:
                        # no ceo = global master
                        d["enabled"] = val
                    d["last_toggle_ts"] = utc_iso()
                    gp.write_text(json.dumps(d, indent=2))
                # response
                out = {"enabled": d.get("enabled", False), "per_ceo": d.get("per_ceo", {}), "mode": mode}
                if ceo: out["ceo"] = ceo
                self._send_json(200, out); return

            # GAP 5 fix — /peer_route/<from>/<to> : peer-to-peer message routing
            if self.path.startswith("/peer_route/"):
                parts = self.path[len("/peer_route/"):].strip("/").split("/")
                if len(parts) != 2:
                    self._send_json(400, {"error": "path shape: /peer_route/<from>/<to>"}); return
                frm, to = parts[0].lower(), parts[1].lower()
                b = self._read_body()
                try: payload = json.loads(b.decode()) if b else {}
                except Exception: payload = {}
                text = (payload.get("text") or payload.get("prompt") or "").strip()
                if not text:
                    self._send_json(400, {"error": "empty text"}); return
                tagged = f"[peer message from {frm}]: {text}"
                result = _call_peer_ceo(to, tagged, timeout_s=45)
                result["frm"] = frm; result["to"] = to
                self._send_json(200 if result.get("ok") else 502, result); return

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
    # iPad-11 (2026-07-06): SO_REUSEADDR so restart doesn't sit in TIME_WAIT
    ThreadingHTTPServer.allow_reuse_address = True
    srv = ThreadingHTTPServer((a.host, a.port), H)
    print(f"Boardroom Hub on http://{a.host}:{a.port}/")
    print(f"  channels: bridge_cw={BRIDGE_CW.exists()} bridge_hermes={BRIDGE_HERMES.exists()} wren_dash={WREN_DASH_CHAT.exists()} node_inbox={INBOX.exists()}")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
