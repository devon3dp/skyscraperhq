#!/usr/bin/env python3
"""
qsb_ceo_task_worker.py — makes tp_pip, acer_cass and bill genuinely TASK-DRIVEN.

Ross 2026-07-28: "get everyone task driven even bill use his work mode".

Wren (qsb_task_council_autorunner) and Codex (qsb_codex_autorunner) are ALREADY
task-driven. This loop covers the three leadership CEOs that were NOT:

  · TP   (tp_pip)     -> real mind at his :9120 cockpit  (llama3.2)
  · Asa  (acer_cass)  -> real mind at her :9120 cockpit  (llama3.2)
  · Bill (bill)       -> real mind on his Mac, reached via the leadership RELAY
                         (his qsb_bill_responder posts back to the room). Bill
                         only claims tasks when his WORK MODE is active.

Per tick, for each CEO with free capacity:
  1. respect a per-CEO in-flight cap (default 1) so they never clog the 3/CEO
     council cap or fight Wren/Codex.
  2. pick ONE real open backlog task (same real() filter as the autorunners),
     skipping tasks already owned by anyone.
  3. claim it as that CEO (qsb_council_tasks.claim).
  4. delegate the ACTUAL WORK to that CEO's own mind (cockpit / responder) and
     capture the REAL reply as the artifact.
  5. note the real artifact on the task (qsb_council_tasks.note).
  6. does NOT self-verify or mark done — the existing 2-CEO gene-pool quorum in
     Wren's autorunner verifies. "Taker can't sign off own" stays intact.

For BILL: work mode is activated/refreshed via the governed tool
qsb_bill_work_mode (mode=work, enabled, fresh lease, heartbeat, endpoint probe
against his live responder). Bill only claims when work mode is ACTIVE. If his
mind can't be reached, he is SKIPPED and logged honestly — never faked.

Kill switch: data/registries/qsb_autorunner_gate.json enabled=false stops it
(shared with the other autorunners). Non-autonomous-worker note: Ross explicitly
ordered this loop; it is bounded (1 task/CEO/tick, real-mind-backed notes only,
never self-verifies, kill-switchable).

Run one proof tick:  python3 tools/qsb_ceo_task_worker.py --once
"""
import os
import sys
import json
import time
import re
import uuid
import urllib.request
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import qsb_council_tasks as T          # noqa: E402
import qsb_bill_work_mode as BILL       # noqa: E402
import qsb_bill_mode as BILLMODE        # noqa: E402  high-level mode (work|concierge|both)
import qsb_federation as FED            # noqa: E402  drift-proof box address resolver

REG = os.path.join(ROOT, "data", "registries")
GATE = os.path.join(REG, "qsb_autorunner_gate.json")
ACT = os.path.join(REG, "qsb_ceo_task_worker_activity.jsonl")

INTERVAL = int(os.environ.get("CEO_WORKER_INTERVAL", "120"))
PER_CEO_CAP = int(os.environ.get("CEO_WORKER_PER_CAP", "1"))

# Verified reachable minds (Ross 2026-07-28 directive).
# 2026-07-30 (F08 IP-drift fix): cockpit URLs resolve via qsb_federation (mDNS,
# drift-proof) instead of hardcoded IPs. The old acer_cass .41 dial went dead on
# every DHCP lease change (Acer .41 -> .60). Env overrides still win.
COCKPITS = {
    "tp_pip": os.environ.get("TP_COCKPIT")
        or FED.cockpit_url("tp_pip") or "http://DESKTOP-9RBVKSM.local:9120/api/chat",
    "acer_cass": os.environ.get("ASA_COCKPIT")
        or FED.cockpit_url("acer_cass") or "http://DESKTOP-1E2FB5N.local:9120/api/chat",
}

# Bill is reached through the leadership relay (he has no cockpit — his Mac
# responder posts back to the room). We DM him as 'wren' and read his room reply.
RELAY = os.environ.get("QSB_RELAY", "http://192.168.1.72:8855")
ROOM_LOG = os.path.join(REG, "leadership_comms", "room.jsonl")
VAULT_TOKENS = os.path.join(ROOT, "floors", "floor_28_security_department",
                            "vault", "leadership_tokens.json")


def utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def log(rec):
    rec["ts"] = utc()
    with open(ACT, "a") as f:
        f.write(json.dumps(rec) + "\n")


def gate_enabled():
    try:
        return bool(json.load(open(GATE)).get("enabled", True))
    except Exception:
        return True  # default on; create gate with enabled=false to stop


# ─── real backlog task selection (mirrors the autorunners' real() filter) ────
def real(t):
    tid = t.get("id", "") or ""
    title = (t.get("title") or "")
    return ("council_proof" not in (t.get("tags") or [])
            and "AUTO" not in title
            and "#TEST" not in title.upper()
            and not tid.startswith("t_test"))


