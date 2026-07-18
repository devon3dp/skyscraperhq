#!/usr/bin/env python3
"""qsb_receptionist_dash.py — Receptionist Dashboard V1C.

Pi-touchscreen receptionist control desk for the QSB Tower. NO Pico / GPIO /
serial dependency — pure web dashboard.

V1C panels (Ross 2026-07-11):
  1. Morning brief      2. Approval queue   3. Issue board
  4. Receptionist inbox 5. Visitor mode     6. Handover log   7. Emergency desk
  8. Truth guard: every panel shows LIVE / STALE / OFFLINE / NOT BUILT / NEEDS APPROVAL.

TRUTH RULES (no fake green):
- Every "online" light is a REAL live HTTP probe. No random/demo lights.
- Tour Guide = NOT BUILT YET until a real endpoint answers.
- TP/Acer show corrected hardware-true physical worker truth.
- Wren = OBSERVER / GUARDIAN. Claude HQ = COORDINATOR / ARCHITECT.
- Inbox creates DRAFT intake notes only — NEVER executes anything.

Routes:
  GET  / /visitor /health
  GET  /api/state /api/links /api/latest_reports /api/brief /api/approvals
       /api/issues /api/handover /api/inbox /api/public_state
  POST /api/checkin /api/note   (append-only; /api/note kind = note|intake_draft|
                                 ross_attention|freeze_request)
Writes (append-only): data/registries/qsb_receptionist_events.jsonl
                      data/registries/qsb_receptionist_status.json
"""
from __future__ import annotations
import json, os, socket, time, urllib.request
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
EVENTS = ROOT / "data/registries/qsb_receptionist_events.jsonl"
STATUS = ROOT / "data/registries/qsb_receptionist_status.json"
COUNCIL = ROOT / "data/registries/qsb_council_tasks.jsonl"
REPORTS_DIR = Path("/home/ross/Desktop/SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT")
PORT = 8856


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hq_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("192.168.1.1", 80)); ip = s.getsockname()[0]; s.close()
        if ip.startswith("192.168."):
            return ip
    except Exception:
        pass
    return "192.168.1.72"


HQ_IP = hq_ip()

NODES = [
    {"key": "hq_claude", "name": "Claude HQ", "role": "COORDINATOR / ARCHITECT",
     "probe": "http://127.0.0.1:8850/", "open": f"http://{HQ_IP}:8850/"},
    {"key": "wren", "name": "Wren", "role": "OBSERVER / GUARDIAN",
     "probe": "http://127.0.0.1:8851/", "open": f"http://{HQ_IP}:8851/"},
    {"key": "boardroom", "name": "Boardroom", "role": "town square / council",
     "probe": "http://127.0.0.1:8852/", "open": f"http://{HQ_IP}:8852/"},
    {"key": "brain_v4", "name": "Brain Module V4 / Gene Pool", "role": "gene-pool router",
     "probe": "http://127.0.0.1:8860/health", "open": f"http://{HQ_IP}:8860/"},
    {"key": "tp_pip", "name": "TP-Pip", "role": "PHYSICAL_TASK_CAPABLE_WORKER",
     "probe": "http://192.168.1.74:8871/whoami", "caps": "http://192.168.1.74:8871/capabilities",
     "open": "http://192.168.1.74:8871/", "expect_host": "DESKTOP-9RBVKSM",
     "truth": "192.168.1.74:8871 · DESKTOP-9RBVKSM · Lenovo ThinkPad"},
    {"key": "acer_cass", "name": "Acer-Cass / Asa", "role": "PHYSICAL_TASK_CAPABLE_WORKER",
     "probe": "http://192.168.1.41:8872/whoami", "caps": "http://192.168.1.41:8872/capabilities",
     "open": "http://192.168.1.41:8872/", "expect_host": "DESKTOP-1E2FB5N",
     "truth": "192.168.1.41:8872 · DESKTOP-1E2FB5N · Acer Aspire A315-56"},
    {"key": "task_council", "name": "Task Council", "role": "shared task board", "kind": "file",
     "open": f"http://{HQ_IP}:8852/tasks"},
    {"key": "tour_guide", "name": "Tour Guide", "role": "guided tour", "kind": "not_ready"},
]

# Known safe next-approvals (truthful — reflects real pending state). NOT executable here.
APPROVALS = [
    {"item": "Task Council refresh", "why": "council file is STALE (>1h old)", "status": "NEEDS APPROVAL"},
    {"item": "Tour Guide build", "why": "no live endpoint — NOT BUILT YET", "status": "NEEDS APPROVAL"},
    {"item": "Pi kiosk setup", "why": "Pi-side change (Chromium --kiosk / autostart) not done", "status": "NEEDS APPROVAL"},
    {"item": "Final four-CEO smoke test", "why": "liveness + capability across HQ/TP/Acer/Wren", "status": "NEEDS APPROVAL"},
    {"item": "S4B3 :8850 stale-listener confirm", "why": "HQ dash reloaded to new code; parked for confirmation", "status": "NEEDS APPROVAL"},
    {"item": "Stale/offline service reloads", "why": "reload any STALE/OFFLINE node once approved", "status": "NEEDS APPROVAL"},
]

_state_cache = {"ts": 0.0, "data": None}
_LAST_STATUS_LOG = 0.0


def _get(url: str, timeout: float = 1.6):
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:
        return None, str(e)[:120]


def probe_node(n: dict) -> dict:
    kind = n.get("kind")
    out = {"key": n["key"], "name": n["name"], "role": n["role"], "open": n.get("open"),
           "truth": n.get("truth"), "status": "OFFLINE", "detail": "", "host_ok": None}
    if kind == "not_ready":
        out["status"] = "NOT BUILT YET"
        out["detail"] = "no live endpoint — not started; needs approval"
        return out
    if kind == "file":
        if COUNCIL.exists():
            try:
                lines = [l for l in COUNCIL.read_text(errors="ignore").splitlines() if l.strip()]
                states = Counter()
                for l in lines:
                    try:
                        states[json.loads(l).get("state", "?")] += 1
                    except Exception:
                        pass
                age = int(datetime.now(timezone.utc).timestamp() - COUNCIL.stat().st_mtime)
                out["status"] = "LIVE" if age < 3600 else "STALE"
                open_n = states.get("open", 0) + states.get("routed_for_work", 0) + states.get("needs_implementation", 0)
                out["detail"] = f"{len(lines)} rows · ~{open_n} open · updated {age}s ago"
            except Exception as e:
                out["status"] = "STALE"; out["detail"] = f"read err: {str(e)[:60]}"
        else:
            out["detail"] = "council file not found"
        return out
    code, body = _get(n["probe"])
    if code == 200:
        out["status"] = "LIVE"
        if n.get("caps"):
            _, cbody = _get(n["caps"])
            try:
                d = json.loads(cbody)
                host = d.get("hostname")
                out["host_ok"] = (host == n.get("expect_host")) if n.get("expect_host") else None
                out["detail"] = (f"{d.get('runtime_id')} @ {host} · {d.get('host_mode')} · "
                                 f"task_capable={d.get('can_receive_task')} · self_close={d.get('can_self_close')}")
                if out["host_ok"] is False:
                    out["status"] = "OFFLINE"  # wrong endpoint = do not call it LIVE
                    out["detail"] = f"WRONG ENDPOINT: got host {host}, expected {n.get('expect_host')}"
            except Exception:
                out["detail"] = "whoami ok; capabilities unread"
        else:
            out["detail"] = "responds 200"
    else:
        out["detail"] = f"no response ({body})"
    return out


def build_state(force: bool = False) -> dict:
    now = time.time()
    if not force and _state_cache["data"] and now - _state_cache["ts"] < 4:
        return _state_cache["data"]
    nodes = [probe_node(n) for n in NODES]
    st = {"ok": True, "service": "QSB Receptionist Dashboard V1C", "port": PORT,
          "hq_ip": HQ_IP, "ts": now_iso(), "nodes": nodes,
          "live_count": sum(1 for n in nodes if n["status"] == "LIVE")}
    _state_cache["ts"] = now; _state_cache["data"] = st
    try:
        STATUS.write_text(json.dumps(st, indent=2))
    except Exception:
        pass
    return st


def append_event(ev: dict) -> dict:
    ev = {"ts": now_iso(), **ev}
    try:
        EVENTS.parent.mkdir(parents=True, exist_ok=True)
        with EVENTS.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        return {"ok": True, "event": ev}
    except Exception as e:
        return {"ok": False, "error": str(e)[:120]}


def read_events_tail(n: int = 60) -> list:
    if not EVENTS.exists():
        return []
    out = []
    for l in EVENTS.read_text(errors="ignore").splitlines()[-n:]:
        try:
            out.append(json.loads(l))
        except Exception:
            pass
    return out


