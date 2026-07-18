#!/usr/bin/env python3
"""qsb_wren_concierge_dash.py — Wren Full Concierge V1 (Ross's private command companion).

SEPARATE dashboard on :8857. It READS Wren's existing state + the Receptionist APIs
+ Task Council + CEO endpoints. It NEVER edits Wren's mind/dashboard/logs, never
executes, never sends messages, never submits Task Council tasks, never self-approves,
never self-closes. All POST actions are append-only records for Ross.

Wren stays OBSERVER / GUARDIAN + draft-only. Ross is the only approver.
"""
from __future__ import annotations
import json, os, time, urllib.request
from collections import Counter
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
EVENTS = REG / "qsb_wren_concierge_events.jsonl"
ACTIVITY = REG / "qsb_wren_concierge_activity.jsonl"
STATUS = REG / "qsb_wren_concierge_status.json"
DRAFTS = REG / "qsb_wren_concierge_drafts.json"
COUNCIL = REG / "qsb_council_tasks.jsonl"
WREN_OBSERVED = REG / "qsb_wren_observed_events.jsonl"
WREN_CARD = REG / "qsb_wren_operator_card.json"
REPORTS_DIR = Path("/home/ross/Desktop/SKYSCRAPERHQ_RUNS/00_SEND_THIS_TO_CHATGPT")
RECEPTIONIST = "http://127.0.0.1:8856"
PORT = 8857


def now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def hq_ip():
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("192.168.1.1", 80))
        ip = s.getsockname()[0]; s.close()
        return ip if ip.startswith("192.168.") else "192.168.1.72"
    except Exception:
        return "192.168.1.72"


HQ_IP = hq_ip()


def _get(url, timeout=1.8):
    try:
        r = urllib.request.urlopen(url, timeout=timeout)
        return r.status, r.read().decode("utf-8", "ignore")
    except Exception as e:
        return None, str(e)[:100]


def _getj(url, timeout=1.8):
    c, b = _get(url, timeout)
    if c == 200:
        try:
            return json.loads(b)
        except Exception:
            return None
    return None


def log_activity(action, item="", result="", actor="wren"):
    try:
        with ACTIVITY.open("a") as f:
            f.write(json.dumps({"ts": now_iso(), "action": action, "actor": actor, "item": item, "result": result}) + "\n")
    except Exception:
        pass


def append_event(ev):
    ev = {"ts": now_iso(), **ev}
    try:
        with EVENTS.open("a") as f:
            f.write(json.dumps(ev) + "\n")
        return {"ok": True, "event": ev}
    except Exception as e:
        return {"ok": False, "error": str(e)[:100]}


def read_tail(p, n=40):
    if not p.exists():
        return []
    out = []
    for l in p.read_text(errors="ignore").splitlines()[-n:]:
        try:
            out.append(json.loads(l))
        except Exception:
            pass
    return out


