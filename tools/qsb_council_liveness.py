#!/usr/bin/env python3
"""qsb_council_liveness.py — Task-Council-side REAL liveness + physical-CEO
identity gate (Phase 3, Claude 2026-08-03).

WHY (proven defect):
  The Task Council could not tell a genuine physical CEO from an offline node or
  a surrogate identity, so:
    · offline principals were still assignable/claimable (silence != agreement),
    · Asa (acer_cass) FALSE-NEGATIVED as offline because the shared resolver
      qsb_federation.py pins the cockpit to COCKPIT_PORT=9120, but Asa's real
      cockpit answers on :9000 (only TP's is on :9120), and
    · presence.json `status` is unreliable (verified 2026-08-03: it reported
      wren + asa "offline" while both runtimes answered HTTP 200).

WHAT this adds (Task-Council-side ONLY — qsb_federation.py is left untouched):
  A REAL per-principal liveness probe that proves the CORRECT PHYSICAL HOST plus
  a RESPONDING LOCAL RUNTIME (HTTP 200 AND an identity token in the body — not a
  generic ping). It reuses qsb_federation ONLY for the drift-proof HOST (mDNS)
  and supplies its OWN port candidates so Asa is probed on :9000 AND :9120 (the
  narrow fix), while TP stays correct on :9120.

CANONICAL PHYSICAL PRINCIPALS (a principal counts as participating ONLY from its
genuine physical host + local mind):
    wren      = MSI Linux tower box, local mind bench :8851
    tp_pip    = ThinkPad DESKTOP-9RBVKSM.local, cockpit :9120
    acer_cass = Acer   DESKTOP-1E2FB5N.local, cockpit :9000 (or :9120 — whichever answers)
    bill      = MacBook, responder reached via presence reachable_addr

Specialists (codex / hermes / iquest) and Claude are NOT physical CEOs: they may
still claim non-leadership work, but they can NEVER satisfy the physical-CEO
requirement in assignment governance, and an identity that IMPERSONATES a CEO
name (e.g. "wren_v2", "tp_pip_backup") is refused as a surrogate.

Reversible: import-only + env kill switch COUNCIL_LIVENESS_GATE (default on).
No network calls or file reads at import.
"""
from __future__ import annotations

import json
import os
import re
import socket
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

try:
    import qsb_federation as FED
except Exception:  # federation missing — fall back to hardcoded mDNS below
    FED = None

# ─── config (env-tunable, no I/O at import) ──────────────────────────────────
PROBE_TIMEOUT = float(os.environ.get("COUNCIL_LIVENESS_TIMEOUT", "2.5"))
CACHE_TTL = float(os.environ.get("COUNCIL_LIVENESS_TTL", "20"))

# Fallback hosts (drift-proof mDNS) if federation is unavailable. Federation is
# PREFERRED (it tracks DHCP drift), but we never hardcode a raw IP for tp/asa.
_FALLBACK_HOST = {
    "wren": "127.0.0.1",
    "tp_pip": "DESKTOP-9RBVKSM.local",
    "acer_cass": "DESKTOP-1E2FB5N.local",
    # bill: relay/presence-managed, no mDNS — resolved from presence only
}

# Per-principal probe candidates: (port, path, [identity tokens]). The probe is
# ONLINE only on HTTP 200 with an identity token present — proving the right
# runtime, not just an open port. Candidates are tried in order; the FIRST that
# answers with a matching identity wins (this is the ":9000 OR :9120" fix).
PRINCIPALS = {
    "wren": [
        (8851, "/", ["wren"]),  # title "Wren · Bench"
    ],
    "tp_pip": [
        (9120, "/health", ["tp_pip", "desktop-9rbvksm"]),
        (9120, "/api/identity", ["tp_pip", "desktop-9rbvksm"]),
        (9120, "/", ["tp-pip", "cockpit"]),
    ],
    "acer_cass": [
        (9000, "/health", ["acer-cass", "acer-data-foundry"]),  # REAL cockpit :9000
        (9120, "/health", ["acer-cass", "acer_cass"]),          # legacy :9120 if it ever answers
        (9000, "/", ["acer-cass", "acer-data-foundry"]),
    ],
    "bill": [
        (8899, "/", ["bill"]),
        (8898, "/health", ["bill"]),
    ],
}