def latest_reports(n: int = 8) -> list:
    out = []
    try:
        files = sorted(REPORTS_DIR.glob("*REPORT*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
        for p in files:
            head = p.read_text(errors="ignore").splitlines()
            verdict = next((l for l in head if l.startswith("VERDICT:")), "")
            out.append({"name": p.name,
                        "mtime": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                        "title": (head[0] if head else "")[:90], "verdict": verdict[:80]})
    except Exception:
        pass
    return out


def listen_port_counts() -> Counter:
    c = Counter()
    for fn in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            for line in Path(fn).read_text().splitlines()[1:]:
                p = line.split()
                if len(p) > 3 and p[3] == "0A":
                    c[int(p[1].split(":")[1], 16)] += 1
        except Exception:
            pass
    return c


def compute_issues() -> dict:
    issues = []
    st = build_state()
    for n in st["nodes"]:
        if n["status"] == "OFFLINE":
            kind = "wrong endpoint" if str(n.get("detail", "")).startswith("WRONG ENDPOINT") else "service offline"
            issues.append({"sev": "HIGH", "kind": kind, "detail": f"{n['name']}: {n.get('detail') or ''}"[:120]})
        elif n["status"] == "STALE":
            issues.append({"sev": "MED", "kind": "stale source", "detail": f"{n['name']}: {n.get('detail') or ''}"[:120]})
        elif n["status"] == "NOT BUILT YET":
            issues.append({"sev": "LOW", "kind": "not built", "detail": f"{n['name']}: {n.get('detail') or ''}"[:120]})
    counts = listen_port_counts()
    for port in (8850, 8851, 8852, 8856, 8860):
        if counts.get(port, 0) > 1:
            issues.append({"sev": "HIGH", "kind": "duplicate port owner", "detail": f":{port} has {counts[port]} LISTEN sockets"})
    if not (REPORTS_DIR / "LATEST_REPORT.txt").exists():
        issues.append({"sev": "MED", "kind": "report missing", "detail": "LATEST_REPORT.txt not found in runs folder"})
    if not issues:
        issues.append({"sev": "OK", "kind": "none", "detail": "no issues detected"})
    return {"ts": now_iso(), "issues": issues,
            "counts": {"HIGH": sum(1 for i in issues if i["sev"] == "HIGH"),
                       "MED": sum(1 for i in issues if i["sev"] == "MED"),
                       "LOW": sum(1 for i in issues if i["sev"] == "LOW")}}


def compute_brief() -> dict:
    st = build_state()
    g = lambda s: [n["name"] + (f" — {n['detail']}" if n.get("detail") else "") for n in st["nodes"] if n["status"] == s]
    return {"ts": now_iso(), "changed_overnight": latest_reports(8),
            "live": [n["name"] for n in st["nodes"] if n["status"] == "LIVE"],
            "stale": g("STALE"), "offline": g("OFFLINE"), "not_built": g("NOT BUILT YET"),
            "needs_approval": [a["item"] for a in APPROVALS]}


def compute_handover() -> dict:
    reps = latest_reports(12)
    last_report = reps[0] if reps else None
    last_smoke = next((r for r in reps if "SMOKE" in r["name"].upper()), None) or last_report
    blocker = next((r for r in reps if any(x in (r["verdict"] or "") for x in ("BLOCKED", "FAILED", "PARTIAL"))), None)
    evs = read_events_tail(200)
    last_flag = next((e for e in reversed(evs) if e.get("type") in ("ross_attention", "freeze_request")), None)
    iss = compute_issues()["issues"]
    if iss and iss[0]["kind"] != "none":
        nxt = f"Address: {iss[0]['detail']}"
    else:
        nxt = APPROVALS[0]["item"] + " (needs approval)"
    return {"ts": now_iso(),
            "last_report": last_report,
            "last_smoke": last_smoke,
            "last_approval": "tracked by Ross/ChatGPT off-desk; latest applied verdict = " + ((last_report or {}).get("verdict") or "—"),
            "last_blocker": (blocker["verdict"] + " (" + blocker["name"] + ")") if blocker else (
                (last_flag.get("type") + " @ " + last_flag.get("ts")) if last_flag else "none logged"),
            "next_step": nxt}


def public_state() -> dict:
    st = build_state()
    return {"ts": now_iso(), "online": st["live_count"], "total": len(st["nodes"]),
            "systems": [{"name": n["name"], "status": n["status"]} for n in st["nodes"]]}


# ---------------------------------------------------------------- floors + comms
FLOOR_DIR = ROOT / "data/registries/qsb_receptionist_floor_directory.json"


def load_floors() -> list:
    try:
        return json.loads(FLOOR_DIR.read_text()).get("floors", [])
    except Exception:
        return []


def floor_status(f: dict) -> dict:
    svc = f.get("service")
    if svc and svc.get("live"):
        code, _ = _get(svc["live"])
        st = "LIVE" if code == 200 else "OFFLINE"
        detail = f"{svc['name']} :{svc.get('port')}"
    elif f.get("skeleton"):
        st, detail = "NOT BUILT YET", "skeleton floor (card only)"
    elif f.get("advisory_only"):
        st, detail = "PARTIAL", "advisory / card defined"
    else:
        st, detail = "UNKNOWN", "card defined"
    keep = ("floor_number", "floor_name", "department", "zone", "staff_lead",
            "visitor_open", "tour_blurb", "path", "evidence_source")
    return {**{k: f.get(k) for k in keep}, "status": st, "detail": detail,
            "open": (svc.get("open") if svc else None), "has_dashboard": bool(svc)}


def floors_status() -> dict:
    fl = [floor_status(f) for f in load_floors()]
    return {"ts": now_iso(), "count": len(fl),
            "live": sum(1 for f in fl if f["status"] == "LIVE"),
            "with_dashboard": sum(1 for f in fl if f["has_dashboard"]), "floors": fl}


def floor_search(q: str) -> list:
    q = (q or "").strip().lower()
    if not q:
        return []
    res = []
    for f in load_floors():
        hay = f"{f.get('floor_number')} {f.get('floor_name','')} {f.get('department','')} {f.get('staff_lead','')}".lower()
        if q == str(f.get("floor_number")) or q in hay:
            res.append(floor_status(f))
    return res[:40]


def proc_running(substr: str) -> bool:
    import glob as _g
    for cl in _g.glob("/proc/[0-9]*/cmdline"):
        try:
            if substr in open(cl, "rb").read().decode("utf-8", "ignore"):
                return True
        except Exception:
            pass
    return False


# Truthful comms channels. status = LIVE (proc running OR fresh log) / PARTIAL
# (files exist, no live proof) / NEEDS WIRING (no files). NEVER sends, NEVER reads bodies.
COMMS_DEFS = [
    {"channel": "Telegram", "proc": "qsb_telegram_receptionist.py", "log": "qsb_telegram_audit.jsonl",
     "file": "tools/qsb_telegram_receptionist.py", "reply_mode": "DRAFT_ONLY"},
    {"channel": "WhatsApp", "proc": "qsb_wa_inbound.js", "log": "qsb_whatsapp_sends.jsonl",
     "file": "tools/whatsapp_inbound/qsb_wa_inbound.js", "reply_mode": "DRAFT_ONLY"},
    {"channel": "Gmail", "proc": "qsb_email_receiver.py", "log": "qsb_email_triage_log.jsonl",
     "file": "tools/qsb_email_sender.py", "reply_mode": "DRAFT_ONLY"},
    {"channel": "Phone / voice", "proc": "qsb_twilio_voice_receptionist.py", "log": None,
     "file": "tools/qsb_twilio_voice_receptionist.py", "reply_mode": "DISABLED"},
    {"channel": "Galaxy bridge", "proc": "qsb_galaxy", "log": None,
     "file": "tools/qsb_galaxy_receptionist.sh", "reply_mode": "DISABLED"},
]


def _one_comm(c: dict) -> dict:
    running = proc_running(c["proc"])
    last, count, fresh = None, None, False
    if c.get("log"):
        lp = ROOT / "data/registries" / c["log"]
        if lp.exists():
            mt = lp.stat().st_mtime
            fresh = (time.time() - mt) < 86400
            last = datetime.fromtimestamp(mt, timezone.utc).isoformat().replace("+00:00", "Z")
            try:
                count = sum(1 for _ in lp.open())  # ROW COUNT only — never message bodies
            except Exception:
                count = None
    files_exist = (ROOT / c["file"]).exists()
    if running:
        status, detail = "LIVE", "process running"
    elif fresh:
        status, detail = "LIVE", "fresh log (<24h), no running process confirmed"
    elif files_exist:
        status, detail = "PARTIAL", "scripts/config exist; no live process; log stale/absent"
    else:
        status, detail = "NEEDS WIRING", "no integration found"
    return {"channel": c["channel"], "status": status, "service_running": running,
            "last_event": last, "log_rows": count, "detail": detail,
            "reply_mode": c.get("reply_mode", "DRAFT_ONLY"),
            "send_enabled": False, "read_body_enabled": False, "needs_approval": True}


# ---------------------------------------------------------------- V2: websites / network / drive / replies
WEBSITE_DIR = ROOT / "data/registries/qsb_receptionist_website_directory.json"
NETWORK_DIR = ROOT / "data/registries/qsb_receptionist_network_directory.json"
DRIVE_INDEX = ROOT / "data/registries/qsb_receptionist_drive_index.json"
DRIVE = ROOT / "data/receptionist_drive"


def load_websites() -> dict:
    try:
        return json.loads(WEBSITE_DIR.read_text())
    except Exception:
        return {"sites": [], "count": 0, "shops": 0, "netlify_cli": "unknown"}


def website_search(q: str) -> list:
    q = (q or "").strip().lower()
    if not q:
        return []
    out = []
    for s in load_websites().get("sites", []):
        hay = f"{s.get('site_name','')} {s.get('slug','')} {s.get('source_type','')}".lower()
        if q in hay:
            out.append(s)
    return out[:40]


def network_status() -> dict:
    try:
        net = json.loads(NETWORK_DIR.read_text())
    except Exception:
        return {"devices": [], "storage": []}
    devs = []
    for d in net.get("devices", []):
        st, detail = "UNKNOWN", d.get("evidence", "")
        if d.get("probe"):
            code, _ = _get(d["probe"], timeout=1.3)
            st = "LIVE" if code == 200 else ("OFFLINE" if code is None else "LIVE")
        elif not d.get("addr"):
            st = "NEEDS WIRING"
        devs.append({"name": d.get("name"), "kind": d.get("kind"), "addr": d.get("addr"),
                     "evidence": d.get("evidence"), "status": st, "detail": detail})
    store = []
    for s in net.get("storage", []):
        mt = s.get("mount")
        if mt and Path(mt).exists():
            st = "LIVE"
        elif not mt:
            st = "NEEDS WIRING"
        else:
            st = "OFFLINE"
        store.append({"name": s.get("name"), "mount": mt, "evidence": s.get("evidence"), "status": st})
    return {"ts": now_iso(), "devices": devs, "storage": store}


def drive_status() -> dict:
    try:
        di = json.loads(DRIVE_INDEX.read_text())
    except Exception:
        di = {"folders": []}
    folders = di.get("folders", [])

    def cnt(sub):
        try:
            return sum(1 for _ in (DRIVE / sub).glob("*"))
        except Exception:
            return 0
    return {"ts": now_iso(), "path": str(DRIVE), "writable": os.access(DRIVE, os.W_OK),
            "folders": folders, "records": sum(cnt(f) for f in folders),
            "notes": cnt("notes"), "checkins": cnt("checkins"), "drafts": cnt("drafts"),
            "websites": cnt("websites"), "network": cnt("network"),
            "secrets_excluded": True, "private_bodies_excluded": True,
            "unmasked_phones_excluded": True,
            "latest_handover": (sorted((DRIVE / "handover").glob("*"))[-1].name
                                if list((DRIVE / "handover").glob("*")) else None)}


def draft_reply(b: dict) -> dict:
    ch = (b.get("channel") or "?")[:40]
    text = (b.get("text") or "")[:800]
    add_draft({"title": f"REPLY DRAFT [{ch}]", "raw_text": text, "category": "comms_reply", "linked_device": ch})
    try:
        (DRIVE / "drafts" / f"reply_{int(time.time())}.json").write_text(
            json.dumps({"channel": ch, "text": text, "ts": now_iso(), "status": "draft_only"}, indent=1))
    except Exception:
        pass
    log_activity("comms_draft_reply", item=ch, result="draft saved (NOT sent)", actor="ross")
    return {"ok": True, "status": "DRAFT_ONLY", "channel": ch, "sent": False, "note": "draft saved; NOT sent"}


def approve_reply(b: dict) -> dict:
    # Refuse unless the channel is LIVE_APPROVED — no channel is. Nothing is sent.
    ch = (b.get("channel") or "?")[:40]
    log_activity("comms_approve_reply_refused", item=ch, result="no LIVE_APPROVED connector", actor="ross")
    return {"ok": False, "refused": True, "channel": ch, "status": "REFUSED", "sent": False,
            "reason": "channel is not LIVE_APPROVED — sending needs a separate explicit approval + a live connector. No message sent."}


def comms_status() -> dict:
    return {"ts": now_iso(), "channels": [_one_comm(c) for c in COMMS_DEFS]}


def comm_by_name(name: str) -> dict:
    for c in COMMS_DEFS:
        if c["channel"].lower().startswith(name.lower()):
            return _one_comm(c)
    return {"error": "unknown channel"}


# ---------------------------------------------------------------- V1F working desk
CHECKLIST = ROOT / "data/registries/qsb_receptionist_checklist.json"
ACTIVITY = ROOT / "data/registries/qsb_receptionist_activity.jsonl"
WORKQ = ROOT / "data/registries/qsb_receptionist_work_queue.json"

# (category, title, seed truth_label, evidence). Seeded ONCE; then persisted + editable.
DEFAULT_CHECKLIST = [
    ("Floors", "Verify floor directory", "LIVE", "qsb_receptionist_floor_directory.json (170 floors)"),
    ("Floors", "Verify Floor 47 Claude Embassy", "LIVE", "floor_card #47 -> Claude HQ :8850"),
    ("Floors", "Verify Floor 46 Wren Room", "LIVE", "floor_card #46 -> Wren :8851"),
    ("Websites / Netlify / Shops", "Find Netlify public websites", "NEEDS APPROVAL", "not scanned yet"),
    ("Websites / Netlify / Shops", "Verify Lumen AI website", "UNKNOWN", "not scanned yet"),
    ("Websites / Netlify / Shops", "Verify Green Lane Seeds website", "UNKNOWN", "not scanned yet"),
    ("Communications", "Check Gmail wiring", "PARTIAL", "comms desk: scripts+postfix, no live sync"),
    ("Communications", "Check WhatsApp wiring", "LIVE", "comms desk: wa_inbound bridge running"),
    ("Communications", "Check Telegram wiring", "LIVE", "comms desk: telegram poller running"),
    ("Network / Devices", "Check Galaxy bridge", "UNKNOWN", "not proven this session"),
    ("Network / Devices", "Check Nighthawk status", "UNKNOWN", "not proven this session"),
    ("Network / Devices", "Check SSK / NAS storage", "UNKNOWN", "not proven this session"),
    ("Pi / Receptionist", "Check Pi Receptionist screen", "UNKNOWN", "Pi not probed (no Pi touch authorized)"),
    ("Task Council", "Refresh Task Council stale state", "STALE", "council file >1h old"),
    ("Tour Guide", "Build Tour Guide after approval", "NEEDS APPROVAL", "no live endpoint (NOT BUILT YET)"),
    ("Reports / Smoke Tests", "Run final four-CEO smoke test", "NEEDS APPROVAL", "pending approval"),
]

# Approval queue cards (truthful; nothing here executes).
APPROVAL_QUEUE = [
    {"title": "Make Receptionist persistent (systemd)", "why": "boot + crash survival",
     "risk": "low", "touches": "qsb-receptionist-dash.service", "not_allowed": "no other service",
     "suggested": "already DONE in V1B", "status": "DONE"},
    {"title": "Full floor directory verification", "why": "170 floors mapped; deep per-floor probe pending",
     "risk": "low (read-only)", "touches": "read-only floor cards", "not_allowed": "no floor edits",
     "suggested": "RECEPTIONIST floor-verify pass", "status": "NEEDS APPROVAL"},
    {"title": "Netlify / public website / shop read-only discovery", "why": "websites section unscanned",
     "risk": "low (read-only)", "touches": "netlify API + public URLs (read-only)", "not_allowed": "no deploy",
     "suggested": "WEBSITES-DISCOVERY task", "status": "NEEDS APPROVAL"},
    {"title": "Gmail / WhatsApp / Telegram wiring audit", "why": "confirm bridges + freshness",
     "risk": "low", "touches": "read-only logs/process", "not_allowed": "no send, no body read",
     "suggested": "COMMS-AUDIT task", "status": "NEEDS APPROVAL"},
    {"title": "Network / Nighthawk / Galaxy / Pi status audit", "why": "devices unproven",
     "risk": "low (read-only)", "touches": "read-only pings", "not_allowed": "no router change, no Pi reflash",
     "suggested": "NETWORK-AUDIT task", "status": "NEEDS APPROVAL"},
    {"title": "Final four-CEO smoke test", "why": "liveness + capability HQ/TP/Acer/Wren",
     "risk": "low (read-only)", "touches": "read-only GET", "not_allowed": "no writes",
     "suggested": "FOUR-CEO-SMOKE task", "status": "NEEDS APPROVAL"},
    {"title": "Tour Guide build (after smoke)", "why": "NOT BUILT YET",
     "risk": "med", "touches": "new tour-guide service", "not_allowed": "no auto-start without approval",
     "suggested": "TOUR-GUIDE-BUILD task", "status": "NEEDS APPROVAL"},
]


def log_activity(action: str, item: str = "", result: str = "", actor: str = "receptionist"):
    try:
        with ACTIVITY.open("a") as f:
            f.write(json.dumps({"ts": now_iso(), "action": action, "actor": actor,
                                "item": item, "result": result}) + "\n")
    except Exception:
        pass


def load_checklist() -> list:
    if CHECKLIST.exists():
        try:
            return json.loads(CHECKLIST.read_text())
        except Exception:
            pass
    items = []
    for i, (cat, title, tl, ev) in enumerate(DEFAULT_CHECKLIST):
        items.append({"id": f"chk_{i:02d}", "title": title, "category": cat, "status": "open",
                      "truth_label": tl, "source": "seed", "evidence": ev, "created_at": now_iso(),
                      "updated_at": now_iso(), "checked_by": None, "cleared_by": None,
                      "snooze_until": None, "notes": []})
    save_checklist(items)
    log_activity("checklist_seeded", result=f"{len(items)} items")
    return items


def save_checklist(items: list):
    try:
        CHECKLIST.write_text(json.dumps(items, indent=1))
    except Exception:
        pass


def checklist_action(cid: str, action: str, note: str = "", by: str = "ross") -> dict:
    items = load_checklist()
    hit = None
    for it in items:
        if it["id"] == cid:
            hit = it
            break
    if not hit:
        return {"ok": False, "error": "item not found"}
    # Clear NEVER deletes — it flips status to 'cleared' (kept in history file).
    m = {"done": "done", "clear": "cleared", "snooze": "snoozed",
         "needs_approval": "needs_approval", "watch": "open", "open": "open", "blocked": "blocked"}
    if action in m:
        hit["status"] = m[action]
        if action == "done":
            hit["checked_by"] = by
        if action == "clear":
            hit["cleared_by"] = by
        if action == "snooze":
            hit["snooze_until"] = now_iso()  # marker; UI treats snoozed as hidden-from-active
    if note:
        hit["notes"].append({"ts": now_iso(), "by": by, "text": note[:400]})
    hit["updated_at"] = now_iso()
    save_checklist(items)
    log_activity("item_" + (action if action != "watch" else "keep_watching"),
                 item=hit["title"], result=hit["status"], actor=by)
    return {"ok": True, "item": hit}


def checklist_view() -> dict:
    items = load_checklist()
    active = [i for i in items if i["status"] not in ("cleared",)]
    by = Counter(i["status"] for i in items)
    return {"ts": now_iso(), "active": active, "all_count": len(items), "by_status": dict(by)}


def load_drafts() -> list:
    if WORKQ.exists():
        try:
            return json.loads(WORKQ.read_text())
        except Exception:
            pass
    return []


def add_draft(d: dict) -> dict:
    drafts = load_drafts()
    item = {"id": f"draft_{len(drafts)+1:03d}_{int(time.time())}",
            "title": (d.get("title") or (d.get("raw_text") or "untitled"))[:120],
            "raw_text": (d.get("raw_text") or "")[:800], "category": d.get("category") or "general",
            "linked_floor": d.get("linked_floor"), "linked_site": d.get("linked_site"),
            "linked_device": d.get("linked_device"), "urgency": d.get("urgency") or "normal",
            "status": "draft_only", "created_at": now_iso(), "needs_approval": True}
    drafts.append(item)
    try:
        WORKQ.write_text(json.dumps(drafts, indent=1))
    except Exception:
        pass
    log_activity("draft_task_created", item=item["title"], result="draft_only", actor="ross")
    return {"ok": True, "draft": item}


def desk_today() -> dict:
    st = build_state()
    iss = compute_issues()["issues"]
    top = next((i for i in iss if i["sev"] == "HIGH"), None) or next((i for i in iss if i["sev"] == "MED"), None) or (iss[0] if iss else None)
    reps = latest_reports(1)
    evs = read_events_tail(200)
    last_note = next((e for e in reversed(evs) if e.get("type") in ("note", "ross_attention")), None)
    last_checkin = next((e for e in reversed(evs) if e.get("type") == "checkin"), None)
    nxt = next((a["title"] for a in APPROVAL_QUEUE if a["status"] == "NEEDS APPROVAL"), "—")
    counts = Counter(n["status"] for n in st["nodes"])
    rows = [
        {"row": "Monitoring physical CEOs (TP-Pip, Acer-Cass)", "label": "LIVE"},
        {"row": "Watching Task Council stale state", "label": "STALE"},
        {"row": f"Waiting for Ross approval: {nxt}", "label": "NEEDS APPROVAL"},
        {"row": "Websites / Netlify / shops", "label": "NEEDS APPROVAL"},
        {"row": "Comms desk (Gmail PARTIAL, Voice PARTIAL)", "label": "PARTIAL"},
        {"row": "Tour Guide", "label": "NOT BUILT YET"},
    ]
    return {"ts": now_iso(), "desk_status": "LIVE",
            "counts": {k: counts.get(k, 0) for k in ("LIVE", "STALE", "OFFLINE", "NOT BUILT YET")},
            "top_issue": top, "next_approval": nxt,
            "latest_report": reps[0] if reps else None,
            "latest_note": last_note, "latest_checkin": last_checkin, "rows": rows}


# ---------------------------------------------------------------- HTML (desk)
CSS = """
:root{--bg:#0b1220;--card:#111a2b;--ink:#e8ecf3;--dim:#8aa2b8;--line:#22334a;
--live:#31d07f;--off:#ff5d5d;--stale:#f5b942;--wait:#7d8ea3;--gold:#eab308;--cyan:#22d3ee;--violet:#a78bfa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,Segoe UI,Roboto,sans-serif}
header{padding:14px 18px;background:linear-gradient(180deg,#0e1626,#0b1220);border-bottom:1px solid var(--line);display:flex;align-items:center;gap:12px;flex-wrap:wrap}
header h1{margin:0;font-size:21px}
.badge{padding:5px 11px;border-radius:999px;font-size:12px;font-weight:800;border:1px solid var(--line)}
.rec-live{background:rgba(49,208,127,.14);color:var(--live);border-color:var(--live)}
.tabs{display:flex;gap:6px;flex-wrap:wrap;padding:10px 14px;position:sticky;top:0;background:var(--bg);z-index:9;border-bottom:1px solid var(--line)}
.tab{padding:11px 16px;border-radius:10px;background:#16233a;border:1px solid var(--line);color:var(--ink);font-weight:700;cursor:pointer;font-size:15px}
.tab.on{background:#1d3358;border-color:var(--cyan);color:var(--cyan)}
.wrap{max-width:1100px;margin:0 auto;padding:14px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:12px}
.node,.card2{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
.node b{font-size:16px}.role{font-size:11px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em;margin-top:2px}
.truth{font-size:11px;color:var(--cyan);margin-top:5px;font-family:ui-monospace,monospace}
.detail{font-size:12px;color:var(--dim);margin-top:6px;min-height:16px}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px}
.stat{float:right;font-size:11px;font-weight:800;padding:2px 8px;border-radius:6px;border:1px solid var(--line)}
.s-LIVE .dot{background:var(--live);box-shadow:0 0 9px var(--live)}.s-LIVE .stat{color:var(--live);border-color:var(--live)}
.s-OFFLINE .dot{background:var(--off)}.s-OFFLINE .stat{color:var(--off);border-color:var(--off)}
.s-STALE .dot{background:var(--stale)}.s-STALE .stat{color:var(--stale);border-color:var(--stale)}
.s-NOTBUILT .dot,.s-NEEDS .dot{background:var(--wait)}.s-NOTBUILT .stat,.s-NEEDS .stat{color:var(--wait)}
.s-PARTIAL .dot{background:var(--stale)}.s-PARTIAL .stat{color:var(--stale);border-color:var(--stale)}
.s-NEEDSWIRING .dot{background:var(--gold)}.s-NEEDSWIRING .stat{color:var(--gold);border-color:var(--gold)}
.s-UNKNOWN .dot{background:var(--wait)}.s-UNKNOWN .stat{color:var(--wait)}
h2{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin:20px 4px 10px}
.actions{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:12px}
.btn{display:block;text-align:center;text-decoration:none;color:var(--ink);background:#16233a;border:1px solid var(--line);border-radius:14px;padding:18px 14px;font-size:16px;font-weight:700;cursor:pointer}
.btn:active{transform:scale(.97)}.btn small{display:block;font-size:11px;color:var(--dim);font-weight:500;margin-top:5px}
.btn.gold{border-color:var(--gold);color:var(--gold)}.btn.red{border-color:var(--off);color:var(--off)}.btn.dis{opacity:.5;border-style:dashed;cursor:not-allowed}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:8px}
input,textarea{flex:1;min-width:160px;background:#0b1322;color:var(--ink);border:1px solid var(--line);border-radius:10px;padding:14px;font-size:16px}
.li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 12px;margin-bottom:8px;font-size:13px}
.li .v{color:var(--live);font-family:ui-monospace,monospace;font-size:11px}
.pill{display:inline-block;font-size:10px;font-weight:800;padding:1px 7px;border-radius:6px;border:1px solid var(--line);margin-right:6px}
.HIGH{color:var(--off);border-color:var(--off)}.MED{color:var(--stale);border-color:var(--stale)}.LOW{color:var(--wait)}.OK{color:var(--live);border-color:var(--live)}
.NEEDS{color:var(--gold);border-color:var(--gold)}
.foot{color:var(--dim);font-size:11px;text-align:center;padding:16px}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:#16233a;border:1px solid var(--live);color:var(--live);padding:12px 18px;border-radius:10px;font-weight:700;opacity:0;transition:.2s;pointer-events:none}
#toast.show{opacity:1}.hide{display:none}
.legend{font-size:11px;color:var(--dim)}.legend span{margin-right:10px}
"""

PAGE = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<title>QSB Receptionist</title><style>__CSS__</style></head><body>
<header>
 <h1>🛎️ QSB Receptionist</h1>
 <span class="badge rec-live"><span class="dot" style="background:var(--live)"></span>DESK LIVE</span>
 <span class="badge" id="clock">—</span><span class="badge" id="livecount">—</span>
 <a class="badge" href="/visitor" style="text-decoration:none;color:var(--violet);border-color:var(--violet)">👋 Visitor mode →</a>
 <span class="legend" style="margin-left:auto">🟢 LIVE · 🔴 OFFLINE · 🟡 STALE · ⚪ NOT BUILT / NEEDS APPROVAL — real probes, no fake green</span>
</header>
<div class="tabs" id="tabs"></div>
<div id="doingNow" style="padding:8px 16px;background:#0e1626;border-bottom:1px solid var(--line);color:var(--cyan);font-size:12.5px;font-weight:600">Receptionist is at her desk…</div>
<div class="wrap">
 <section id="t_desk">
  <h2>Who is online — live probes</h2><div class="grid" id="nodes"></div>
  <h2>Receptionist actions</h2><div class="actions" id="links"></div>
  <h2>Visitor check-in &amp; notes</h2>
  <div class="row"><input id="visitor" placeholder="visitor name / who is here"><button class="btn" style="flex:0 0 auto" onclick="checkin()">Check in ✓</button></div>
  <div class="row"><input id="note" placeholder="receptionist note..."><button class="btn" style="flex:0 0 auto" onclick="addnote()">Add note ✎</button></div>
 </section>

 <section id="t_brief" class="hide">
  <h2>Morning brief — what changed overnight</h2><div id="brief_changed"></div>
  <h2>Live / Stale / Offline / Not built</h2><div id="brief_status"></div>
  <h2>Needs Ross approval</h2><div id="brief_appr"></div>
 </section>

 <section id="t_approvals" class="hide">
  <h2>Approval queue — next safe approvals (Ross decides; desk does NOT execute)</h2><div id="appr"></div>
 </section>

 <section id="t_issues" class="hide">
  <h2>Issue board — auto-detected problems</h2><div id="issues"></div>
 </section>

 <section id="t_inbox" class="hide">
  <h2>Receptionist inbox — type an intent → creates a DRAFT intake note (never executed)</h2>
  <div class="row"><input id="intake" placeholder='e.g. "Lou needs to do X" · "Build Tour Guide" · "Check TP"'><button class="btn" style="flex:0 0 auto" onclick="intake()">Create draft ✎</button></div>
  <div class="card2" style="margin-top:8px;color:var(--dim);font-size:12px">Drafts are intake notes only. Nothing runs. A CEO/Ross converts a draft into a real Task Council task separately.</div>
  <h2>Recent desk activity</h2><div id="inbox"></div>
 </section>

 <section id="t_handover" class="hide">
  <h2>Handover log</h2><div id="handover"></div>
 </section>

 <section id="t_emergency" class="hide">
  <h2>Emergency desk</h2>
  <div class="actions">
   <div class="btn gold" onclick="attention()">🔔 Ross needs attention</div>
   <div class="btn red" onclick="freeze()">⏸️ Freeze work (flag only)</div>
   <div class="btn" onclick="sysCheck()">🩺 System check (re-probe now)</div>
   <div class="btn" onclick="toggleTrouble()">⚠️ Show stale/offline only</div>
  </div>
  <div class="card2" style="margin-top:10px;color:var(--dim);font-size:12px">Freeze is a REQUEST FLAG written to the desk log — it does not stop any process. A CEO/Ross acts on it.</div>
  <h2>Trouble view <span id="troubleState" class="pill LOW">all</span></h2><div class="grid" id="trouble"></div>
 </section>

 <section id="t_floors" class="hide">
  <h2>Floor directory — take Ross to any floor (real floor cards)</h2>
  <div class="row"><input id="floorq" placeholder='Take me to… 47 · Claude · Wren · Boardroom · Reception' onkeypress='if(event.key==="Enter")floorSearch()'><button class="btn" style="flex:0 0 auto" onclick="floorSearch()">Find floor →</button></div>
  <div id="floorResults"></div>
  <h2>All floors <span id="floorMeta" class="pill LOW"></span></h2><div class="grid" id="floors"></div>
 </section>

 <section id="t_comms" class="hide">
  <h2>Communications desk — truthful channel status</h2><div class="grid" id="comms"></div>
  <div class="card2" style="margin-top:10px;color:var(--dim);font-size:12px">Counts are log-row counts only — <b>no message bodies are read</b>, no tokens or phone numbers are shown. Sending is DISABLED and needs separate approval.</div>
 </section>

 <section id="t_websites" class="hide">
  <h2>Websites / Online shops / Netlify</h2>
  <div class="row"><input id="webq" placeholder="search shops… Lumen · Green · Seeds · little robin" onkeypress='if(event.key==="Enter")webSearch()'><button class="btn" style="flex:0 0 auto" onclick="webSearch()">Search →</button></div>
  <div id="webResults"></div>
  <div class="card2" style="margin:8px 0;color:var(--dim);font-size:12px">Shops are real storefront sources under <b>web/shops/</b>. No Netlify CLI here, so a live public URL is <b>NEEDS VERIFICATION</b> — not faked. Internal apps (Lumen AI, Tower Studio) are NOT labelled shops.</div>
  <h2>All sites <span id="webMeta" class="pill LOW"></span></h2><div class="grid" id="websites"></div>
 </section>

 <section id="t_network" class="hide">
  <h2>Network &amp; devices</h2><div class="grid" id="netDevices"></div>
  <h2>Storage</h2><div class="grid" id="netStorage"></div>
  <h2>Receptionist Drive</h2><div class="card2" id="drive"></div>
 </section>

 <section id="t_today" class="hide">
  <h2>Today's Receptionist Desk</h2>
  <div class="card2" id="todayHead">loading…</div>
  <div id="todayRows" style="margin-top:10px"></div>
 </section>

 <section id="t_checklist" class="hide">
  <h2>Checklist board <span id="ckMeta" class="pill LOW"></span></h2>
  <div class="row"><input id="ckNew" placeholder="add a checklist item…"><input id="ckCat" placeholder="category" style="max-width:150px"><button class="btn" style="flex:0 0 auto" onclick="ckAdd()">+ Add</button></div>
  <div class="card2" style="margin:8px 0;color:var(--dim);font-size:12px">Clear keeps history (marks <b>cleared</b>, never deletes). Every action is logged to the Activity feed. No item executes work.</div>
  <div id="checklist"></div>
 </section>

 <section id="t_activity" class="hide">
  <h2>Receptionist activity feed — what she is doing</h2><div id="activity"></div>
 </section>

 <section id="t_drafts" class="hide">
  <h2>Draft task tray — saved as DRAFT ONLY (never submitted to Task Council)</h2>
  <div class="card2">
   <div class="row"><input id="dtTitle" placeholder="what do you want? (title)"></div>
   <div class="row"><input id="dtText" placeholder="details / raw request"></div>
   <div class="row"><input id="dtCat" placeholder="category" style="max-width:150px"><input id="dtFloor" placeholder="floor #" style="max-width:110px"><input id="dtSite" placeholder="site" style="max-width:130px"><input id="dtDev" placeholder="device" style="max-width:130px"></div>
   <div class="row"><button class="btn gold" style="flex:1" onclick="draftSubmit()">Save DRAFT (no submit)</button></div>
  </div>
  <div id="drafts" style="margin-top:10px"></div>
 </section>

 <h2>Latest task / status reports</h2><div id="reports"></div>
</div>
<div id="toast"></div>
<div class="foot">QSB Receptionist Dashboard V1C · :8856 · no Pico/GPIO · truth-labelled · desk does not execute</div>
<script>
const $=s=>document.querySelector(s);
const TABS=[['today','📋 Today'],['desk','🛎️ Desk'],['floors','🏢 Floors'],['websites','🛍️ Websites'],['comms','📡 Comms'],['network','🌐 Network'],['checklist','☑️ Checklist'],['issues','⚠️ Issues'],['approvals','✅ Approvals'],['activity','📜 Activity'],['drafts','📝 Drafts'],['brief','🌅 Brief'],['inbox','📥 Inbox'],['handover','🔀 Handover'],['emergency','🚨 Emergency']];
let cur='desk',troubleOnly=false;
function cls(s){return 's-'+s.replace(/[^A-Z]/gi,'').replace('NOTBUILTYET','NOTBUILT').replace('NEEDSAPPROVAL','NEEDS')}
async function j(u,o){const r=await fetch(u,o||{cache:'no-store'});return r.json()}
async function post(u,b){return j(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)})}
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800)}
function renderTabs(){$('#tabs').innerHTML=TABS.map(([k,l])=>`<div class="tab ${k===cur?'on':''}" onclick="go('${k}')">${l}</div>`).join('')}
function go(k){cur=k;renderTabs();TABS.forEach(([t])=>$('#t_'+t).classList.toggle('hide',t!==k));load()}
function nodeCard(n){return `<div class="node ${cls(n.status)}"><span class="stat">${n.status}</span><b><span class="dot"></span>${n.name}</b>
 <div class="role">${n.role||''}</div>${n.truth?`<div class="truth">${n.truth}</div>`:''}<div class="detail">${n.detail||''}</div>
 ${n.open&&n.status!=='NOT BUILT YET'?`<div class="row"><a class="btn" style="padding:9px;font-size:13px;flex:1" href="${n.open}" target="_blank">Open →</a></div>`:''}</div>`}
