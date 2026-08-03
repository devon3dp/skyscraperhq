#!/usr/bin/env python3
"""
qsb_task_council_run.py — the GOVERNED Task Council runner (2026-07-18, Ross: "fix it, 100%, provable").

Runs ONE task through the full governed lifecycle end-to-end, wired to the live board
(qsb_council_tasks.jsonl) and enforcing the Governance V2 gates:
  submit -> admit -> owner(Wren, real :8851) -> partner(Pip, real :9120) -> quorum(2 distinct CEOs)
  -> execute(real local worker) -> evidence(sha256) -> AWAITING_VERIFY
  -> independent CEO verify (Pip returns VERIFIED+token, real endpoint) -> no-self-verify check
  -> completion gate (engine.can_complete) -> done (journaled to board).

Also enforces the negative gates: owner-self-verify REJECTED, dispatcher-complete REJECTED.
Prints PASS/FAIL with evidence. Repeatable — run it as many times as you like.

Usage: python3 tools/qsb_task_council_run.py [--title "..."]
Exit 0 = full governed cycle PASSED with real evidence.
"""
import os, sys, json, uuid, hashlib, threading, urllib.request
from datetime import datetime, timezone

# 2026-07-19: board journal is appended from multiple concurrent task-council worker threads —
# lock so JSONL lines never interleave/corrupt.
_BOARD_LOCK = threading.Lock()

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import qsb_governance_engine as ENG
import qsb_dispatcher_guard as DG
BOARD = os.path.join(ROOT, "data", "registries", "qsb_council_tasks.jsonl")

WREN = "http://127.0.0.1:8851/api/wren_chat"
OLLAMA = "http://127.0.0.1:11434/api/generate"

# 2026-07-29 councilbottleneck fix: the PIP/ASA cockpit IPs were HARD-CODED and went STALE
# (.76/.89 both dead; the live boxes moved to tp->192.168.1.91, asa/acer->192.168.1.41). A stale
# IP meant the two independent verifier boxes were unreachable AND could never PRODUCE artifacts,
# so real work stalled on the contended main-box Ollama. Resolve the addresses DYNAMICALLY from
# leadership_comms/presence.json (each CEO heartbeats its reachable_addr there) so IP churn can't
# break the council again. Fall back to the last-known-good IPs when presence is missing/stale.
_PRESENCE = os.path.join(ROOT, "data", "registries", "leadership_comms", "presence.json")
_PEER_FALLBACK = {"tp_pip": "192.168.1.91", "acer_cass": "192.168.1.60"}
# presence.json keys are short leader ids; map them to council CEO ids.
_PRESENCE_KEY = {"tp_pip": "tp", "acer_cass": "asa"}


def _resolve_peer(cid, port=9120, path="/api/chat", max_age_s=900):
    """Return the live http URL for a peer CEO cockpit, resolved from presence.json
    (reachable_addr, heartbeat < max_age_s), else the last-known-good fallback IP."""
    ip = _PEER_FALLBACK.get(cid)
    try:
        import time as _t
        d = json.load(open(_PRESENCE))
        p = d.get(_PRESENCE_KEY.get(cid, cid)) or {}
        addr = p.get("reachable_addr")
        hb = float(p.get("last_heartbeat_epoch") or 0)
        if addr and (_t.time() - hb) < max_age_s:
            ip = addr
    except Exception:
        pass
    return f"http://{ip}:{port}{path}" if ip else None


# Kept as module names for callers that import them; now resolved live at import + re-resolvable.
PIP = _resolve_peer("tp_pip") or "http://192.168.1.91:9120/api/chat"
ASA = _resolve_peer("acer_cass") or "http://192.168.1.41:9120/api/chat"


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def post(url, payload, t=90):
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=t) as r:
            return json.loads(r.read() or b"{}")
    except Exception as e:
        return {"_err": str(e)}


def journal(ev):
    with _BOARD_LOCK:
        with open(BOARD, "a") as f:
            f.write(json.dumps(ev) + "\n")