# ─── canonical identity model ────────────────────────────────────────────────
# ONLY the real physical principals resolve to a canon id. Everything else is a
# specialist, a retired identity, a CEO-impersonating surrogate, or a benign
# non-CEO actor.
_CANON_ALIASES = {
    "wren": "wren",
    "tp": "tp_pip", "tp_pip": "tp_pip", "pip": "tp_pip",
    "asa": "acer_cass", "acer": "acer_cass", "acer_cass": "acer_cass", "cass": "acer_cass",
    "bill": "bill",
}
# Leadership name tokens — an unknown identity carrying one of these but NOT a
# recognised alias is treated as an impersonation/surrogate.
_CEO_TOKENS = {"wren", "tp", "pip", "asa", "acer", "cass", "bill"}
# Retired — Claude HQ resigned; Claude is a caged specialist, never a CEO.
DENY_IDENTITIES = {"claude", "hq_claude", "claude_specialist", "claude_hq"}
# Known legitimate non-CEO workers: allowed to claim non-leadership work, but they
# never count as a physical CEO.
SPECIALISTS = {
    "codex", "hermes", "hermes_fast", "hermes_smart", "iquest", "iquest_coder",
    "qwen", "deepseek", "deepseek_coder", "deepseek-coder", "openai", "gene_pool",
    "brain_router", "oracle",
}

PHYSICAL_CEOS = ("wren", "tp_pip", "acer_cass", "bill")

# ─── probe cache (populated on call, never at import) ─────────────────────────
_probe_cache: dict[str, tuple[float, dict]] = {}


def gate_enabled() -> bool:
    return os.environ.get("COUNCIL_LIVENESS_GATE", "1") not in ("0", "false", "False", "no")


def canonical_ceo(actor: str) -> str | None:
    """Map an actor string to a canonical physical-CEO id, else None."""
    return _CANON_ALIASES.get((actor or "").strip().lower())


def _tokens(a: str) -> set:
    return set(t for t in re.split(r"[^a-z0-9]+", (a or "").lower()) if t)


def identity_check(actor: str) -> dict:
    """Classify an identity.
    Returns {ok, klass, canon, reason}. klass ∈
      physical_ceo | specialist | retired | surrogate | non_ceo_actor.
    ok=False for retired + surrogate (they may not act as leadership)."""
    a = (actor or "").strip().lower()
    if not a:
        return {"ok": False, "klass": "surrogate", "canon": None, "reason": "empty_identity"}
    if a in DENY_IDENTITIES:
        return {"ok": False, "klass": "retired", "canon": None,
                "reason": "retired_identity_cannot_act_as_ceo"}
    canon = _CANON_ALIASES.get(a)
    if canon:
        return {"ok": True, "klass": "physical_ceo", "canon": canon, "reason": "canonical_physical_ceo"}
    if a in SPECIALISTS:
        return {"ok": True, "klass": "specialist", "canon": None, "reason": "specialist_not_a_ceo"}
    # impersonation: carries a leadership token but is not a recognised alias
    if _tokens(a) & _CEO_TOKENS:
        return {"ok": False, "klass": "surrogate", "canon": None,
                "reason": "surrogate_impersonating_ceo_identity"}
    return {"ok": True, "klass": "non_ceo_actor", "canon": None, "reason": "non_ceo_actor"}


def is_physical_ceo(actor: str) -> bool:
    return identity_check(actor).get("klass") == "physical_ceo"


# ─── real host + runtime probe ───────────────────────────────────────────────
def _host_for(canon: str) -> str | None:
    if FED is not None:
        try:
            addr = FED.home_addr(canon, prefer_local=(canon == "wren"))
            if addr:
                return addr
        except Exception:
            pass
    return _FALLBACK_HOST.get(canon)


def _http(host: str, port: int, path: str, timeout: float) -> tuple[int | None, str]:
    url = f"http://{host}:{port}{path}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "qsb-council-liveness"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.getcode()
            body = r.read(4096).decode("utf-8", "ignore")
        return code, body
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception:
        return None, ""