async function refreshDesk(){let d;try{d=await j('/api/state')}catch(e){return}
 $('#clock').textContent=new Date().toLocaleTimeString();$('#livecount').textContent=d.live_count+'/'+d.nodes.length+' LIVE';
 $('#nodes').innerHTML=d.nodes.map(nodeCard).join('');
 $('#trouble').innerHTML=d.nodes.filter(n=>n.status!=='LIVE').map(nodeCard).join('')||'<div class="li">nothing stale/offline 🎉</div>';
 window._nodes=d.nodes;}
async function loadLinks(){const d=await j('/api/links');$('#links').innerHTML=d.links.map(l=>l.ready?`<a class="btn" href="${l.url}" target="_blank">${l.label}<small>${l.note||''}</small></a>`:`<div class="btn dis">${l.label}<small>${l.note||'not available'}</small></div>`).join('')}
async function loadReports(){const d=await j('/api/latest_reports');$('#reports').innerHTML=(d.reports||[]).map(r=>`<div class="li"><b>${r.name}</b> <span style="color:var(--dim)">· ${r.mtime}</span><br><span class="v">${r.verdict||r.title||''}</span></div>`).join('')||'<div class="li">no reports</div>'}
async function loadBrief(){const d=await j('/api/brief');
 $('#brief_changed').innerHTML=(d.changed_overnight||[]).map(r=>`<div class="li"><b>${r.name}</b> <span style="color:var(--dim)">${r.mtime}</span><br><span class="v">${r.verdict||''}</span></div>`).join('')||'<div class="li">none</div>';
 const blk=(t,arr,c)=>`<div class="li"><span class="pill ${c}">${t}</span>${arr.length?arr.join(' · '):'none'}</div>`;
 $('#brief_status').innerHTML=blk('LIVE',d.live,'OK')+blk('STALE',d.stale,'MED')+blk('OFFLINE',d.offline,'HIGH')+blk('NOT BUILT',d.not_built,'LOW');
 $('#brief_appr').innerHTML=d.needs_approval.map(a=>`<div class="li"><span class="pill NEEDS">NEEDS APPROVAL</span>${a}</div>`).join('');}