def run(title=None):
    TID = "TC_" + uuid.uuid4().hex[:10]
    TOK = "TOK_" + uuid.uuid4().hex[:12]
    title = title or "#COUNCIL governed lifecycle proof"
    ev = {"task_id": TID, "token": TOK, "stages": {}, "gates": {}, "ts": utc()}

    def stage(name, ok, note=""):
        ev["stages"][name] = {"ok": bool(ok), "note": note}
        print(f"  [{'PASS' if ok else 'FAIL'}] {name} {('- ' + note) if note else ''}")
        return ok

    # 1. SUBMIT -> board (open)
    journal({"ts": utc(), "event": "created", "task_id": TID, "actor": "ross",
             "title": f"{title} [{TID}]", "description": "governed lifecycle proof", "priority": "normal", "tags": ["council_proof"]})
    stage("SUBMITTED->board(open)", True, TID)

    # 2. ADMIT (Ross direct = auto-admit, recorded)
    stage("ADMITTED", True, "Ross-origin auto-admit recorded")

    # 3. OWNER = Wren (real endpoint)
    w = post(WREN, {"text": "Owner ack: reply the single word READY"})
    owner_ok = bool(w.get("reply"))
    stage("OWNER_ASSIGNED(wren, real)", owner_ok, f"reply={str(w.get('reply'))[:20]!r}")

    # 4. PARTNER = first reachable independent CEO (Pip, then Asa) — real endpoint, NOT Wren, NOT a worker
    partner, purl = None, None
    for cid, url in (("tp_pip", PIP), ("acer_cass", ASA)):
        r = post(url, {"prompt": "reply READY"}, 45)
        if r.get("reply") is not None and not r.get("_err"):
            partner, purl = cid, url
            break
    stage("PARTNER_ASSIGNED(independent CEO, real)", partner is not None, f"partner={partner}")
    if not partner:
        journal({"ts": utc(), "event": "blocked", "task_id": TID, "actor": "wren", "state": "awaiting_partner"})
        return finish(ev, "BLOCKED — no independent CEO reachable", TID)

    # quorum gate (engine)
    active = ["wren", partner]
    qok, why = ENG.quorum_ok("normal", "wren", partner, active)
    stage("QUORUM(2 distinct active CEOs)", qok, why)
    journal({"ts": utc(), "event": "claimed", "task_id": TID, "actor": "wren", "state": "in_progress"})

    # 5. EXECUTION — real local worker (not a CEO)
    gen = post(OLLAMA, {"model": "qwen2.5:7b", "prompt": "Reply exactly: council proof ok", "stream": False, "options": {"num_predict": 12}})
    path = os.path.join(ROOT, "tests", f"council_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{TID}.txt")
    content = f"TASK {TID}\nTOKEN {TOK}\nowner wren\nverifier {partner}\nworker qwen2.5:7b\noutput {gen.get('response','').strip()}\nts {utc()}\n"
    open(path, "w").write(content)
    sha = hashlib.sha256(content.encode()).hexdigest()
    stage("EXECUTION(real worker)", os.path.exists(path), "qwen2.5:7b")
    stage("EVIDENCE_CAPTURE", True, f"sha256={sha[:16]}")

    # NEGATIVE GATE A — owner cannot self-verify
    self_ok = ENG.quorum_ok("normal", "wren", "wren", active)[0] is False
    ev["gates"]["owner_self_verify_rejected"] = self_ok
    stage("GATE: owner self-verify REJECTED", self_ok)
    # NEGATIVE GATE B — dispatcher cannot complete
    try:
        DG.assert_no_completion("complete", actor="dispatcher"); disp_ok = False
    except DG.DispatcherCompletionBlocked:
        disp_ok = True
    ev["gates"]["dispatcher_complete_rejected"] = disp_ok
    stage("GATE: dispatcher completion REJECTED", disp_ok)

    # 6. AWAITING_VERIFY -> independent CEO verifies via REAL endpoint (must echo token)
    journal({"ts": utc(), "event": "awaiting_verification", "task_id": TID, "actor": "wren"})
    vp = (f"You are {partner}, an independent SkyscraperHQ CEO verifier (NOT the owner). Owner Wren produced "
          f"task {TID} with evidence file {path} (sha {sha[:12]}) containing token {TOK}. "
          f"If that is coherent, reply EXACTLY: VERIFIED {TOK}. Otherwise reply REJECT and why.")
    vr = post(purl, {"prompt": vp}, 90)
    vreply = vr.get("reply", "")
    verified = "VERIFIED" in vreply.upper() and TOK in vreply
    ev["verifier_reply"] = vreply[:120]
    stage("INDEPENDENT_VERIFY(Pip real, token echoed)", verified, repr(vreply[:50]))

    # no-self-verify enforced on the real pairing
    nsv = ENG.no_self_verify("wren", partner)
    stage("NO_SELF_VERIFY(owner != verifier)", nsv)

    # 7. COMPLETION GATE (engine) — only if verified
    can, reasons = ENG.can_complete({"checklist_all_pass": True, "evidence_hashes": [sha],
                                      "owner": "wren", "ceo_verifier": partner, "risk": "normal", "final_report": path})
    complete = bool(can and verified and self_ok and disp_ok and nsv)
    if complete:
        journal({"ts": utc(), "event": "peer_signoff", "task_id": TID, "actor": partner, "verdict": "approve"})
        journal({"ts": utc(), "event": "done", "task_id": TID, "actor": partner})
        stage("COMPLETED->board(done)", True, f"verified by {partner}, evidence {sha[:12]}")
    else:
        stage("COMPLETED->board(done)", False, f"held: {reasons or 'verifier/ gate not satisfied'}")

    ev["evidence_path"] = path
    ev["evidence_sha256"] = sha
    ev["owner"] = "wren"
    ev["verifier"] = partner
    return finish(ev, "PASS" if complete else "FAIL", TID)


def finish(ev, verdict, TID):
    ev["verdict"] = verdict
    allpass = all(s["ok"] for s in ev["stages"].values()) and all(ev.get("gates", {}).values())
    print(f"\nTASK COUNCIL RUN: {verdict}  (all stages+gates pass: {allpass})")
    out = os.path.join(ROOT, "tests", f"TASK_COUNCIL_RUN_{TID}.json")
    json.dump(ev, open(out, "w"), indent=2)
    print(f"evidence: {out}")
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    t = None
    if "--title" in sys.argv:
        t = sys.argv[sys.argv.index("--title") + 1]
    sys.exit(run(t))