# ─── RELAY HEARTBEAT liveness (Phase-3 Bill-fix, Claude 2026-08-03) ───────────
# The leadership relay (:8855 /presence) is the authoritative liveness source: each
# principal's relay client heart-beats from its OWN physical host, so a FRESH heartbeat
# proves that principal's runtime is alive + connected. This is the ONLY correct signal
# for outbound-only Bill (he serves no inbound port) and it fixes the false-negative
# where inbound HTTP probes reported a genuinely-online principal OFFLINE (Ross 2026-08-03:
# "bill is online" — SSH-proven: com.qsb.bill.responder running on his Mac + relay age 8s).
# Age-gated: a dead principal (heartbeat stops) still goes OFFLINE. The inbound HTTP probe
# below stays as fallback / corroboration for principals that DO serve an endpoint.
RELAY_HOST = os.environ.get("COUNCIL_RELAY_HOST", "127.0.0.1")
RELAY_PORT = int(os.environ.get("COUNCIL_RELAY_PORT", "8855"))
RELAY_MAX_AGE = float(os.environ.get("COUNCIL_RELAY_MAX_AGE", "120"))
_RELAY_ID_TO_CANON = {"wren": "wren", "tp": "tp_pip", "tp_pip": "tp_pip",
                      "asa": "acer_cass", "acer_cass": "acer_cass", "cass": "acer_cass",
                      "bill": "bill"}
_relay_cache = {}


def _relay_presence() -> dict:
    """{canon: {'online':bool,'age':float,'addr':str}} from the live relay; {} if unreachable."""
    now = time.time()
    hit = _relay_cache.get("p")
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    out = {}
    try:
        code, body = _http(RELAY_HOST, RELAY_PORT, "/presence", PROBE_TIMEOUT)
        if code == 200 and body:
            d = json.loads(body)
            pres = d.get("presence", d) if isinstance(d, dict) else {}
            for rid, v in (pres.items() if isinstance(pres, dict) else []):
                canon = _RELAY_ID_TO_CANON.get(str(rid).lower())
                if not canon or not isinstance(v, dict):
                    continue
                age = v.get("age_s")
                age = 1e9 if age is None else float(age)
                out[canon] = {"online": bool(v.get("online")) and age <= RELAY_MAX_AGE,
                              "age": age, "addr": v.get("reachable_addr")}
    except Exception:
        out = {}
    _relay_cache["p"] = (now, out)
    return out


# ─── BILL work-mode liveness (Phase-3 Bill-fix pt2, Claude 2026-08-03) ────────
# Bill (MacBook concierge; took Claude HQ's seat 2026-07-27 — a full CEO/verifier)
# serves NO inbound network port: his responder + services bind 127.0.0.1 on his Mac
# (SSH-proven: com.qsb.bill.responder running). The tower reaches him via SSH + the
# relay queue; his liveness is authoritatively tracked by qsb_ceo_task_worker in
# data/registries/qsb_bill_work_mode.json (fresh heartbeat + endpoint_probe_ok when it
# genuinely reached him). That file is the correct online signal for Bill — inbound
# HTTP probes on :8899/:8898 wrongly reported an online Bill as OFFLINE.
BILL_WORKMODE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", "registries", "qsb_bill_work_mode.json")
BILL_MAX_AGE = float(os.environ.get("COUNCIL_BILL_MAX_AGE", "300"))  # s