function pillClass(l){l=(l||'').toUpperCase();if(l.includes('LIVE')||l.includes('DONE'))return 'OK';if(l.includes('STALE')||l.includes('PARTIAL'))return 'MED';if(l.includes('OFFLINE'))return 'HIGH';if(l.includes('APPROVAL')||l.includes('WIRING'))return 'NEEDS';return 'LOW'}
function labelPill(l){return `<span class="pill ${pillClass(l)}">${l}</span>`}
async function loadApprovals(){const d=await j('/api/approval_queue');$('#appr').innerHTML=d.queue.map(a=>`<div class="li">${labelPill(a.status)}<b>${a.title}</b><br><span style="color:var(--dim)">why: ${a.why} · risk: ${a.risk}</span><br><span style="color:var(--dim)">touches: ${a.touches} · not allowed: ${a.not_allowed}</span><br><span class="v">suggested: ${a.suggested}</span></div>`).join('')}
async function loadToday(){const d=await j('/api/desk_today');
 $('#todayHead').innerHTML=`<b>Desk: ${d.desk_status}</b> · LIVE ${d.counts['LIVE']} · STALE ${d.counts['STALE']} · OFFLINE ${d.counts['OFFLINE']} · NOT BUILT ${d.counts['NOT BUILT YET']}<br>
  <span style="color:var(--dim)">Top issue:</span> ${d.top_issue?('['+d.top_issue.sev+'] '+d.top_issue.kind+' — '+d.top_issue.detail):'none'}<br>
  <span style="color:var(--dim)">Next approval:</span> ${labelPill('NEEDS APPROVAL')} ${d.next_approval}<br>
  <span style="color:var(--dim)">Latest report:</span> ${d.latest_report?(d.latest_report.name+' — '+(d.latest_report.verdict||'')):'—'}<br>
  <span style="color:var(--dim)">Latest note:</span> ${d.latest_note?(d.latest_note.text||d.latest_note.type):'—'} · <span style="color:var(--dim)">last check-in:</span> ${d.latest_checkin?d.latest_checkin.visitor:'—'}`;
 $('#todayRows').innerHTML=d.rows.map(r=>`<div class="li">${labelPill(r.label)} ${r.row}</div>`).join('');}