def _owned_ids(tasks):
    """Set of task ids currently owned/held by anyone (so we never double-grab)."""
    held = {}
    for t in tasks:
        st = (t.get("state") or "").lower()
        if st in ("claimed", "in_progress", "assigned", "acknowledged",
                  "awaiting_peer_signoff", "awaiting_verification", "needs_rework"):
            if t.get("owner"):
                held.setdefault(t.get("owner"), 0)
                held[t["owner"]] += 1
    return held


def inflight_for(ceo, tasks):
    return sum(1 for t in tasks
               if t.get("owner") == ceo
               and (t.get("state") or "").lower() in (
                   "claimed", "in_progress", "assigned", "acknowledged",
                   "awaiting_peer_signoff", "awaiting_verification", "needs_rework"))


# ─── capability-aware dispatch (Ross 2026-08-04) ─────────────────────────────
# The CEOs this worker drives (tp_pip, acer_cass, bill) are ANALYSIS minds, not
# coders. Feeding them CODE/DEPLOY tasks pins them at their 3-task cap with work
# they can never ship (why tp_pip had 0 completions). Classify the backlog so they
# take analysis/inspection/decision work and leave code for the coders (Codex/Wren).
_CODE_RX = re.compile(
    r"(\bendpoint\b|/api/|\.py\b|\.js\b|\.html\b|\.css\b|\.sh\b|\bsystemd\b|\bservice\b|"
    r"\bdeploy\b|\bpatch\b|\bwire\b|\bimplement\b|\brefactor\b|\bmigrat|\binstall\b|"
    r"\bcockpit\b|\bjavascript\b|\bscript\b|\btraceback\b|\bstack ?trace\b|\bcodebase\b|"
    r"add .*\bendpoint\b|\bfix\b.*\b(bug|service|import|module|crash)\b)", re.I)
_ANALYSIS_RX = re.compile(
    r"(\binspect|\breport\b|\banaly[sz]|\bassess|\breview\b|\baudit\b|\bclassif|\bsummar|"
    r"\bdecide\b|\brecommend|\bhealth\b|\bstatus\b|\bdiagnos|\bevaluat|\bcompare\b|"
    r"\bresearch\b|\binvestigat|\btop risk\b|healthy vs|degraded)", re.I)


def _task_capability(task):
    """'code' → route to coders; 'analysis' → box CEOs' analysis minds can ship it.
    Analysis INTENT wins over incidental code nouns: 'classify systemd services healthy
    vs degraded' is analysis even though it says 'service'."""
    blob = ((task.get("title") or "") + " " + (task.get("description") or "")).lower()
    if _ANALYSIS_RX.search(blob):
        return "analysis"
    if _CODE_RX.search(blob):
        return "code"
    return "analysis"   # ambiguous → a note/analysis is a real deliverable


def pick_open_task(tasks, exclude=None, ceo=None):
    """Oldest real, open, UNOWNED backlog task, skipping any id in `exclude`.
    Capability-aware: when picking for one of this worker's analysis-mind CEOs,
    skip CODE/DEPLOY tasks (left for the coders) so they take work they can finish."""
    exclude = exclude or set()
    opens = [t for t in tasks
             if t.get("state") == "open" and not t.get("owner") and real(t)
             and t.get("id") not in exclude]
    if ceo:   # all CEOs this worker drives are analysis minds, not coders
        opens = [t for t in opens if _task_capability(t) != "code"]
    opens.sort(key=lambda t: t.get("created_at", ""))
    return opens[0] if opens else None


# ─── delegating the real work to each CEO's own mind ─────────────────────────
def cockpit_ask(url, prompt, timeout=150):
    """POST {'prompt': ...} to a :9120 cockpit -> real {'reply': ...}."""
    body = json.dumps({"prompt": prompt}).encode()
    req = urllib.request.Request(url, data=body,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read() or b"{}")
    return (d.get("reply") or "").strip(), d


def _wren_token():
    return json.load(open(VAULT_TOKENS))["tokens"]["wren"]


def _relay_call(path, method="GET", payload=None, timeout=8):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(RELAY + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method=method)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"{}")


def _room_tail(n=60):
    try:
        with open(ROOM_LOG) as f:
            lines = f.readlines()[-n:]
    except Exception:
        return []
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except Exception:
            pass
    return out