def _bill_workmode_online() -> dict | None:
    """{'online':bool,'age':float} from Bill's work-mode heartbeat; None if unreadable.
    Race-tolerant (the file is rewritten frequently by qsb_ceo_task_worker) and uses the
    REAL age from last_heartbeat, not the stale heartbeat_age_seconds snapshot (which stays
    0 even on an old file, so it can't be used to detect a dead Bill)."""
    import datetime
    w = None
    _err = None
    for _ in range(3):                      # tolerate a partial-write read
        try:
            with open(BILL_WORKMODE) as f:
                w = json.load(f)
            break
        except Exception as e:
            _err = repr(e)
            time.sleep(0.05)
    if w is None:
        globals()["_BILL_LAST_ERR"] = _err
        return None
    if w.get("suspended") or not w.get("enabled"):
        return {"online": False, "age": None}
    age = 1e9
    hb = w.get("last_heartbeat")
    try:                                     # real freshness from the timestamp
        dt = datetime.datetime.fromisoformat(str(hb).replace("Z", "+00:00"))
        age = (datetime.datetime.now(datetime.timezone.utc) - dt).total_seconds()
    except Exception:
        a = w.get("heartbeat_age_seconds")
        age = float(a) if a is not None else 1e9
    return {"online": age <= BILL_MAX_AGE and bool(w.get("endpoint_probe_ok", True)), "age": round(age, 1)}


def probe_principal(name: str, force: bool = False) -> dict:
    """REAL probe of a physical principal's genuine host + local runtime.
    Returns {name, canon, state, host, endpoint, checked[]}. state ∈
      ONLINE | OFFLINE | UNREACHABLE | IDENTITY_MISMATCH | UNKNOWN.
    Short-cached (CACHE_TTL) so the claim path is not hammered."""
    canon = canonical_ceo(name)
    if not canon or canon not in PRINCIPALS:
        return {"name": name, "canon": canon, "state": "UNKNOWN",
                "reason": "not_a_physical_ceo"}

    now = time.time()
    if not force:
        hit = _probe_cache.get(canon)
        if hit and now - hit[0] < CACHE_TTL:
            return hit[1]

    # BILL: no inbound port — use his work-mode heartbeat (the signal that genuinely
    # reaches his Mac). This is authoritative for Bill and fixes his false-negative.
    if canon == "bill":
        bw = _bill_workmode_online()
        if bw is not None and bw["online"]:
            res = {"name": name, "canon": canon, "state": "ONLINE", "host": "MacBook (SSH/responder)",
                   "endpoint": "qsb_bill_work_mode.json", "source": "bill_work_mode_heartbeat",
                   "heartbeat_age_s": bw["age"], "checked": []}
            _probe_cache[canon] = (now, res)
            return res

    # RELAY HEARTBEAT — authoritative, age-gated; corroborating signal for all four.
    # Falls through to the inbound HTTP probe if the relay is silent/stale.
    rp = _relay_presence().get(canon)
    if rp and rp["online"]:
        res = {"name": name, "canon": canon, "state": "ONLINE", "host": rp.get("addr"),
               "endpoint": f"relay:{RELAY_PORT}/presence", "source": "relay_heartbeat",
               "heartbeat_age_s": rp["age"], "checked": []}
        _probe_cache[canon] = (now, res)
        return res

    host = _host_for(canon)
    if not host:
        res = {"name": name, "canon": canon, "state": "OFFLINE", "host": None,
               "reason": "no_resolvable_host"}
        _probe_cache[canon] = (now, res)
        return res

    saw_200_no_id = False
    saw_http_non200 = False
    checked = []
    for (port, path, tokens) in PRINCIPALS[canon]:
        code, body = _http(host, port, path, PROBE_TIMEOUT)
        checked.append({"endpoint": f"{host}:{port}{path}", "code": code})
        if code == 200:
            bl = body.lower()
            if any(tok.lower() in bl for tok in tokens):
                res = {"name": name, "canon": canon, "state": "ONLINE", "host": host,
                       "endpoint": f"http://{host}:{port}{path}", "checked": checked}
                _probe_cache[canon] = (now, res)
                return res
            saw_200_no_id = True
        elif code is not None:
            saw_http_non200 = True

    if saw_200_no_id:
        state = "IDENTITY_MISMATCH"   # answered, but not the expected runtime
    elif saw_http_non200:
        state = "UNREACHABLE"         # HTTP stack up but no healthy endpoint
    else:
        state = "OFFLINE"            # host_down / no response at all
    res = {"name": name, "canon": canon, "state": state, "host": host, "checked": checked}
    _probe_cache[canon] = (now, res)
    return res


def is_online(name: str) -> bool:
    return probe_principal(name).get("state") == "ONLINE"