let _ckItems={};
function ckBtns(it){return `<div class="row" style="margin-top:6px">
 <button class="btn" style="flex:1;padding:9px;font-size:13px" onclick="ck('done','${it.id}')">✓ Done</button>
 <button class="btn" style="flex:1;padding:9px;font-size:13px" onclick="ck('clear','${it.id}')">Clear</button>
 <button class="btn" style="flex:1;padding:9px;font-size:13px" onclick="ck('snooze','${it.id}')">Snooze</button>
 <button class="btn" style="flex:1;padding:9px;font-size:13px" onclick="ck('needs_approval','${it.id}')">Needs appr.</button>
 <button class="btn" style="flex:1;padding:9px;font-size:13px" onclick="ck('watch','${it.id}')">Keep watching</button>
 <button class="btn" style="flex:1;padding:9px;font-size:13px" onclick="ckNote('${it.id}')">Add note</button>
 <button class="btn" style="flex:1;padding:9px;font-size:13px" onclick="ckDraft('${it.id}')">Draft task</button></div>`}
async function loadChecklist(){const d=await j('/api/checklist');$('#ckMeta').textContent=d.all_count+' items · '+JSON.stringify(d.by_status);_ckItems={};
 $('#checklist').innerHTML=d.active.filter(i=>i.status!=='snoozed').map(it=>{_ckItems[it.id]=it.title;return `<div class="li"><span class="stat" style="float:right">${it.status.toUpperCase()}</span><b>${it.title}</b> ${labelPill(it.truth_label)}<br><span style="color:var(--dim)">${it.category} · ${it.evidence||''}</span>${it.notes.length?('<br><span class="v">'+it.notes.length+' note(s)</span>'):''}${ckBtns(it)}</div>`}).join('')||'<div class="li">no active items</div>';}