def bill_probe(timeout_wait=45):
    """Round-trip Bill's real mind through the relay: DM him a unique token as
    'wren', wait for his responder to post the echoed token back to the room.
    Returns True if Bill's mind answered (endpoint_probe_ok)."""
    tok = "PROBE-" + uuid.uuid4().hex[:10]
    try:
        _relay_call("/dm", "POST", {
            "identity": "wren", "token": _wren_token(), "to": "bill",
            "body": f"Bill, reply with the exact word {tok} to confirm your responder is live.",
            "msg_id": "m_" + uuid.uuid4().hex[:16]})
    except Exception as e:
        log({"bill_probe": "dm_failed", "error": str(e)[:160]})
        return False
    deadline = time.time() + timeout_wait
    while time.time() < deadline:
        time.sleep(5)
        for m in reversed(_room_tail(40)):
            if m.get("from") == "bill" and tok in (m.get("body") or ""):
                return True
    return False


def bill_ask(prompt, timeout_wait=None):
    """Send Bill a task via the relay and capture his REAL room reply.
    Bill's Mac (qwen2.5:14b) is slow and his inbox interleaves other leadership
    chatter, so we wait generously and accept the FIRST fresh bill room post
    after we sent (his responder replies to our DM by posting to the room)."""
    if timeout_wait is None:
        timeout_wait = int(os.environ.get("BILL_WAIT_S", "300"))
    marker = "TASKREF-" + uuid.uuid4().hex[:8]
    # timestamp baseline (robust to room churn): only accept bill posts strictly
    # newer than the moment we send.
    sent_ts = utc()
    framed = (f"[{marker}] Council task for you, Bill. Do the work with your own "
              f"judgement and reply with your concrete result.\n\n{prompt}\n\n"
              f"(End your reply so it is self-contained.)")
    try:
        _relay_call("/dm", "POST", {
            "identity": "wren", "token": _wren_token(), "to": "bill",
            "body": framed, "msg_id": "m_" + uuid.uuid4().hex[:16]})
    except Exception as e:
        return "", f"relay_dm_failed: {e}"
    # ignore Bill's short echo/status one-liners; wait for his real task answer
    def _substantive(b):
        return len(b) > 60 and not b.startswith(("PROBE-", "PONG-", "WB-"))
    deadline = time.time() + timeout_wait
    while time.time() < deadline:
        time.sleep(5)
        for m in reversed(_room_tail(120)):
            if m.get("from") != "bill":
                continue
            if (m.get("ts") or "") <= sent_ts:
                break  # reached posts older than our send; stop scanning back
            body = (m.get("body") or "").strip()
            if _substantive(body):
                return body, "ok"
    return "", "timeout_no_room_reply"


def ensure_bill_work_mode():
    """Activate/refresh Bill's work mode via the governed tool. Only report
    active=True when his mind actually answers (endpoint_probe_ok)."""
    probe_ok = bill_probe()
    BILL.enable("qsb_ceo_task_worker", "task-driven activation (Ross 2026-07-28)",
                lease_seconds=3600)
    BILL.heartbeat(endpoint_ok=probe_ok)
    st = BILL.status()
    return bool(st.get("counts_for_quorum")) and probe_ok, st


# ─── the per-CEO worker ──────────────────────────────────────────────────────
def build_prompt(task):
    """Concise prompt. The :9120 cockpits run a small local model with an
    internal ~120s ceiling — a verbose prompt makes them over-generate and hit
    that ceiling. Keep it tight and bound the answer so we get REAL content back."""
    title = (task.get("title") or "").strip()
    desc = (task.get("description") or "").strip()[:400]
    p = f"Council task {task['id']}: {title}."
    if desc:
        p += f" Details: {desc}."
    p += (" In 4-6 concrete sentences, give your specific plan or result for this "
          "task using your own judgement. Be concrete and self-contained.")
    return p


def work_one(ceo, task):
    """Claim `task` as `ceo`, delegate to that CEO's real mind, note the real
    artifact. Returns a result dict. Never marks done / self-verifies."""
    tid = task["id"]
    prompt = build_prompt(task)

    claim = T.claim(tid, ceo)
    if not claim.get("ok"):
        return {"ceo": ceo, "task": tid, "result": "claim_blocked",
                "detail": claim.get("error") or claim.get("detail")}

    # delegate to the real mind
    try:
        if ceo == "bill":
            reply, why = bill_ask(prompt)
        else:
            reply, _raw = cockpit_ask(COCKPITS[ceo], prompt)
            why = "ok" if reply else "empty_reply"
    except Exception as e:
        reply, why = "", f"mind_error: {e}"

    # A cockpit that fails internally returns an HONEST failure sentinel as the
    # 'reply' (e.g. "LOCAL GENERATION FAILED ... not fabricating"). Treat that as
    # a skip, NOT a real artifact — never note a non-answer as work.
    if reply and ("LOCAL GENERATION FAILED" in reply
                  or "not fabricating" in reply.lower()
                  or reply.lower().startswith("(bill's local model error")):
        why = "cockpit_generation_failed"
        reply = ""

    if not reply:
        # HONEST: mind unreachable / empty. RELEASE the claim (clear owner, back
        # to open) so it doesn't clog this CEO's cap, and log a skip — never
        # fabricate an artifact.
        try:
            T.update(tid, ceo, state="open", owner="")
            T.note(tid, ceo, f"[{ceo}] released: own mind unreachable ({why}); back to pool")
        except Exception:
            pass
        return {"ceo": ceo, "task": tid, "result": "skip_no_reply", "detail": why}

    # real artifact -> note it on the task (this is what makes them task-driven)
    note = (f"[{ceo} own mind] {reply}")[:4000]
    T.note(tid, ceo, note)
    return {"ceo": ceo, "task": tid, "result": "noted",
            "reply_snippet": reply[:200], "chars": len(reply)}