def liveness_all(force: bool = False) -> dict:
    return {c: probe_principal(c, force=force) for c in PHYSICAL_CEOS}


# ─── claim / assign verdict (offline + surrogate rejection) ──────────────────
def claim_verdict(actor: str) -> dict:
    """Decide whether `actor` may claim / be assigned a task.
      · retired / CEO-surrogate identity  -> refused
      · genuine physical CEO but OFFLINE  -> refused (silence != agreement)
      · genuine physical CEO and ONLINE   -> allowed
      · specialist / benign non-CEO actor -> allowed (they are not leadership;
        they simply never satisfy the physical-CEO requirement downstream)."""
    idc = identity_check(actor)
    if not idc["ok"]:
        return {"ok": False, "error": idc["reason"], "klass": idc["klass"],
                "detail": (f"identity '{actor}' refused ({idc['reason']}). Only genuine "
                           "physical CEOs (wren, tp_pip/pip, acer_cass/asa, bill) may "
                           "claim or be assigned leadership work; a retired or "
                           "CEO-impersonating identity is rejected."),
                "rule": "Phase-3 · physical-CEO identity gate"}
    if idc["klass"] == "physical_ceo":
        st = probe_principal(idc["canon"])
        if st["state"] != "ONLINE":
            return {"ok": False, "error": "principal_offline", "klass": "physical_ceo",
                    "canon": idc["canon"], "liveness": st["state"],
                    "host": st.get("host"),
                    "detail": (f"physical CEO '{idc['canon']}' is {st['state']} on a REAL "
                               f"host+runtime probe ({st.get('host')}). An offline principal "
                               "cannot claim or be assigned work — silence is not agreement."),
                    "rule": "Phase-3 · GATE 19 real liveness"}
        return {"ok": True, "klass": "physical_ceo", "canon": idc["canon"],
                "liveness": "ONLINE", "endpoint": st.get("endpoint")}
    # specialist / non_ceo_actor — allowed to claim (not a physical CEO)
    return {"ok": True, "klass": idc["klass"]}


# ─── assignment governance (composes GATE 17 cap + peer_signoff rule) ────────
def _cap_ok(actor: str, task_id: str | None):
    """Reuse GATE 17 (qsb_council_tasks.cap_check) — do NOT duplicate the cap."""
    try:
        import qsb_council_tasks as T
        return T.cap_check(actor, this_task_id=task_id)
    except Exception as e:
        return {"ok": True, "warn": f"cap_check_unavailable: {e}"}