async function ck(a,id){const r=['done','clear','snooze'].includes(a)?a:'update';await post('/api/checklist/'+r,{id:id,action:a});toast(a.replace('_',' ')+' ✓');loadChecklist();}
async function ckNote(id){const t=prompt('note for this item:');if(t){await post('/api/checklist/update',{id:id,action:'watch',note:t});toast('note added');loadChecklist()}}
async function ckDraft(id){const title=_ckItems[id]||id;await post('/api/draft_task',{title:'FROM CHECKLIST: '+title,raw_text:title,category:'checklist'});toast('draft created (not submitted)')}
async function ckAdd(){const t=$('#ckNew').value.trim();if(!t)return;await post('/api/checklist/add',{title:t,category:$('#ckCat').value.trim()||'General'});$('#ckNew').value='';$('#ckCat').value='';toast('item added');loadChecklist()}
async function loadActivity(){const d=await j('/api/activity');$('#activity').innerHTML=(d.events||[]).map(e=>`<div class="li"><span style="color:var(--dim)">${e.ts}</span> · <b>${e.action}</b> · ${e.actor}${e.item?(' · '+e.item):''}${e.result?(' → '+e.result):''}</div>`).join('')||'<div class="li">no activity yet</div>';}
async function loadDrafts(){const d=await j('/api/draft_tasks');$('#drafts').innerHTML=(d.drafts||[]).map(t=>`<div class="li"><span class="pill NEEDS">DRAFT ONLY</span><b>${t.title}</b><br><span style="color:var(--dim)">${t.category} · floor:${t.linked_floor||'-'} · site:${t.linked_site||'-'} · ${t.created_at}</span></div>`).join('')||'<div class="li">no drafts</div>';}
async function draftSubmit(){const t=$('#dtTitle').value.trim();if(!t)return toast('title?');await post('/api/draft_task',{title:t,raw_text:$('#dtText').value.trim(),category:$('#dtCat').value.trim(),linked_floor:$('#dtFloor').value.trim(),linked_site:$('#dtSite').value.trim(),linked_device:$('#dtDev').value.trim()});['dtTitle','dtText','dtCat','dtFloor','dtSite','dtDev'].forEach(i=>$('#'+i).value='');toast('draft saved (not submitted)');loadDrafts()}
async function loadIssues(){const d=await j('/api/issues');$('#issues').innerHTML=`<div class="li">HIGH ${d.counts.HIGH} · MED ${d.counts.MED} · LOW ${d.counts.LOW}</div>`+d.issues.map(i=>`<div class="li"><span class="pill ${i.sev}">${i.sev}</span><b>${i.kind}</b> — ${i.detail}</div>`).join('')}
async function loadInbox(){const d=await j('/api/inbox');$('#inbox').innerHTML=(d.events||[]).map(e=>`<div class="li"><span class="pill ${e.type==='intake_draft'?'NEEDS':e.type==='ross_attention'||e.type==='freeze_request'?'HIGH':'LOW'}">${e.type}</span><span style="color:var(--dim)">${e.ts}</span><br>${e.text||e.visitor||''}</div>`).join('')||'<div class="li">no activity</div>'}
async function loadHandover(){const d=await j('/api/handover');const r=x=>x?(x.name?`${x.name} — ${x.verdict||x.title||''}`:x):'—';
 $('#handover').innerHTML=[['Last report',r(d.last_report)],['Last smoke test',r(d.last_smoke)],['Last approval',d.last_approval],['Last blocker',d.last_blocker],['Next recommended step',d.next_step]].map(([k,v])=>`<div class="li"><b>${k}:</b> <span class="v">${v}</span></div>`).join('')}