def latest_reports(n=8):
    out = []
    try:
        for p in sorted(REPORTS_DIR.glob("*REPORT*.txt"), key=lambda x: x.stat().st_mtime, reverse=True)[:n]:
            head = p.read_text(errors="ignore").splitlines()
            verdict = next((l for l in head if l.startswith("VERDICT:")), "")
            out.append({"name": p.name, "mtime": datetime.fromtimestamp(p.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                        "verdict": verdict[:90]})
    except Exception:
        pass
    return out


# ---------------- Receptionist bridge (read-only) ----------------
def receptionist_bridge():
    st = _getj(RECEPTIONIST + "/api/state")
    iss = _getj(RECEPTIONIST + "/api/issues")
    appr = _getj(RECEPTIONIST + "/api/approval_queue")
    ck = _getj(RECEPTIONIST + "/api/checklist")
    comms = _getj(RECEPTIONIST + "/api/comms")
    net = _getj(RECEPTIONIST + "/api/network")
    web = _getj(RECEPTIONIST + "/api/websites")
    act = _getj(RECEPTIONIST + "/api/activity")
    reachable = st is not None
    return {"ts": now_iso(), "reachable": reachable,
            "receptionist_live": bool(st and st.get("live_count") is not None),
            "issues": (iss or {}).get("issues", []),
            "issue_counts": (iss or {}).get("counts", {}),
            "approvals": (appr or {}).get("queue", []),
            "checklist_open": sum(1 for i in (ck or {}).get("active", []) if i.get("status") in ("open", "needs_approval")),
            "comms": [(c["channel"], c["status"]) for c in (comms or {}).get("channels", [])],
            "websites_needing_url": sum(1 for s in (web or {}).get("sites", []) if s.get("status") in ("OFFLINE", "NEEDS VERIFICATION")),
            "network_gaps": [d["name"] for d in (net or {}).get("devices", []) if d.get("status") in ("NEEDS WIRING", "OFFLINE")],
            "recent_activity": (act or {}).get("events", [])[:8]}


# ---------------- CEO team watch ----------------
def team():
    def probe(url):
        return _get(url)[0] == 200
    tp = _getj("http://192.168.1.74:8871/capabilities") or {}
    ac = _getj("http://192.168.1.41:8872/capabilities") or {}
    return {"ts": now_iso(), "members": [
        {"name": "Claude HQ", "role": "CEO / engineer (R115)", "endpoint": f"{HQ_IP}:8850",
         "status": "LIVE" if probe("http://127.0.0.1:8850/") else "OFFLINE",
         "can_execute": True, "can_verify": True, "can_self_close": False, "blockers": "not external verifier"},
        {"name": "Wren", "role": "OBSERVER / GUARDIAN / concierge", "endpoint": f"{HQ_IP}:8851",
         "status": "LIVE" if probe("http://127.0.0.1:8851/") else "OFFLINE",
         "can_execute": False, "can_verify": True, "can_self_close": False, "blockers": "draft-only; :8851 dash launcher thrashing"},
        {"name": "TP-Pip", "role": "PHYSICAL_TASK_CAPABLE_WORKER", "endpoint": "192.168.1.74:8871",
         "status": "LIVE" if tp else "OFFLINE",
         "can_execute": bool(tp.get("can_receive_task")), "can_verify": True, "can_self_close": bool(tp.get("can_self_close")),
         "blockers": "Lenovo ThinkPad DESKTOP-9RBVKSM; awaiting Task Council work"},
        {"name": "Acer-Cass", "role": "PHYSICAL_TASK_CAPABLE_WORKER", "endpoint": "192.168.1.41:8872",
         "status": "LIVE" if ac else "OFFLINE",
         "can_execute": bool(ac.get("can_receive_task")), "can_verify": True, "can_self_close": bool(ac.get("can_self_close")),
         "blockers": "Acer Aspire DESKTOP-1E2FB5N; awaiting Task Council work"},
        {"name": "Receptionist", "role": "front-desk building operator", "endpoint": f"{HQ_IP}:8856",
         "status": "LIVE" if probe("http://127.0.0.1:8856/health") else "OFFLINE",
         "can_execute": False, "can_verify": False, "can_self_close": False, "blockers": "audio pending Ross manual accept"},
        {"name": "Council of 15", "role": "specialist toolbox / resources", "endpoint": "n/a",
         "status": "REFERENCE", "can_execute": False, "can_verify": False, "can_self_close": False, "blockers": "resource pool"},
    ]}


# ---------------- Task Council bridge ----------------
def task_council_bridge():
    states = Counter()
    total = 0
    age = None
    if COUNCIL.exists():
        try:
            for l in COUNCIL.read_text(errors="ignore").splitlines():
                if l.strip():
                    total += 1
                    try:
                        states[json.loads(l).get("state", "?")] += 1
                    except Exception:
                        pass
            age = int(time.time() - COUNCIL.stat().st_mtime)
        except Exception:
            pass
    tpu = _getj("http://192.168.1.74:8871/whoami") is not None
    acu = _getj("http://192.168.1.41:8872/whoami") is not None
    stale = age is not None and age > 3600
    return {"ts": now_iso(), "total": total, "by_state": dict(states),
            "open": states.get("open", 0) + states.get("routed_for_work", 0) + states.get("needs_implementation", 0),
            "needs_approval": states.get("needs_approval", 0), "age_s": age, "stale": stale,
            "tp_available": tpu, "acer_available": acu,
            "note": "Wren may DRAFT + mark ready-for-Ross; she does NOT submit/claim/close tasks or fake peer signoff."}


# ---------------- Briefing + Past/Present/Future ----------------
def briefing():
    rb = receptionist_bridge()
    tc = task_council_bridge()
    live = [c for c, s in rb["comms"] if s == "LIVE"]
    stale = ["Task Council" ] if tc["stale"] else []
    needs = [a["title"] if isinstance(a, dict) else a for a in rb["approvals"]]
    unsafe = []
    if any(s != "LIVE" for _, s in rb["comms"]):
        unsafe.append("comms partial/needs-wiring")
    nxt = "Ross: accept Receptionist audio, then approve Task Council refresh" if tc["stale"] else "Ross: review approvals queue"
    return {"ts": now_iso(),
            "changed": latest_reports(5),
            "live": ["Receptionist" if rb["receptionist_live"] else None, "WhatsApp/Telegram inbound"] ,
            "stale": stale, "blocked": rb["network_gaps"], "needs_approval": needs[:8],
            "unsafe": unsafe, "next_safest": nxt}


def past_present_future():
    reps = latest_reports(6)
    tc = task_council_bridge()
    rb = receptionist_bridge()
    return {"ts": now_iso(),
            "past": {"reports": reps, "proven": "Receptionist Full Desk V2 + audio-safety controls; TP/Acer hardware-true; Wren observer/guardian audited"},
            "present": {"receptionist_reachable": rb["reachable"], "receptionist_issues": rb["issue_counts"],
                        "task_council_stale": tc["stale"], "task_council_open": tc["open"],
                        "blocker": "Receptionist audio pending Ross manual accept; Task Council stale" if tc["stale"] else "Receptionist audio pending Ross manual accept"},
            "future": {"next_approval": briefing()["next_safest"],
                       "risk": "Wren self-assessment can be unreliable; keep her draft-only. Council/:8851 launcher thrash unresolved.",
                       "when_task_council_real": "after Ross approves Task Council refresh + a booked task with R115"}}


# ---------------- Wren is watching ----------------
def watch():
    def probe(url):
        return "LIVE" if _get(url)[0] == 200 else "OFFLINE"
    tc = task_council_bridge()
    cards = [
        {"name": "Receptionist", "status": probe("http://127.0.0.1:8856/health"), "endpoint": ":8856"},
        {"name": "Claude HQ", "status": probe("http://127.0.0.1:8850/"), "endpoint": ":8850"},
        {"name": "Boardroom", "status": probe("http://127.0.0.1:8852/"), "endpoint": ":8852"},
        {"name": "Brain Module V4", "status": probe("http://127.0.0.1:8860/health"), "endpoint": ":8860"},
        {"name": "Task Council", "status": "STALE" if tc["stale"] else "LIVE", "endpoint": f"{tc['open']} open"},
        {"name": "TP-Pip", "status": probe("http://192.168.1.74:8871/whoami"), "endpoint": ".74:8871"},
        {"name": "Acer-Cass", "status": probe("http://192.168.1.41:8872/whoami"), "endpoint": ".41:8872"},
        {"name": "Wren (self)", "status": probe("http://127.0.0.1:8851/"), "endpoint": ":8851 bench"},
        {"name": "Public websites/shops", "status": "NEEDS VERIFICATION", "endpoint": "skyscraperhq.uk offline"},
        {"name": "Comms", "status": "PARTIAL", "endpoint": "wa/tg live (send off), gmail partial"},
        {"name": "Network", "status": "PARTIAL", "endpoint": "Pi/Galaxy/SSK need wiring"},
        {"name": "Tour Guide", "status": "NOT BUILT YET", "endpoint": "no endpoint"},
    ]
    return {"ts": now_iso(), "cards": cards}


# ---------------- Guardian warnings ----------------
def guardian_warnings():
    w = []
    tc = task_council_bridge()
    rb = receptionist_bridge()
    if tc["stale"]:
        w.append({"sev": "MED", "warning": "Task Council is STALE (>1h) — needs refresh approval."})
    w.append({"sev": "LOW", "warning": "Tour Guide is NOT BUILT YET — do not present it as ready."})
    if not rb["reachable"]:
        w.append({"sev": "HIGH", "warning": "Receptionist :8856 unreachable — bridge degraded."})
    if any(s != "LIVE" for _, s in rb["comms"]):
        w.append({"sev": "LOW", "warning": "Comms partial — sending stays DISABLED until Ross approves."})
    if not (REPORTS_DIR / "LATEST_REPORT.txt").exists():
        w.append({"sev": "MED", "warning": "LATEST_REPORT.txt missing."})
    w.append({"sev": "GUARD", "warning": "Reminder: verify Claude HQ claims against latest reports; watch for stale TP/Acer-swap memory; every action needs R115; no fake green; Wren stays draft-only."})
    if not w:
        w.append({"sev": "OK", "warning": "no guardian warnings"})
    return {"ts": now_iso(), "warnings": w}


# ---------------- Commentary (Wren's voice, truthful, Ross-directed) ----------------
def commentary():
    rb = receptionist_bridge()
    tc = task_council_bridge()
    lines = ["Ross, this is Wren, your concierge."]
    if tc["stale"]:
        lines.append("Ross, Receptionist says Task Council is stale.")
    lines.append("Ross, Tour Guide is not built yet.")
    lines.append("Ross, shops are found but public URLs need verification.")
    live_comms = [c for c, s in rb["comms"] if s == "LIVE"]
    if live_comms:
        lines.append("Ross, " + " and ".join(live_comms) + " are live, but sending is disabled.")
    lines.append("Ross, T P and Acer are physical task capable and waiting for Task Council work.")
    lines.append("Ross, Claude H Q memory must be checked against the latest reports.")
    lines.append(f"Ross, {len(rb['approvals'])} approvals are waiting for you.")
    return {"ts": now_iso(), "lines": lines,
            "counts": {"issues": sum(rb["issue_counts"].values()) if rb["issue_counts"] else 0,
                       "approvals": len(rb["approvals"]), "watched": 12}}


def load_drafts():
    if DRAFTS.exists():
        try:
            return json.loads(DRAFTS.read_text())
        except Exception:
            return []
    return []


def add_draft(b):
    d = load_drafts()
    item = {"id": f"wdraft_{len(d)+1:03d}_{int(time.time())}", "title": (b.get("title") or "untitled")[:120],
            "details": (b.get("details") or b.get("raw_text") or "")[:800], "urgency": b.get("urgency") or "normal",
            "category": b.get("category") or "general", "target": b.get("target"),
            "suggested_owner": b.get("suggested_owner"), "suggested_partner": b.get("suggested_partner"),
            "suggested_verifier": b.get("suggested_verifier"), "status": "draft_only", "needs_approval": True,
            "created_at": now_iso()}
    d.append(item)
    try:
        DRAFTS.write_text(json.dumps(d, indent=1))
    except Exception:
        pass
    log_activity("draft_task_created", item=item["title"], result="draft_only", actor="ross")
    return {"ok": True, "draft": item}


# ---------------- V1C: approval checklist + packets + voice transcript (record-only) ----------------
CHECKLIST = REG / "qsb_wren_concierge_approval_checklist.json"
PACKETS = REG / "qsb_wren_concierge_approval_packets.jsonl"
TRANSCRIPTS = REG / "qsb_wren_concierge_transcripts.jsonl"

DEFAULT_APPROVALS = [
    ("Accept Receptionist audio after manual test", "Receptionist"),
    ("Refresh Task Council freshness", "Task Council"),
    ("Decide Wren :8851 final vs :8857 staging", "Wren"),
    ("Approve first real Task Council booked task", "Task Council"),
    ("Approve Front Gate visitor code build", "Front Gate"),
    ("Approve Tour Guide build", "Tour Guide"),
    ("Approve website/Netlify verification", "Websites"),
    ("Approve Gmail wiring audit", "Comms"),
    ("Approve WhatsApp send wiring later", "Comms"),
    ("Approve Telegram send wiring later", "Comms"),
    ("Approve phone/Twilio wiring later", "Comms"),
    ("Approve Galaxy bridge wiring later", "Comms"),
    ("Approve Pi kiosk setup", "Network"),
    ("Approve SSK/NAS wiring", "Network"),
]


def load_approval_checklist():
    if CHECKLIST.exists():
        try:
            return json.loads(CHECKLIST.read_text())
        except Exception:
            pass
    items = []
    for i, (title, cat) in enumerate(DEFAULT_APPROVALS):
        items.append({"id": f"ap_{i:02d}", "title": title, "category": cat, "source": "seed",
                      "evidence": "", "status": "open", "checked": False, "ross_decision": None,
                      "notes": [], "linked_report": None, "linked_task": None, "linked_service": None,
                      "created_at": now_iso(), "updated_at": now_iso(), "actor": None})
    save_approval_checklist(items)
    return items


def save_approval_checklist(items):
    try:
        CHECKLIST.write_text(json.dumps(items, indent=1))
    except Exception:
        pass


def _find_ap(items, cid):
    for it in items:
        if it["id"] == cid:
            return it
    return None


def approval_update(b):
    items = load_approval_checklist()
    it = _find_ap(items, b.get("id"))
    if not it:
        return {"ok": False, "error": "item not found"}
    if "checked" in b:
        it["checked"] = bool(b["checked"])
    if b.get("note"):
        it["notes"].append({"ts": now_iso(), "by": "ross", "text": str(b["note"])[:400]})
    it["updated_at"] = now_iso()
    save_approval_checklist(items)
    log_activity("approval_checklist_update", item=it["title"], result="checked=%s" % it["checked"], actor="ross")
    return {"ok": True, "item": it}


def _approval_set(cid, status, decision, note=""):
    items = load_approval_checklist()
    it = _find_ap(items, cid)
    if not it:
        return {"ok": False, "error": "item not found"}
    it["status"] = status
    it["ross_decision"] = decision
    it["actor"] = "ross"
    if note:
        it["notes"].append({"ts": now_iso(), "by": "ross", "text": str(note)[:400]})
    it["updated_at"] = now_iso()
    save_approval_checklist(items)
    log_activity("approval_" + status, item=it["title"], result=str(decision), actor="ross")
    return {"ok": True, "item": it}


def approval_submit(b):
    # Records Ross's decision + writes an approval PACKET. Does NOT execute / submit / touch services.
    cid = b.get("id")
    decision = (b.get("decision") or b.get("ross_decision") or "approved")[:40]
    res = _approval_set(cid, {"approve": "approved", "deny": "denied", "reject": "rejected",
                              "accept": "approved", "sign off": "signed_off"}.get(decision, decision),
                        decision, b.get("note", ""))
    if not res.get("ok"):
        return res
    packet = {"packet_id": f"pkt_{int(time.time())}_{cid}", "approval_item_id": cid,
              "ross_decision": decision, "requested_action": res["item"]["title"],
              "allowed_scope": b.get("allowed_scope") or "as titled; R115 manifest required before any action",
              "forbidden_actions": ["execute", "send", "submit_task", "claim_task", "close_task", "self_approve", "self_close"],
              "needs_R115": True, "created_at": now_iso(), "status": "pending_consumption", "consumed_by": None}
    try:
        with PACKETS.open("a") as f:
            f.write(json.dumps(packet) + "\n")
    except Exception:
        pass
    log_activity("approval_packet_created", item=res["item"]["title"], result=decision + " (pending_consumption)", actor="ross")
    return {"ok": True, "item": res["item"], "packet": packet}


def save_transcript(b):
    # Spoken/typed text becomes DRAFT/intake only. Never executes.
    text = (b.get("text") or "")[:1000]
    ev = {"ts": now_iso(), "text": text, "source": b.get("source") or "voice", "status": "draft_intake_only"}
    try:
        with TRANSCRIPTS.open("a") as f:
            f.write(json.dumps(ev) + "\n")
    except Exception:
        pass
    log_activity("voice_transcript", item=(text[:50]), result="draft/intake only (no execution)", actor="ross")
    return {"ok": True, "saved": ev, "note": "saved as draft/intake only — Wren suggests, Ross approves"}


def voice_status():
    return {"ts": now_iso(), "wren_tts": "http://127.0.0.1:8851/api/wren_tts",
            "wren_stt": "http://127.0.0.1:8851/api/wren_stt", "browser_fallback": True,
            "note": "STT does not execute; spoken text is draft/intake only"}


# ---------------- V1 Job Flow + Skyscraper Knowledge (draft/record-only) ----------------
DICT = REG / "qsb_wren_skyscraper_dictionary.json"
SYN = REG / "qsb_wren_skyscraper_synonyms.json"
ENT = REG / "qsb_wren_skyscraper_entities.json"
JOBS = REG / "qsb_wren_job_cards.jsonl"
JOB_EVENTS = REG / "qsb_wren_job_card_events.jsonl"


def _loadj(p, default):
    try:
        return json.loads(p.read_text())
    except Exception:
        return default


def knowledge_search(q):
    q = (q or "").strip().lower()
    if not q:
        return {"q": q, "results": []}
    out = []
    for t in _loadj(DICT, {}).get("terms", []):
        hay = (t["term"] + " " + " ".join(t.get("aliases", [])) + " " + t.get("description", "")).lower()
        if q in hay or any(q in a.lower() for a in t.get("aliases", [])):
            out.append({"term": t["term"], "type": t["type"], "status": t.get("status"), "description": t["description"]})
    return {"q": q, "results": out[:20]}


def knowledge_entity(eid):
    for e in _loadj(ENT, {}).get("entities", []):
        if e["id"] == eid or e["name"].lower() == (eid or "").lower():
            return e
    return {"error": "entity not found"}


def wren_ask(b):
    text = (b.get("text") or "").strip()
    syn = _loadj(SYN, {}).get("map", {})
    tl = text.lower()
    for k, v in syn.items():
        if k in tl:
            tl = tl.replace(k, v.lower())
    r = knowledge_search(tl or text)
    if not r["results"]:  # tokenize natural questions ("where is tour guide?")
        _STOP = {"what", "where", "when", "which", "whom", "whose", "how", "why", "are", "the", "and",
                 "for", "with", "this", "that", "does", "can", "you", "there", "here", "about", "into",
                 "not", "old", "dashboards", "public"}
        seen = set()
        for word in (tl or text).replace("?", " ").replace(".", " ").replace("(", " ").replace(")", " ").split():
            if len(word) > 3 and word not in _STOP:
                for m in knowledge_search(word)["results"]:
                    if m["term"] not in seen:
                        seen.add(m["term"]); r["results"].append(m)
    log_activity("wren_ask", item=text[:60], result="answered from knowledge (no execution)", actor="ross")
    if r["results"]:
        top = r["results"][0]
        answer = f"{top['term']} — {top.get('status')}. {top['description']}"
        if len(r["results"]) > 1:
            answer += f" (+{len(r['results'])-1} related)"
    else:
        answer = "I'm not certain from my knowledge index — I'd suggest a verification pass. I won't invent facts."
    return {"ts": now_iso(), "question": text, "answer": answer, "matches": r["results"],
            "note": "Wren answers from the knowledge index + reports; she suggests, Ross decides."}


def load_jobs():
    return read_tail(JOBS, 300)


def _job_log(job_id, action, result=""):
    try:
        with JOB_EVENTS.open("a") as f:
            f.write(json.dumps({"ts": now_iso(), "job_id": job_id, "action": action, "result": result, "actor": "ross"}) + "\n")
    except Exception:
        pass


def _rewrite_jobs(jobs):
    try:
        JOBS.write_text(("\n".join(json.dumps(j) for j in jobs) + "\n") if jobs else "")
    except Exception:
        pass


def _suggest_owner(text):
    tl = (text or "").lower()
    if any(x in tl for x in ("physical", "box", "windows", "deploy", "runtime", "trade", "order")):
        return "TP-Pip"
    if any(x in tl for x in ("data", "scan", "audit", "parallel")):
        return "Acer-Cass"
    if any(x in tl for x in ("front desk", "visitor", "website", "shop", "comms")):
        return "Receptionist"
    return "Claude HQ"


def create_job(b):
    raw = (b.get("raw_ross_text") or b.get("text") or "").strip()[:600]
    interp = (b.get("interpreted_request") or raw)[:600]
    owner = b.get("recommended_owner") or _suggest_owner(raw)
    job = {"job_id": f"job_{int(time.time())}", "created_at": now_iso(), "created_by": b.get("created_by") or "Ross",
           "raw_ross_text": raw, "interpreted_request": interp, "category": b.get("category") or "general",
           "linked_floor": b.get("linked_floor"), "linked_department": b.get("linked_department"),
           "linked_site": b.get("linked_site"), "linked_service": b.get("linked_service"),
           "linked_ceos": b.get("linked_ceos") or [owner], "linked_reports": [], "priority": b.get("priority") or "normal",
           "status": "draft", "recommended_owner": owner, "recommended_partner": b.get("recommended_partner") or "Claude HQ",
           "recommended_verifier": b.get("recommended_verifier") or ("Acer-Cass" if owner == "TP-Pip" else "TP-Pip"),
           "council_of_15_resources_needed": b.get("council_of_15_resources_needed") or [], "R115_manifest_required": True,
           "safety_rules": ["R115 required", "no execution by Wren", "no self-approve", "no self-close", "no fake green"],
           "forbidden_actions": ["execute", "send", "submit_task_without_approval", "claim", "close", "self_approve", "self_close"],
           "approval_packet_id": None, "task_council_task_id": None, "evidence_paths": [], "latest_report_path": None,
           "result_summary": None, "ross_signoff": None, "next_action": "Ross review -> approve / deny / change"}
    with JOBS.open("a") as f:
        f.write(json.dumps(job) + "\n")
    _job_log(job["job_id"], "created", "draft (needs Ross review)")
    log_activity("job_card_created", item=job["job_id"], result=interp[:50], actor="ross")
    return {"ok": True, "job": job}


def _job_set(job_id, **kw):
    jobs = load_jobs()
    hit = None
    for j in jobs:
        if j.get("job_id") == job_id:
            j.update(kw); j["updated_at"] = now_iso(); hit = j
    if not hit:
        return {"ok": False, "error": "job not found"}
    _rewrite_jobs(jobs)
    return {"ok": True, "job": hit}


def job_action(path, b):
    jid = b.get("job_id")
    act = path.rsplit("/", 1)[1]
    if act == "create":
        return create_job(b)
    if act == "submit_to_council":
        tc = task_council_bridge()
        job = next((j for j in load_jobs() if j.get("job_id") == jid), None)
        if not job:
            return {"ok": False, "error": "job not found"}
        reasons = []
        if tc.get("stale"):
            reasons.append("Task Council is STALE — a refresh must be approved first")
        if job.get("status") != "approved_by_ross":
            reasons.append("job is not approved_by_ross")
        if job.get("R115_manifest_required") and not b.get("r115_manifest_confirmed"):
            reasons.append("R115 manifest not confirmed")
        if reasons:
            _job_log(jid, "submit_refused", "; ".join(reasons))
            log_activity("job_submit_refused", item=jid, result="; ".join(reasons), actor="wren")
            return {"ok": False, "refused": True, "reasons": reasons,
                    "note": "Wren REFUSES to submit — conditions not met (no fake submission)"}
        r = _job_set(jid, status="ready_for_task_council")
        _job_log(jid, "ready_for_task_council", "Wren prepared; actual submission still needs the R115-gated step")
        return r
    m = {"update": ("status", None), "approve": ("approved_by_ross", None), "reject": ("rejected", None),
         "request_change": ("needs_change", None), "mark_needs_report": ("needs_report", None),
         "mark_ready_for_signoff": ("ready_for_ross_signoff", None), "signoff": ("signed_off", "signoff")}
    if act not in m:
        return {"ok": False, "error": "unknown action"}
    kw = {}
    if act == "update":
        for k in ("interpreted_request", "category", "priority", "linked_floor", "linked_site"):
            if k in b:
                kw[k] = b[k]
    else:
        kw["status"] = m[act][0]
    if act == "request_change":
        kw["next_action"] = b.get("note") or "revise and resubmit"
    if act == "signoff":
        kw["ross_signoff"] = now_iso()
    r = _job_set(jid, **kw)
    if r.get("ok"):
        _job_log(jid, act, kw.get("status", "updated"))
        log_activity("job_" + act, item=jid, result=kw.get("status", "updated"), actor="ross")
    return r


def explain_job(jid):
    job = next((j for j in load_jobs() if j.get("job_id") == jid), None)
    if not job:
        return {"error": "job not found"}
    return {"job_id": jid,
            "what_ross_asked": job["raw_ross_text"],
            "what_wren_understood": job["interpreted_request"],
            "why_category": f"classified as '{job['category']}' from Ross's words",
            "floor_or_service": job.get("linked_floor") or job.get("linked_service") or "n/a",
            "who_should_do_it": f"owner {job['recommended_owner']}, partner {job['recommended_partner']}, verifier {job['recommended_verifier']}",
            "proof_required": "smoke test + report + Ross signoff (no worker self-close)",
            "what_could_go_wrong": "Task Council stale; needs R115; no fake peer verification",
            "ross_must_approve": "approve the job card, then approve Task Council submission",
            "after_approval": "Wren marks ready_for_task_council -> R115-gated step submits -> workers do it -> report returns for Ross signoff",
            "current_status": job["status"]}


PAGE = r"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1,maximum-scale=1"><title>Wren · Concierge</title>
<style>
:root{--bg:#0a1018;--card:#0f1a2a;--ink:#e8ecf3;--dim:#8aa2b8;--line:#22334a;--live:#31d07f;--off:#ff5d5d;--stale:#f5b942;--wait:#7d8ea3;--gold:#eab308;--cyan:#22d3ee;--violet:#a78bfa}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:system-ui,Segoe UI,Roboto,sans-serif}
header{padding:14px 18px;background:linear-gradient(180deg,#101d30,#0a1018);border-bottom:1px solid var(--line);display:flex;gap:12px;align-items:center;flex-wrap:wrap}
header h1{margin:0;font-size:21px;color:var(--violet)}
.badge{padding:5px 11px;border-radius:999px;font-size:12px;font-weight:800;border:1px solid var(--line)}
.doing{padding:8px 16px;background:#101d30;border-bottom:1px solid var(--line);color:var(--violet);font-size:12.5px;font-weight:600}
.wrap{max-width:1150px;margin:0 auto;padding:14px}
.tabs{display:flex;gap:6px;flex-wrap:wrap;padding:10px 14px;position:sticky;top:0;background:var(--bg);z-index:9;border-bottom:1px solid var(--line)}
.tab{padding:11px 15px;border-radius:10px;background:#152234;border:1px solid var(--line);color:var(--ink);font-weight:700;cursor:pointer;font-size:14px}
.tab.on{background:#1d3358;border-color:var(--violet);color:var(--violet)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.card,.node{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:14px}
h2{font-size:13px;color:var(--dim);text-transform:uppercase;letter-spacing:.08em;margin:20px 4px 10px}
.dot{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:6px}
.stat{float:right;font-size:11px;font-weight:800;padding:2px 8px;border-radius:6px;border:1px solid var(--line)}
.s-LIVE .dot{background:var(--live);box-shadow:0 0 9px var(--live)}.s-LIVE .stat{color:var(--live);border-color:var(--live)}
.s-OFFLINE .dot{background:var(--off)}.s-OFFLINE .stat{color:var(--off);border-color:var(--off)}
.s-STALE .dot,.s-PARTIAL .dot{background:var(--stale)}.s-STALE .stat,.s-PARTIAL .stat{color:var(--stale);border-color:var(--stale)}
.s-NOTBUILTYET .dot,.s-NEEDSVERIFICATION .dot,.s-NEEDSWIRING .dot,.s-REFERENCE .dot{background:var(--wait)}
.btn{display:block;text-align:center;text-decoration:none;color:var(--ink);background:#152234;border:1px solid var(--line);border-radius:12px;padding:14px 12px;font-size:14px;font-weight:700;cursor:pointer}
.btn:active{transform:scale(.97)}.btn.g{border-color:var(--gold);color:var(--gold)}.btn.r{border-color:var(--off);color:var(--off)}.btn.v{border-color:var(--violet);color:var(--violet)}.btn.ok{border-color:var(--live);color:var(--live)}
.row{display:flex;gap:8px;flex-wrap:wrap;margin-top:8px}.cbtn{flex:1 1 auto;min-width:130px;padding:12px 8px;font-size:13px}
.li{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 11px;margin-bottom:7px;font-size:12.5px}
.pill{display:inline-block;font-size:10px;font-weight:800;padding:1px 7px;border-radius:6px;border:1px solid var(--line);margin-right:6px}
.HIGH{color:var(--off);border-color:var(--off)}.MED{color:var(--stale);border-color:var(--stale)}.LOW,.GUARD{color:var(--wait)}.OK{color:var(--live);border-color:var(--live)}.NEEDS{color:var(--gold);border-color:var(--gold)}
.avatarCard{display:flex;gap:14px;align-items:flex-start;background:var(--card);border:1px solid var(--violet);border-radius:14px;padding:14px}
.wren{font-size:52px;width:70px;height:70px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:#141f33;border:2px solid var(--violet);flex:0 0 auto}
.wren.idle{animation:bob 2.6s ease-in-out infinite}.wren.speaking{animation:sp .5s infinite;border-color:var(--live);box-shadow:0 0 22px var(--live)}.wren.listening{border-color:var(--gold);box-shadow:0 0 22px var(--gold)}
@keyframes bob{50%{transform:translateY(-5px)}}@keyframes sp{50%{transform:scale(1.08)}}
.sub{font-size:12px;color:var(--dim)}input,select{background:#0b1322;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:10px}
#toast{position:fixed;left:50%;bottom:20px;transform:translateX(-50%);background:#152234;border:1px solid var(--live);color:var(--live);padding:12px 18px;border-radius:10px;font-weight:700;opacity:0;transition:.2s;pointer-events:none}#toast.show{opacity:1}
.hide{display:none}.ppf{display:grid;grid-template-columns:1fr 1fr 1fr;gap:10px}@media(max-width:720px){.ppf{grid-template-columns:1fr}}
</style></head><body>
<header><h1>🛡️ Wren · Concierge</h1><span class="badge" style="color:var(--violet);border-color:var(--violet)">Ross's private command companion</span><span class="badge" id="clock">—</span>
<span class="sub" style="margin-left:auto">🟢 LIVE · 🔴 OFFLINE · 🟡 STALE/PARTIAL · ⚪ NEEDS WIRING/NOT BUILT — real probes, no fake green</span></header>
<div class="doing" id="doing">Wren is with Ross…</div>

<div class="wrap">
 <div class="avatarCard">
  <div id="wavatar" class="wren idle">🛡️</div>
  <div style="flex:1;min-width:200px">
   <b style="font-size:16px">Wren · guardian & concierge</b> <span id="wstate" class="pill OK">Watching</span>
   <div class="sub" style="margin-top:3px">issues <b id="wIssues">–</b> · approvals <b id="wAppr">–</b> · systems watched <b id="wWatched">12</b> · last check <b id="wCheck">–</b></div>
   <div id="wadvice" style="margin-top:6px;color:var(--cyan);font-size:13px;min-height:18px">…</div>
   <div class="sub" style="font-size:10px;color:var(--wait)">idle bob = COSMETIC · speaking glow only while TTS speaks · Wren is observer/guardian, draft-only</div>
  </div>
 </div>

 <div class="card" style="margin-top:12px">
  <div class="row" style="margin-top:0">
   <button class="btn cbtn v" onclick="speakBrief()">🔊 Speak Ross briefing</button>
   <button class="btn cbtn" onclick="speakUrgent()">⚠️ Speak urgent issues</button>
   <button class="btn cbtn" onclick="speakAppr()">✅ Speak approvals</button>
   <button class="btn cbtn" onclick="speakFuture()">🔮 Speak future plan</button>
   <button class="btn cbtn" onclick="startComm()">▶️ Start commentary</button>
   <button class="btn cbtn" onclick="stopComm()">⏸️ Stop</button>
   <button class="btn cbtn" id="muteBtn" onclick="toggleMute()">🔇 Mute</button>
   <button class="btn cbtn r" onclick="killAudio()">🔴 Stop all speech</button>
   <button class="btn cbtn" onclick="toggleAdv()">🎛️ Voice settings</button>
  </div>
  <div id="dupWarn" style="display:none;margin-top:8px;padding:8px;border-radius:8px;background:#3a0d0d;color:#ff6b6b;border:1px solid #ff6b6b;font-weight:700;font-size:12px">⚠ Another Wren tab may also be speaking — close duplicates or mute.</div>
  <div id="adv" style="display:none;margin-top:8px;border-top:1px solid var(--line);padding-top:8px">
   <div class="row"><select id="voiceSel" onchange="vset('voice',this.value)" style="flex:2 1 220px"><option value="">(auto — best English)</option></select></div>
   <div class="row sub"><label style="flex:1;min-width:150px">Rate <b id="rateV">0.90</b><input id="rate" type=range min=0.6 max=1.4 step=0.05 oninput="vset('rate',this.value)" style="width:100%"></label>
    <label style="flex:1;min-width:150px">Pitch <b id="pitchV">1.00</b><input id="pitch" type=range min=0.6 max=1.6 step=0.05 oninput="vset('pitch',this.value)" style="width:100%"></label>
    <label style="flex:1;min-width:150px">Volume <b id="volV">1.00</b><input id="vol" type=range min=0 max=1 step=0.05 oninput="vset('volume',this.value)" style="width:100%"></label></div>
   <div class="sub" style="font-size:10px;color:var(--wait)">Anti-overlap guard ON · duplicate-tab guard ON · pause when hidden ON. Browser speech, no cloud.</div>
  </div>
 </div>

 <div class="tabs" id="tabs"></div>

 <section id="t_brief">
  <h2>Ross briefing</h2><div class="card" id="briefBox">…</div>
  <h2>Past / Present / Future</h2><div class="ppf"><div class="card" id="ppfPast"></div><div class="card" id="ppfPresent"></div><div class="card" id="ppfFuture"></div></div>
 </section>
 <section id="t_watch" class="hide"><h2>Wren is watching</h2><div class="grid" id="watch"></div></section>
 <section id="t_recep" class="hide"><h2>Receptionist bridge (read-only)</h2><div class="card" id="recepBox"></div></section>
 <section id="t_approve" class="hide">
  <h2>Approval console (records only — no execution)</h2>
  <div class="row">
   <button class="btn cbtn ok" onclick="ap('Approve')">Approve</button><button class="btn cbtn r" onclick="ap('Deny')">Deny</button>
   <button class="btn cbtn ok" onclick="ap('Accept')">Accept</button><button class="btn cbtn r" onclick="ap('Do not accept')">Don't accept</button>
   <button class="btn cbtn r" onclick="ap('Reject')">Reject</button><button class="btn cbtn" onclick="ap('Snooze')">Snooze</button>
   <button class="btn cbtn" onclick="ap('Needs report')">Needs report</button><button class="btn cbtn" onclick="ap('Needs smoke test')">Needs smoke test</button>
   <button class="btn cbtn" onclick="ap('Ask Receptionist')">Ask Receptionist</button><button class="btn cbtn" onclick="ap('Mark reviewed')">Mark reviewed</button>
   <button class="btn cbtn g" onclick="ap('Sign off')">Sign off</button><button class="btn cbtn r" onclick="ap('Freeze work')">Freeze work</button>
   <button class="btn cbtn v" onclick="ap('Escalate to Task Council')">Escalate to Task Council</button>
  </div>
  <h2>Pending approvals (from Receptionist)</h2><div id="apprList"></div>
 </section>
 <section id="t_ccc" class="hide">
  <h2>Chance / Choice / Change (logs decision only, no execution)</h2>
  <div class="ppf">
   <div class="card"><b style="color:var(--cyan)">CHANCE</b><div class="row"><button class="btn cbtn" onclick="dec('chance','explore option')">Explore option</button><button class="btn cbtn" onclick="dec('chance','ask for alternatives')">Alternatives</button><button class="btn cbtn" onclick="dec('chance','risk/reward')">Risk/reward</button><button class="btn cbtn" onclick="dec('chance','Council of 15 recommendation')">Ask Council of 15</button></div></div>
   <div class="card"><b style="color:var(--live)">CHOICE</b><div class="row"><button class="btn cbtn ok" onclick="dec('choice','approve option A')">Approve A</button><button class="btn cbtn ok" onclick="dec('choice','approve option B')">Approve B</button><button class="btn cbtn r" onclick="dec('choice','reject')">Reject</button><button class="btn cbtn" onclick="dec('choice','wait')">Wait</button><button class="btn cbtn" onclick="dec('choice','ask for smoke test')">Ask smoke test</button></div></div>
   <div class="card"><b style="color:var(--gold)">CHANGE</b><div class="row"><button class="btn cbtn" onclick="dec('change','request change')">Request change</button><button class="btn cbtn" onclick="dec('change','revise task')">Revise task</button><button class="btn cbtn" onclick="dec('change','send back for correction')">Send back</button><button class="btn cbtn" onclick="dec('change','mark stale')">Mark stale</button><button class="btn cbtn" onclick="dec('change','update plan')">Update plan</button></div></div>
  </div>
 </section>
 <section id="t_council" class="hide"><h2>Task Council bridge</h2><div class="card" id="councilBox"></div>
  <div class="sub" style="margin:6px 4px">Wren may DRAFT + mark ready-for-Ross. She does NOT submit, claim, close, or fake peer signoff.</div></section>
 <section id="t_team" class="hide"><h2>CEO team watch</h2><div class="grid" id="team"></div></section>
 <section id="t_guard" class="hide"><h2>Guardian warnings</h2><div id="guard"></div></section>
 <section id="t_drafts" class="hide">
  <h2>Draft task tray (DRAFT ONLY — never submitted)</h2>
  <div class="card">
   <div class="row"><input id="dtTitle" placeholder="job title" style="flex:2 1 200px"><input id="dtUrg" placeholder="urgency" style="flex:1;max-width:120px"><input id="dtCat" placeholder="category" style="flex:1;max-width:140px"></div>
   <div class="row"><input id="dtDetails" placeholder="details" style="flex:1"></div>
   <div class="row"><input id="dtOwner" placeholder="suggested owner"><input id="dtPartner" placeholder="suggested partner"><input id="dtVerifier" placeholder="suggested verifier"></div>
   <div class="row"><button class="btn cbtn g" onclick="draft()">Save DRAFT (no submit)</button></div>
  </div><div id="drafts" style="margin-top:10px"></div>
 </section>
 <section id="t_activity" class="hide"><h2>Concierge activity feed</h2><div id="activity"></div></section>
</div>
<div id="toast"></div>
<script>
const $=s=>document.querySelector(s);
const TABS=[['brief','📋 Briefing'],['watch','👁️ Watching'],['recep','🛎️ Receptionist'],['approve','✅ Approvals'],['ccc','🎲 Chance/Choice/Change'],['council','📋 Task Council'],['team','👥 CEO Team'],['guard','🛡️ Guardian'],['drafts','📝 Drafts'],['activity','📜 Activity']];
let cur='brief';
function cls(s){return 's-'+(s||'').replace(/[^A-Z]/gi,'')}
async function j(u){const r=await fetch(u,{cache:'no-store'});return r.json()}
async function post(u,b){const r=await fetch(u,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json()}
function toast(m){const t=$('#toast');t.textContent=m;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),1800)}
function renderTabs(){$('#tabs').innerHTML=TABS.map(([k,l])=>`<div class="tab ${k===cur?'on':''}" onclick="go('${k}')">${l}</div>`).join('')}
function go(k){cur=k;renderTabs();TABS.forEach(([t])=>$('#t_'+t).classList.toggle('hide',t!==k));load()}
function pillClass(l){l=(l||'').toUpperCase();if(l.includes('LIVE')||l.includes('DONE')||l.includes('OK'))return 'OK';if(l.includes('STALE')||l.includes('PARTIAL')||l.includes('MED'))return 'MED';if(l.includes('OFFLINE')||l.includes('HIGH'))return 'HIGH';if(l.includes('APPROVAL')||l.includes('WIRING')||l.includes('VERIFICATION')||l.includes('NEEDS'))return 'NEEDS';return 'LOW'}
function pill(l){return `<span class="pill ${pillClass(l)}">${l}</span>`}
// ---- voice (browser TTS, safe engine) ----
const TTS=('speechSynthesis' in window);const VKEY='qsb_wren_voice';
let vcfg=Object.assign({voice:'',rate:0.9,pitch:1.0,volume:1.0,overlapGuard:true,pauseWhenHidden:true,intervalMs:8000},(()=>{try{return JSON.parse(localStorage.getItem(VKEY)||'{}')}catch(e){return{}}})());
function saveV(){try{localStorage.setItem(VKEY,JSON.stringify(vcfg))}catch(e){}}
let muted=false,commTimer=null,commLines=[],commIdx=0,otherTab=false,lastAt=0;
let bc=null;try{bc=new BroadcastChannel('qsb_wren_voice_ch')}catch(e){}
if(bc)bc.onmessage=e=>{if(e.data==='sp'){otherTab=true;$('#dupWarn').style.display='block';clearTimeout(window._d);window._d=setTimeout(()=>{otherTab=false},3500)}};
function voices(){return TTS?(speechSynthesis.getVoices()||[]):[]}
function pickV(){const vs=voices();if(!vs.length)return null;if(vcfg.voice){const m=vs.find(v=>v.name===vcfg.voice);if(m)return m}return vs.find(v=>/en[-_]?GB/i.test(v.lang)&&/female|zira|hazel|libby|sonia|aria/i.test(v.name))||vs.find(v=>/^en/i.test(v.lang))||vs[0]}
function busy(){return TTS&&(speechSynthesis.speaking||speechSynthesis.pending)}
function setAv(s){const a=$('#wavatar');if(a)a.className='wren '+(s==='watching'?'idle':s);const st=$('#wstate');if(st)st.textContent=s==='speaking'?'Speaking…':s==='listening'?'Listening…':muted?'Muted':'Watching'}
function stopAll(){if(TTS)speechSynthesis.cancel();setAv('watching')}
function speak(t,o){o=o||{};if(!t||muted||!TTS)return;if(vcfg.overlapGuard){if(!o.interrupt&&busy())return;if(!o.interrupt&&otherTab)return}if(vcfg.pauseWhenHidden&&document.visibilityState==='hidden')return;
 try{speechSynthesis.cancel();const u=new SpeechSynthesisUtterance(t);const v=pickV();if(v)u.voice=v;u.rate=+vcfg.rate||0.9;u.pitch=+vcfg.pitch||1;let vol=+vcfg.volume;if(!(vol>0))vol=1;u.volume=vol;
  u.onstart=()=>{lastAt=Date.now();setAv('speaking');if(bc)bc.postMessage('sp')};u.onend=()=>setAv(commTimer?'watching':'watching');u.onerror=()=>setAv('watching');speechSynthesis.speak(u)}catch(e){}}
function toggleMute(){muted=!muted;$('#muteBtn').textContent=muted?'🔈 Unmute':'🔇 Mute';if(muted)stopAll();toast(muted?'muted':'unmuted')}
function killAudio(){if(commTimer){clearInterval(commTimer);commTimer=null}stopAll();toast('🔴 all speech stopped')}
function toggleAdv(){const a=$('#adv');a.style.display=a.style.display==='none'?'block':'none';if(a.style.display==='block')populateV()}
function populateV(){const s=$('#voiceSel');if(!s||!TTS)return;const vs=voices();if(vs.length)s.innerHTML='<option value="">(auto — best English)</option>'+vs.map(v=>`<option value="${v.name}" ${v.name===vcfg.voice?'selected':''}>${v.name} · ${v.lang}</option>`).join('')}
if(TTS)try{speechSynthesis.onvoiceschanged=populateV}catch(e){}
function vset(k,v){vcfg[k]=v;saveV();if($('#rateV'))$('#rateV').textContent=(+vcfg.rate).toFixed(2);if($('#pitchV'))$('#pitchV').textContent=(+vcfg.pitch).toFixed(2);if($('#volV'))$('#volV').textContent=(+vcfg.volume).toFixed(2)}
document.addEventListener('visibilitychange',()=>{if(document.visibilityState==='hidden'&&vcfg.pauseWhenHidden)stopAll()});
async function loadComm(){try{const d=await j('/api/commentary');commLines=d.lines||[];$('#wadvice').textContent=commLines[0]||'…';const c=d.counts||{};$('#wIssues').textContent=c.issues;$('#wAppr').textContent=c.approvals;$('#wWatched').textContent=c.watched;$('#wCheck').textContent=new Date().toLocaleTimeString()}catch(e){}}
async function speakBrief(){await loadComm();speak(commLines[0],{interrupt:true})}
async function speakUrgent(){const d=await j('/api/guardian_warnings');const w=d.warnings.find(x=>x.sev==='HIGH'||x.sev==='MED');speak(w?('Ross, '+w.warning):'Ross, no urgent issues.',{interrupt:true})}
async function speakAppr(){const d=await j('/api/approvals');speak('Ross, '+(d.queue||[]).length+' approvals are waiting.',{interrupt:true})}
async function speakFuture(){const d=await j('/api/past_present_future');speak('Ross, next: '+(d.future.next_approval||'review approvals')+'. Risk: '+(d.future.risk||''),{interrupt:true})}
function commStep(){if(!commLines.length||busy()||otherTab)return;if(Date.now()-lastAt<4000)return;if(vcfg.pauseWhenHidden&&document.visibilityState==='hidden')return;$('#wadvice').textContent=commLines[commIdx%commLines.length];speak(commLines[commIdx%commLines.length]);commIdx++}
async function startComm(){await loadComm();if(commTimer)clearInterval(commTimer);commIdx=0;commStep();commTimer=setInterval(commStep,vcfg.intervalMs||8000);toast('commentary on')}
function stopComm(){if(commTimer){clearInterval(commTimer);commTimer=null}stopAll();toast('commentary stopped')}
// ---- panels ----
async function loadBrief(){const d=await j('/api/briefing');const blk=(t,a,c)=>`<div class="li">${pill(t)}${(a&&a.filter(Boolean).length)?a.filter(Boolean).join(' · '):'none'}</div>`;
 $('#briefBox').innerHTML=blk('LIVE',d.live,'OK')+blk('STALE',d.stale,'MED')+blk('BLOCKED',d.blocked,'HIGH')+blk('NEEDS APPROVAL',d.needs_approval,'NEEDS')+blk('UNSAFE',d.unsafe,'MED')+`<div class="li"><b>Next safest action:</b> <span style="color:var(--cyan)">${d.next_safest}</span></div>`+'<div class="li"><b>Changed:</b> '+(d.changed||[]).map(r=>r.name).join(', ')+'</div>';
 const p=await j('/api/past_present_future');
 $('#ppfPast').innerHTML='<b>PAST</b><div class="sub">'+p.past.proven+'</div>'+(p.past.reports||[]).map(r=>`<div class="li">${r.name}<br><span style="color:var(--live);font-size:11px">${r.verdict}</span></div>`).join('');
 $('#ppfPresent').innerHTML='<b>PRESENT</b><div class="li">Receptionist reachable: '+p.present.receptionist_reachable+'</div><div class="li">Task Council stale: '+p.present.task_council_stale+' · open '+p.present.task_council_open+'</div><div class="li" style="color:var(--stale)">Blocker: '+p.present.blocker+'</div>';
 $('#ppfFuture').innerHTML='<b>FUTURE</b><div class="li">Next approval: '+p.future.next_approval+'</div><div class="li">When Task Council real: '+p.future.when_task_council_real+'</div><div class="li" style="color:var(--off)">Risk: '+p.future.risk+'</div>';}
async function loadWatch(){const d=await j('/api/watch');$('#watch').innerHTML=d.cards.map(c=>`<div class="node ${cls(c.status)}"><span class="stat">${c.status}</span><b><span class="dot"></span>${c.name}</b><div class="sub">${c.endpoint||''}</div></div>`).join('')}
async function loadRecep(){const d=await j('/api/receptionist_bridge');$('#recepBox').innerHTML=`<div class="li">Receptionist reachable: <b>${d.reachable}</b></div><div class="li">Issues: ${JSON.stringify(d.issue_counts)}</div><div class="li">Checklist waiting: ${d.checklist_open}</div><div class="li">Approvals: ${d.approvals.length}</div><div class="li">Websites needing URL: ${d.websites_needing_url}</div><div class="li">Comms: ${d.comms.map(c=>c[0]+'='+c[1]).join(', ')}</div><div class="li">Network gaps: ${d.network_gaps.join(', ')||'none'}</div><h2>Receptionist issues</h2>`+d.issues.map(i=>`<div class="li">${pill(i.sev)}${i.kind} — ${i.detail}</div>`).join('')}
async function loadAppr(){const d=await j('/api/approvals');$('#apprList').innerHTML=(d.queue||[]).map(a=>`<div class="li">${pill(a.status||'NEEDS APPROVAL')}<b>${a.title||a}</b>${a.why?('<br><span class="sub">'+a.why+'</span>'):''}</div>`).join('')||'<div class="li">none</div>'}
async function loadCouncil(){const d=await j('/api/task_council_bridge');$('#councilBox').innerHTML=`<div class="li">${pill(d.stale?'STALE':'LIVE')}total ${d.total} · open ${d.open} · needs approval ${d.needs_approval} · updated ${d.age_s}s ago</div><div class="li">by state: ${JSON.stringify(d.by_state)}</div><div class="li">TP available: <b>${d.tp_available}</b> · Acer available: <b>${d.acer_available}</b></div><div class="li sub">${d.note}</div>`}
async function loadTeam(){const d=await j('/api/team');$('#team').innerHTML=d.members.map(m=>`<div class="node ${cls(m.status)}"><span class="stat">${m.status}</span><b><span class="dot"></span>${m.name}</b><div class="sub">${m.role}</div><div class="sub">${m.endpoint}</div><div class="sub">exec: <b>${m.can_execute}</b> · verify: <b>${m.can_verify}</b> · self-close: <b style="color:var(--off)">${m.can_self_close}</b></div><div class="sub" style="color:var(--stale)">${m.blockers}</div></div>`).join('')}
async function loadGuard(){const d=await j('/api/guardian_warnings');$('#guard').innerHTML=d.warnings.map(w=>`<div class="li">${pill(w.sev)}${w.warning}</div>`).join('')}
async function loadDrafts(){const d=await j('/api/draft_tasks');$('#drafts').innerHTML=(d.drafts||[]).slice().reverse().map(t=>`<div class="li">${pill('DRAFT ONLY')}<b>${t.title}</b><div class="sub">${t.category} · urgency ${t.urgency} · owner ${t.suggested_owner||'-'} · verifier ${t.suggested_verifier||'-'} · ${t.created_at}</div></div>`).join('')||'<div class="li">no drafts</div>'}
async function loadActivity(){const d=await j('/api/activity');$('#activity').innerHTML=(d.events||[]).map(e=>`<div class="li"><span class="sub">${e.ts}</span> · <b>${e.action}</b> · ${e.actor}${e.item?(' · '+e.item):''}${e.result?(' → '+e.result):''}</div>`).join('')||'<div class="li">no activity</div>'}
async function ap(kind){const r=await post('/api/approval_record',{action:kind});toast('logged: '+kind+' (record only, no execution)');speak('Recorded, '+kind+'.',{interrupt:true});loadActivity()}
async function dec(type,opt){await post('/api/decision',{decision_type:type,option:opt});toast(type+': '+opt+' (logged, no execution)');speak(type+', '+opt,{interrupt:true});loadActivity()}
async function draft(){const t=$('#dtTitle').value.trim();if(!t)return toast('title?');await post('/api/draft_task',{title:t,details:$('#dtDetails').value,urgency:$('#dtUrg').value,category:$('#dtCat').value,suggested_owner:$('#dtOwner').value,suggested_partner:$('#dtPartner').value,suggested_verifier:$('#dtVerifier').value});['dtTitle','dtDetails','dtUrg','dtCat','dtOwner','dtPartner','dtVerifier'].forEach(i=>$('#'+i).value='');toast('draft saved (not submitted)');loadDrafts()}
async function doing(){try{const d=await j('/api/briefing');$('#doing').textContent='Wren is watching 12 systems · next: '+d.next_safest+' · '+new Date().toLocaleTimeString()}catch(e){}}
async function load(){if(cur==='brief')loadBrief();if(cur==='watch')loadWatch();if(cur==='recep')loadRecep();if(cur==='approve')loadAppr();if(cur==='council')loadCouncil();if(cur==='team')loadTeam();if(cur==='guard')loadGuard();if(cur==='drafts')loadDrafts();if(cur==='activity')loadActivity();loadComm();doing();$('#clock').textContent=new Date().toLocaleTimeString()}
renderTabs();go('brief');populateV();setInterval(load,7000);
</script></body></html>"""


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code); self.send_header("Content-Type", ctype); self.send_header("Content-Length", str(len(b)))
        self.send_header("Access-Control-Allow-Origin", "*"); self.end_headers(); self.wfile.write(b)

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
            return self._send(200, PAGE, "text/html; charset=utf-8")
        if p == "/health":
            return self._json(200, {"ok": True, "service": "qsb_wren_concierge_dash", "port": PORT, "ts": now_iso()})
        if p == "/api/state":
            return self._json(200, {"ts": now_iso(), "role": "OBSERVER / GUARDIAN / concierge", "self_execute": False, "self_approve": False, "self_close": False, "port": PORT})
        if p == "/api/briefing":
            return self._json(200, briefing())
        if p == "/api/past_present_future":
            return self._json(200, past_present_future())
        if p == "/api/watch":
            return self._json(200, watch())
        if p == "/api/receptionist_bridge":
            return self._json(200, receptionist_bridge())
        if p == "/api/approvals":
            rb = receptionist_bridge()
            return self._json(200, {"ts": now_iso(), "queue": rb["approvals"]})
        if p == "/api/team":
            return self._json(200, team())
        if p == "/api/task_council_bridge":
            return self._json(200, task_council_bridge())
        if p == "/api/guardian_warnings":
            return self._json(200, guardian_warnings())
        if p == "/api/commentary":
            return self._json(200, commentary())
        if p == "/api/draft_tasks":
            return self._json(200, {"ts": now_iso(), "drafts": load_drafts()})
        if p == "/api/activity":
            return self._json(200, {"ts": now_iso(), "events": list(reversed(read_tail(ACTIVITY, 40)))})
        return self._json(404, {"ok": False, "error": "not found"})

    def do_POST(self):
        p = urlparse(self.path).path
        b = self._body()
        # ALL POST routes are append-only records. No shell, no send, no task submit, no self-close.
        if p == "/api/approval_record":
            a = (b.get("action") or "")[:60]
            log_activity("approval_record", item=a, result="record only (no execution)", actor="ross")
            return self._json(200, append_event({"type": "approval_record", "action": a}))
        if p == "/api/decision":
            dt = (b.get("decision_type") or "")[:20]
            opt = (b.get("option") or "")[:80]
            log_activity("decision_" + dt, item=opt, result="logged (no execution)", actor="ross")
            return self._json(200, append_event({"type": "decision", "decision_type": dt, "option": opt}))
        if p in ("/api/snooze", "/api/reject", "/api/signoff"):
            kind = p.rsplit("/", 1)[1]
            log_activity(kind, item=(b.get("item") or b.get("field") or "")[:60], result=(b.get("value") or "logged")[:40], actor="ross")
            return self._json(200, append_event({"type": kind, **{k: b.get(k) for k in ("item", "field", "value")}}))
        if p == "/api/draft_task":
            return self._json(200, add_draft(b))
        return self._json(404, {"ok": False, "error": "not found"})


def main():
    REG.mkdir(parents=True, exist_ok=True)
    for f in (EVENTS, ACTIVITY):
        if not f.exists():
            f.touch()
    log_activity("concierge_opened", result="Wren Concierge V1 online")
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), H)
    print(f"[wren-concierge] serving on 0.0.0.0:{PORT} (HQ_IP={HQ_IP})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