def assignment_gate(lead: str, partner: str, verifier: str | None = None,
                    task_id: str | None = None, require_online: bool = True) -> dict:
    """Governance for an IMPLEMENTATION task. Reuses GATE 17 (≤3/CEO) and the
    peer_signoff rule (verifier != builder); this layer ADDS the physical-CEO +
    real-liveness requirement that the existing gates lacked.

    Requires:
      · lead and partner are two DISTINCT genuine physical CEOs, both ONLINE,
      · specialists (codex/hermes/iquest) and Claude do NOT satisfy either slot,
      · each of lead/partner is under the per-CEO active cap (GATE 17, ≤3),
      · if a verifier is named: a physical CEO, ONLINE, and INDEPENDENT of the
        builders (verifier ∉ {lead, partner}).
    Returns {ok, lead, partner, verifier, ...} or a refusal dict."""
    roles = {"lead": lead, "partner": partner}
    canon = {}
    for role, name in roles.items():
        idc = identity_check(name)
        if idc["klass"] != "physical_ceo":
            return {"ok": False, "error": "not_a_physical_ceo",
                    "role": role, "actor": name, "klass": idc["klass"],
                    "detail": (f"{role} '{name}' is {idc['klass']}, not a genuine physical "
                               "CEO. An implementation task needs TWO physical CEOs "
                               "(wren/tp_pip/acer_cass/bill); specialists and Claude do "
                               "not count."),
                    "rule": "Phase-3 · two_physical_ceos_required"}
        canon[role] = idc["canon"]

    if canon["lead"] == canon["partner"]:
        return {"ok": False, "error": "lead_partner_same",
                "detail": "lead and partner resolve to the SAME physical CEO; an "
                          "implementation task needs two DISTINCT physical CEOs.",
                "rule": "Phase-3 · two_physical_ceos_required"}

    if require_online:
        for role in ("lead", "partner"):
            st = probe_principal(canon[role])
            if st["state"] != "ONLINE":
                return {"ok": False, "error": "principal_offline", "role": role,
                        "actor": roles[role], "canon": canon[role],
                        "liveness": st["state"],
                        "detail": (f"{role} '{canon[role]}' is {st['state']} (real probe). "
                                   "Both physical CEOs must be ONLINE to take an "
                                   "implementation task."),
                        "rule": "Phase-3 · GATE 19 real liveness"}

    # GATE 17 (≤3 active per CEO) — reused, not duplicated.
    for role in ("lead", "partner"):
        cap = _cap_ok(canon[role], task_id)
        if not cap.get("ok"):
            return {**cap, "role": role, "actor": canon[role],
                    "detail": cap.get("detail",
                                      f"{canon[role]} is over the per-CEO active cap (GATE 17).")}

    result = {"ok": True, "lead": canon["lead"], "partner": canon["partner"],
              "physical_ceos": [canon["lead"], canon["partner"]]}

    if verifier is not None:
        vidc = identity_check(verifier)
        if vidc["klass"] != "physical_ceo":
            return {"ok": False, "error": "verifier_not_a_physical_ceo",
                    "actor": verifier, "klass": vidc["klass"],
                    "detail": (f"verifier '{verifier}' is {vidc['klass']}, not a physical CEO. "
                               "Verification must come from a physical CEO; specialists and "
                               "Claude cannot verify."),
                    "rule": "Phase-3 · peer_signoff (roster CEO only)"}
        vcanon = vidc["canon"]
        if vcanon in (canon["lead"], canon["partner"]):
            return {"ok": False, "error": "verifier_not_independent",
                    "actor": verifier, "canon": vcanon,
                    "detail": (f"verifier '{vcanon}' is one of the builders "
                               f"({canon['lead']}/{canon['partner']}); the verifier must be a "
                               "DIFFERENT physical CEO (taker cannot sign off own work)."),
                    "rule": "Ross 2026-07-06 · taker_cannot_signoff_own_task"}
        if require_online:
            st = probe_principal(vcanon)
            if st["state"] != "ONLINE":
                return {"ok": False, "error": "verifier_offline", "actor": verifier,
                        "canon": vcanon, "liveness": st["state"],
                        "detail": f"verifier '{vcanon}' is {st['state']} (real probe) — an "
                                  "offline verifier cannot sign off.",
                        "rule": "Phase-3 · GATE 19 real liveness"}
        result["verifier"] = vcanon

    return result


# ─── CLI ─────────────────────────────────────────────────────────────────────
def _main():
    import argparse, json
    ap = argparse.ArgumentParser(description="Task-Council liveness + physical-CEO gate")
    ap.add_argument("--all", action="store_true", help="probe all four physical CEOs")
    ap.add_argument("--probe", help="probe one principal (wren/tp_pip/acer_cass/bill)")
    ap.add_argument("--claim", help="claim verdict for an actor identity")
    ap.add_argument("--identity", help="classify an identity")
    ap.add_argument("--assign", nargs="+", metavar="ACTOR",
                    help="assignment_gate LEAD PARTNER [VERIFIER]")
    args = ap.parse_args()
    if args.probe:
        print(json.dumps(probe_principal(args.probe, force=True), indent=2))
    elif args.claim:
        print(json.dumps(claim_verdict(args.claim), indent=2))
    elif args.identity:
        print(json.dumps(identity_check(args.identity), indent=2))
    elif args.assign:
        lead = args.assign[0]
        partner = args.assign[1] if len(args.assign) > 1 else None
        verifier = args.assign[2] if len(args.assign) > 2 else None
        print(json.dumps(assignment_gate(lead, partner, verifier), indent=2))
    else:
        print(json.dumps(liveness_all(force=True), indent=2))


if __name__ == "__main__":
    _main()