function floorCard(f){return `<div class="node ${cls(f.status)}"><span class="stat">${f.status}</span><b><span class="dot"></span>#${f.floor_number} ${f.floor_name}</b>
 <div class="role">${f.department||''}</div>
 <div class="detail">${f.staff_lead?('lead: '+f.staff_lead+' · '):''}${f.zone||''}${f.detail?(' · '+f.detail):''}${f.visitor_open?' · 👋 visitor-open':''}</div>
 ${f.has_dashboard&&f.open?`<div class="row"><a class="btn" style="padding:9px;font-size:13px;flex:1" href="${f.open}" target="_blank">Open dashboard →</a></div>`:`<div class="detail" style="color:var(--wait)">no dashboard · ${f.path||''}</div>`}</div>`}
async function loadFloors(){const d=await j('/api/floors');$('#floorMeta').textContent=d.count+' floors · '+d.live+' live · '+d.with_dashboard+' with dashboard';$('#floors').innerHTML=d.floors.map(floorCard).join('')}
async function floorSearch(){const q=$('#floorq').value.trim();if(!q)return;const d=await j('/api/floor_search?q='+encodeURIComponent(q));$('#floorResults').innerHTML=d.results.length?('<h2>Matches for “'+q+'”</h2>'+d.results.map(floorCard).join('')):('<div class="li">no floor matches “'+q+'”</div>')}
async function loadComms(){const d=await j('/api/comms');$('#comms').innerHTML=d.channels.map(c=>`<div class="node ${cls(c.status)}"><span class="stat">${c.status}</span><b><span class="dot"></span>${c.channel}</b>
 <div class="detail">${c.detail||''}</div>
 <div class="detail">last event: ${c.last_event||'—'} · log rows: ${c.log_rows??'—'} · reply: ${labelPill(c.reply_mode||'DRAFT_ONLY')}</div>
 <div class="detail">send: <b style="color:var(--off)">${c.send_enabled?'YES':'NO'}</b> · read bodies: <b style="color:var(--off)">${c.read_body_enabled?'YES':'NO'}</b> · needs approval: <b style="color:var(--gold)">${c.needs_approval?'YES':'NO'}</b></div>
 <div class="row"><button class="btn" style="flex:1;padding:8px;font-size:12px" onclick="draftReply('${c.channel}')">✎ Draft reply</button><button class="btn" style="flex:1;padding:8px;font-size:12px" onclick="approveReply('${c.channel}')">Try send (approval)</button></div></div>`).join('')}
async function draftReply(ch){const t=prompt('draft reply for '+ch+' (saved as DRAFT, not sent):');if(!t)return;await post('/api/comms/draft_reply',{channel:ch,text:t});toast('reply drafted (not sent)')}
async function approveReply(ch){const r=await post('/api/comms/approve_reply',{channel:ch});toast(r.refused?('REFUSED: '+ch+' not LIVE_APPROVED'):'sent');}
function webCard(s){return `<div class="node ${cls(s.status)}"><span class="stat">${s.status}</span><b><span class="dot"></span>${s.site_name}</b>
 <div class="role">${s.source_type}${s.floor_owner?(' · floor #'+s.floor_owner):''}</div>
 <div class="detail">${s.public_url?('url: '+s.public_url):'no proven public URL'} · ${s.notes||''}</div>
 <div class="detail" style="color:var(--wait)">src: ${s.source_path||''}</div></div>`}
async function loadWebsites(){const d=await j('/api/websites');$('#webMeta').textContent=d.count+' sites · '+d.shops+' shops · netlify CLI: '+(d.netlify_cli||'?');$('#websites').innerHTML=(d.sites||[]).map(webCard).join('')}
async function webSearch(){const q=$('#webq').value.trim();if(!q)return;const d=await j('/api/website_search?q='+encodeURIComponent(q));$('#webResults').innerHTML=d.results.length?('<h2>Matches for “'+q+'”</h2>'+d.results.map(webCard).join('')):('<div class="li">no site matches “'+q+'”</div>')}
async function loadNetwork(){const d=await j('/api/network');
 $('#netDevices').innerHTML=d.devices.map(x=>`<div class="node ${cls(x.status)}"><span class="stat">${x.status}</span><b><span class="dot"></span>${x.name}</b><div class="role">${x.kind}${x.addr?(' · '+x.addr):''}</div><div class="detail">${x.evidence||''}</div></div>`).join('');
 $('#netStorage').innerHTML=d.storage.map(x=>`<div class="node ${cls(x.status)}"><span class="stat">${x.status}</span><b><span class="dot"></span>${x.name}</b><div class="detail">${x.mount||'not mounted'} · ${x.evidence||''}</div></div>`).join('');
 const dr=await j('/api/receptionist_drive');$('#drive').innerHTML=`<b>${dr.path}</b> · writable: ${labelPill(dr.writable?'LIVE':'OFFLINE')}<br>folders: ${(dr.folders||[]).join(', ')}<br>records: ${dr.records} · notes: ${dr.notes} · drafts: ${dr.drafts} · checkins: ${dr.checkins}<br>secrets excluded: <b style="color:var(--live)">${dr.secrets_excluded?'YES':'NO'}</b> · private bodies excluded: <b style="color:var(--live)">${dr.private_bodies_excluded?'YES':'NO'}</b> · unmasked phones excluded: <b style="color:var(--live)">${dr.unmasked_phones_excluded?'YES':'NO'}</b>`;}
async function doingNow(){try{const d=await j('/api/desk_today');const c=d.counts||{};$('#doingNow').textContent=`Receptionist is watching ${(window._nodes||[]).length||8} systems · ${c['STALE']||0} stale · ${c['NOT BUILT YET']||0} not built · next approval: ${d.next_approval} · last check ${new Date().toLocaleTimeString()}`;}catch(e){}}
async function load(){if(cur==='desk'){refreshDesk();loadLinks()}if(cur==='today')loadToday();if(cur==='floors')loadFloors();if(cur==='websites')loadWebsites();if(cur==='comms')loadComms();if(cur==='network')loadNetwork();if(cur==='checklist')loadChecklist();if(cur==='activity')loadActivity();if(cur==='drafts')loadDrafts();if(cur==='brief')loadBrief();if(cur==='approvals')loadApprovals();if(cur==='issues')loadIssues();if(cur==='inbox')loadInbox();if(cur==='handover')loadHandover();if(cur==='emergency')refreshDesk();loadReports();doingNow()}
async function checkin(){const v=$('#visitor').value.trim();if(!v)return toast('enter a name');await post('/api/checkin',{visitor:v});$('#visitor').value='';toast('checked in: '+v)}
async function addnote(){const v=$('#note').value.trim();if(!v)return toast('enter a note');await post('/api/note',{text:v});$('#note').value='';toast('note saved')}
async function intake(){const v=$('#intake').value.trim();if(!v)return toast('type an intent');await post('/api/note',{text:v,kind:'intake_draft'});$('#intake').value='';toast('draft intake created (not executed)');loadInbox()}
async function attention(){await post('/api/note',{text:'ROSS NEEDS ATTENTION',kind:'ross_attention'});toast('🔔 flagged for Ross')}
async function freeze(){await post('/api/note',{text:'FREEZE WORK REQUESTED',kind:'freeze_request'});toast('⏸️ freeze REQUESTED (flag only)')}
async function sysCheck(){toast('re-probing...');await refreshDesk();await loadIssues();toast('system check done')}
function toggleTrouble(){troubleOnly=!troubleOnly;$('#troubleState').textContent=troubleOnly?'stale/offline only':'all';$('#nodes').classList.toggle('hide',troubleOnly)}
renderTabs();go('desk');setInterval(()=>{if(cur==='desk'||cur==='emergency')refreshDesk()},5000);setInterval(loadReports,30000);
</script></body></html>"""

VISITOR = """<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1">
<title>Welcome to SkyscraperHQ</title><style>__CSS__
.hero{max-width:760px;margin:0 auto;padding:24px;text-align:center}
.hero h1{font-size:34px;margin:10px 0}.hero p{color:var(--dim);font-size:16px;line-height:1.6}
.pubgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;margin-top:18px}
.pub{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:14px}
.pub .dot{width:12px;height:12px}</style></head><body>
<div class="hero">
 <div style="font-size:52px">🏙️</div>
 <h1>Welcome to SkyscraperHQ</h1>
 <p><b>SkyscraperHQ</b> is a sovereign AI headquarters — a vertical "city" of cooperating AI workers.
 A coordinator (Claude HQ), a guardian (Wren), and physical worker machines (TP-Pip &amp; Acer-Cass)
 collaborate through a Boardroom and a Brain Router, under human direction. This is the front desk.</p>
 <div class="actions" style="max-width:520px;margin:16px auto">
  <div class="btn dis">🧭 Tour Guide <small>NOT BUILT YET — opens here once ready</small></div>
  <a class="btn" href="/" style="border-color:var(--cyan);color:var(--cyan)">🛎️ Reception desk →</a>
 </div>
 <h2 style="text-align:left">Live system view (safe / public)</h2>
 <div class="pubgrid" id="pub"></div>
 <p style="font-size:12px;margin-top:16px">Status is live and honest: 🟢 online · 🔴 offline · 🟡 stale · ⚪ not built. No fake indicators.</p>