def tick():
    if not gate_enabled():
        log({"tick": "paused", "reason": "kill switch enabled=false"})
        return
    # 2026-07-30 WIP-CAP: recycle stale claimed/in_progress orphans back to the pool so they stop
    # holding this CEO's cap slot (also runs in the autorunner; either loop keeps the board clean).
    # T.claim() below already enforces both the per-CEO cap and the new global WIP ceiling.
    try:
        _r = T.reap_stale_claims()
        if _r.get("reaped"):
            log({"tick": "stale_reaped", "count": _r["reaped"],
                 "ids": [t["id"] for t in _r.get("tasks", [])]})
    except Exception as e:
        log({"tick": "reap_error", "error": str(e)[:160]})
    # Apply any pending mode-switch beacon Bill posted (Ross's relay command loop).
    try:
        import qsb_bill_mode_apply as MA
        MA.apply_once(verbose=False)
    except Exception as e:
        log({"tick": "mode_apply_error", "error": str(e)[:160]})

    snap = T.snapshot()
    tasks = snap.get("tasks", [])

    # Bill's HIGH-LEVEL mode gates whether he works at all. In concierge mode he
    # does NOT claim council tasks (he only monitors). In work/both mode he does.
    bill_work_ok = BILLMODE.work_allowed()
    bill_high_mode = BILLMODE.get_mode()
    if not bill_work_ok:
        log({"tick": "bill_mode_gate", "high_mode": bill_high_mode,
             "reason": "concierge mode — Bill does not claim council tasks this tick"})
        bill_active = False
        bill_st = BILL.status()
    else:
        # Bill is in work/both: activate/refresh his work lease; only claim when his
        # real mind actually answered the probe (endpoint_probe_ok). Never faked.
        bill_active, bill_st = ensure_bill_work_mode()
    log({"tick": "bill_work_mode",
         "high_mode": bill_high_mode,
         "work_allowed": bill_work_ok,
         "active": bill_active,
         "mode": bill_st.get("mode"),
         "counts_for_quorum": bill_st.get("counts_for_quorum"),
         "endpoint_probe_ok": bill_st.get("endpoint_probe_ok"),
         "lease_expires_at": bill_st.get("lease_expires_at")})

    ceos = ["tp_pip", "acer_cass"] + (["bill"] if bill_active else [])
    if not bill_active:
        log({"tick": "bill_skip",
             "reason": ("concierge mode (not working)" if not bill_work_ok
                        else "work mode not active (mind unreachable)")})

    results = []
    attempted = set()  # tasks touched this tick — don't let CEOs pile onto one
    for ceo in ceos:
        # re-snapshot each time so a claim we just made is reflected
        tasks = T.snapshot().get("tasks", [])
        load = inflight_for(ceo, tasks)
        # Bill's cap is mode-aware: 'both' caps him low (work_cap_both) so his
        # concierge monitoring is never starved; pure 'work' uses BILL_WORK_CAP.
        cap = BILLMODE.work_cap() if ceo == "bill" else PER_CEO_CAP
        if cap <= 0 or load >= cap:
            log({"tick": "ceo_at_cap", "ceo": ceo, "inflight": load, "cap": cap})
            continue
        task = pick_open_task(tasks, exclude=attempted, ceo=ceo)
        if not task:
            log({"tick": "no_open_task", "ceo": ceo, "reason": "no analysis-suited open task"})
            continue
        attempted.add(task["id"])
        log({"tick": "delegating", "ceo": ceo, "task": task["id"],
             "title": (task.get("title") or "")[:70]})
        r = work_one(ceo, task)
        log({"tick": "worked", **r})
        results.append(r)
    return results


def main():
    log({"event": "ceo_task_worker_start", "interval_s": INTERVAL,
         "per_ceo_cap": PER_CEO_CAP, "ceos": ["tp_pip", "acer_cass", "bill"],
         "pid": os.getpid()})
    while True:
        try:
            tick()
        except Exception as e:
            log({"tick": "error", "error": str(e)[:200]})
        time.sleep(INTERVAL)


if __name__ == "__main__":
    if "--once" in sys.argv:
        tick()
        print("one tick logged to", ACT)
    else:
        main()