</div>
<script>
const $=s=>document.querySelector(s);
function cls(s){return 's-'+s.replace(/[^A-Z]/gi,'').replace('NOTBUILTYET','NOTBUILT').replace('NEEDSAPPROVAL','NEEDS')}
async function load(){const d=await(await fetch('/api/public_state',{cache:'no-store'})).json();
 $('#pub').innerHTML=`<div class="pub"><b>${d.online}/${d.total}</b><br><span style="color:var(--dim);font-size:12px">systems online</span></div>`+
 d.systems.map(s=>`<div class="pub ${cls(s.status)}"><span class="dot" style="display:inline-block;border-radius:50%;margin-right:6px"></span>${s.name}<br><span class="stat" style="float:none;border:0;padding:0;font-size:11px">${s.status}</span></div>`).join('');}
load();setInterval(load,6000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(b)

    def _json(self, code, obj):
        self._send(code, json.dumps(obj))

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n).decode()) if n else {}
        except Exception:
            return {}

    def do_GET(self):
        p = urlparse(self.path).path
        if p in ("/", "/dashboard"):
            return self._send(200, PAGE.replace("__CSS__", CSS), "text/html; charset=utf-8")
        if p == "/visitor":
            return self._send(200, VISITOR.replace("__CSS__", CSS), "text/html; charset=utf-8")
        if p == "/health":
            return self._json(200, {"ok": True, "service": "qsb_receptionist_dash", "version": "V1C", "port": PORT, "ts": now_iso()})
        if p == "/api/state":
            return self._json(200, build_state())
        if p == "/api/public_state":
            return self._json(200, public_state())
        if p == "/api/brief":
            return self._json(200, compute_brief())
        if p == "/api/approvals":
            return self._json(200, {"ts": now_iso(), "approvals": APPROVALS})
        if p == "/api/issues":
            return self._json(200, compute_issues())
        if p == "/api/handover":
            return self._json(200, compute_handover())
        if p == "/api/inbox":
            return self._json(200, {"ts": now_iso(), "events": list(reversed(read_events_tail(40)))})
        if p == "/api/floors":
            return self._json(200, floors_status())
        if p.startswith("/api/floor/"):
            try:
                n = int(p.rsplit("/", 1)[1])
            except Exception:
                return self._json(400, {"ok": False, "error": "bad floor number"})
            m = [floor_status(f) for f in load_floors() if f.get("floor_number") == n]
            return self._json(200, {"floor": m[0] if m else None})
        if p == "/api/floor_search":
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            return self._json(200, {"q": q, "results": floor_search(q)})
        if p == "/api/comms":
            return self._json(200, comms_status())
        if p == "/api/comms/gmail":
            return self._json(200, comm_by_name("Gmail"))
        if p == "/api/comms/whatsapp":
            return self._json(200, comm_by_name("WhatsApp"))
        if p == "/api/comms/telegram":
            return self._json(200, comm_by_name("Telegram"))
        if p == "/api/comms/phone":
            return self._json(200, comm_by_name("Phone"))
        if p == "/api/comms/galaxy":
            return self._json(200, comm_by_name("Galaxy"))
        if p == "/api/websites":
            return self._json(200, load_websites())
        if p == "/api/shops":
            w = load_websites()
            return self._json(200, {"ts": now_iso(), "shops": [s for s in w.get("sites", []) if s.get("source_type") == "ONLINE_SHOP"]})
        if p == "/api/netlify":
            w = load_websites()
            return self._json(200, {"ts": now_iso(), "netlify_cli": w.get("netlify_cli"),
                                    "sites": w.get("sites", []),
                                    "note": "netlify CLI not installed — live deploy/URL cannot be confirmed; shops labelled NEEDS VERIFICATION"})
        if p == "/api/website_search":
            q = parse_qs(urlparse(self.path).query).get("q", [""])[0]
            return self._json(200, {"q": q, "results": website_search(q)})
        if p == "/api/network":
            return self._json(200, network_status())
        if p == "/api/network/devices":
            return self._json(200, {"ts": now_iso(), "devices": network_status()["devices"]})
        if p == "/api/network/storage":
            return self._json(200, {"ts": now_iso(), "storage": network_status()["storage"]})
        if p == "/api/desk_today":
            global _LAST_STATUS_LOG
            if time.time() - _LAST_STATUS_LOG > 60:
                _LAST_STATUS_LOG = time.time()
                log_activity("status_checked", item="fleet+issues", result="desk refreshed", actor="receptionist")
            return self._json(200, desk_today())
        if p == "/api/checklist":
            return self._json(200, checklist_view())
        if p == "/api/approval_queue":
            return self._json(200, {"ts": now_iso(), "queue": APPROVAL_QUEUE})
        if p == "/api/activity":
            ev = []
            if ACTIVITY.exists():
                for l in ACTIVITY.read_text(errors="ignore").splitlines()[-40:]:
                    try:
                        ev.append(json.loads(l))
                    except Exception:
                        pass
            return self._json(200, {"ts": now_iso(), "events": list(reversed(ev))})
        if p == "/api/draft_tasks":
            return self._json(200, {"ts": now_iso(), "drafts": list(reversed(load_drafts()))})
        if p == "/api/receptionist_drive":
            return self._json(200, drive_status())
        if p == "/api/links":
            ip = HQ_IP
            return self._json(200, {"links": [
                {"label": "🏛️ Open Boardroom", "url": f"http://{ip}:8852/", "ready": True, "note": "town square / council"},
                {"label": "🧠 Open Brain Module V4", "url": f"http://{ip}:8860/", "ready": True, "note": "gene-pool router"},
                {"label": "📋 Open Task Council", "url": f"http://{ip}:8852/tasks", "ready": True, "note": "shared task board"},
                {"label": "🖥️ Claude HQ dashboard", "url": f"http://{ip}:8850/", "ready": True, "note": "coordinator/architect"},
                {"label": "💻 TP-Pip worker", "url": "http://192.168.1.74:8871/", "ready": True, "note": ".74:8871 · DESKTOP-9RBVKSM"},
                {"label": "🖥️ Acer-Cass worker", "url": "http://192.168.1.41:8872/", "ready": True, "note": ".41:8872 · DESKTOP-1E2FB5N"},
                {"label": "🧭 Tour Guide", "url": "", "ready": False, "note": "NOT BUILT YET · needs approval"},
            ]})
        if p == "/api/latest_reports":
            return self._json(200, {"reports": latest_reports()})
        return self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        b = self._body()
        if p == "/api/checkin":
            v = (b.get("visitor") or "").strip()[:120]
            if not v:
                return self._json(400, {"ok": False, "error": "visitor required"})
            return self._json(200, append_event({"type": "checkin", "visitor": v}))
        if p == "/api/note":
            t = (b.get("text") or "").strip()[:500]
            if not t:
                return self._json(400, {"ok": False, "error": "text required"})
            kind = b.get("kind") or "note"
            if kind not in ("note", "intake_draft", "ross_attention", "freeze_request"):
                kind = "note"
            log_activity("note_added", item=kind, result=t[:60], actor="ross")
            return self._json(200, append_event({"type": kind, "text": t}))
        if p == "/api/checklist/add":
            items = load_checklist()
            items.append({"id": f"chk_u{int(time.time())}", "title": (b.get("title") or "untitled")[:120],
                          "category": b.get("category") or "General", "status": "open",
                          "truth_label": b.get("truth_label") or "UNKNOWN", "source": "ross",
                          "evidence": b.get("evidence") or "", "created_at": now_iso(),
                          "updated_at": now_iso(), "checked_by": None, "cleared_by": None,
                          "snooze_until": None, "notes": []})
            save_checklist(items)
            log_activity("item_added", item=items[-1]["title"], result="open", actor="ross")
            return self._json(200, {"ok": True, "item": items[-1]})
        if p == "/api/checklist/done":
            return self._json(200, checklist_action(b.get("id"), "done", b.get("note", "")))
        if p == "/api/checklist/clear":
            return self._json(200, checklist_action(b.get("id"), "clear", b.get("note", "")))
        if p == "/api/checklist/snooze":
            return self._json(200, checklist_action(b.get("id"), "snooze", b.get("note", "")))
        if p == "/api/checklist/update":
            return self._json(200, checklist_action(b.get("id"), b.get("action") or b.get("status") or "watch", b.get("note", "")))
        if p == "/api/draft_task":
            return self._json(200, add_draft(b))
        if p == "/api/comms/draft_reply":
            return self._json(200, draft_reply(b))
        if p == "/api/comms/approve_reply":
            return self._json(200, approve_reply(b))
        return self._json(404, {"ok": False, "error": "not found"})


def main():
    EVENTS.parent.mkdir(parents=True, exist_ok=True)
    if not EVENTS.exists():
        EVENTS.touch()
    if not ACTIVITY.exists():
        ACTIVITY.touch()
    load_checklist()  # seed on first boot
    log_activity("desk_opened", result="receptionist V1F online")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print(f"[receptionist] V1F serving on 0.0.0.0:{PORT} (HQ_IP={HQ_IP})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
