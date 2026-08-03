#!/usr/bin/env python3
"""Canonical FOUR-AI comms identity registry — Phase 1 of the Four-AI Communication Fabric.

This is a READ-THROUGH consolidation of the EXISTING sources, NOT a parallel store:
  · canonical identity + host ownership + surrogate/alias rules  -> qsb_council_liveness
  · dynamic current location + fresh heartbeat + online state    -> relay :8855 /presence
  · endpoint resolution (mDNS, drift-proof)                      -> qsb_federation
Only the four canonical physical principals are registrable. Claude, Codex, Hermes, iQuest,
Task-Council workers and any surrogate/wrong-host identity are REJECTED as principal peers.
An IP change updates a principal's LOCATION, never creates a new identity.

CLI:  python3 tools/qsb_comms_identity.py registry
      python3 tools/qsb_comms_identity.py resolve <name>
      python3 tools/qsb_comms_identity.py check <name> [host]
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import qsb_council_liveness as LIVE  # noqa: E402  canonical identity + surrogate rejection + probe

PROTOCOL_VERSION = "four_ai_comms/1"
RELAY_HOST = os.environ.get("COUNCIL_RELAY_HOST", "127.0.0.1")
RELAY_PORT = int(os.environ.get("COUNCIL_RELAY_PORT", "8855"))

# canonical physical ownership (a principal is valid ONLY from this host + its local mind)
CANONICAL_HOST = {
    "wren":       {"host": "MSI Linux",        "hostname": "24.04ubuntu",           "role": "SkyscraperHQ Governor"},
    "bill":       {"host": "MacBook",          "hostname": "MacBookPro.net",         "role": "Executive Concierge"},
    "tp_pip":     {"host": "ThinkPad",         "hostname": "DESKTOP-9RBVKSM.local",  "role": "Physical CEO / peer"},
    "acer_cass":  {"host": "Acer",             "hostname": "DESKTOP-1E2FB5N.local",  "role": "Physical CEO / peer"},
}
# comms endpoints (the working ones proven in Phase 0; Asa on :9000 NOT the dead :9120)
COMMS_ENDPOINT = {
    "wren":      {"comm_port": 8851, "chat": "http://127.0.0.1:8851/api/wren_chat",           "dash": "http://127.0.0.1:8851/"},
    "bill":      {"comm_port": None, "chat": "relay-queue+responder (com.qsb.bill.responder)", "dash": None},
    "tp_pip":    {"comm_port": 9120, "chat": "http://DESKTOP-9RBVKSM.local:9120/",              "dash": "http://DESKTOP-9RBVKSM.local:9120/"},
    "acer_cass": {"comm_port": 9000, "chat": "http://DESKTOP-1E2FB5N.local:9000/",              "dash": "http://DESKTOP-1E2FB5N.local:9000/"},
}


def _relay_presence() -> dict:
    """{canon: {addr, age_s, online}} from the live relay; {} if unreachable."""
    out = {}
    try:
        req = urllib.request.Request(f"http://{RELAY_HOST}:{RELAY_PORT}/presence")
        with urllib.request.urlopen(req, timeout=3) as r:
            d = json.loads(r.read().decode())
        pres = d.get("presence", d) if isinstance(d, dict) else {}
        alias = {"wren": "wren", "tp": "tp_pip", "asa": "acer_cass", "bill": "bill"}
        for rid, v in (pres.items() if isinstance(pres, dict) else []):
            canon = alias.get(str(rid).lower())
            if canon and isinstance(v, dict):
                out[canon] = {"addr": v.get("reachable_addr"), "age_s": v.get("age_s"),
                              "online": bool(v.get("online"))}
    except Exception:
        pass
    return out


def is_principal(name: str) -> bool:
    """True only for the four canonical physical principals (via the shared identity model)."""
    return LIVE.canonical_ceo(name) in CANONICAL_HOST


def check(name: str, claimed_host: str | None = None) -> dict:
    """Registration/identity verdict. Rejects non-principals, surrogates, wrong-host claims."""
    idc = LIVE.identity_check(name)
    canon = idc.get("canon")
    if not idc.get("ok") or canon not in CANONICAL_HOST:
        return {"ok": False, "reason": idc.get("reason", "not_a_canonical_principal"),
                "klass": idc.get("klass"), "canon": canon}
    if claimed_host:
        want = CANONICAL_HOST[canon]["hostname"].lower()
        got = str(claimed_host).lower()
        if want not in got and got not in want and got != CANONICAL_HOST[canon]["host"].lower():
            return {"ok": False, "reason": "wrong_physical_host",
                    "detail": f"{canon} is canonically on {CANONICAL_HOST[canon]['hostname']}, not {claimed_host}",
                    "canon": canon}
    return {"ok": True, "canon": canon, "klass": "physical_ceo"}


def resolve(name: str) -> dict | None:
    """Full canonical record for one principal (identity + live location + endpoints + state)."""
    canon = LIVE.canonical_ceo(name)
    if canon not in CANONICAL_HOST:
        return None
    pres = _relay_presence().get(canon, {})
    probe = LIVE.probe_principal(canon)
    return {
        "identity": canon,
        "role": CANONICAL_HOST[canon]["role"],
        "physical_host": CANONICAL_HOST[canon]["host"],
        "hostname": CANONICAL_HOST[canon]["hostname"],
        "current_ip": pres.get("addr"),
        "comm_port": COMMS_ENDPOINT[canon]["comm_port"],
        "mind_endpoint": COMMS_ENDPOINT[canon]["chat"],
        "dashboard_endpoint": COMMS_ENDPOINT[canon]["dash"],
        "last_heartbeat_age_s": pres.get("age_s"),
        "online": probe.get("state") == "ONLINE",
        "state": probe.get("state"),
        "liveness_source": probe.get("source", "http_probe"),
        "local_model_required_on": CANONICAL_HOST[canon]["host"],
        "protocol_version": PROTOCOL_VERSION,
    }


def registry() -> dict:
    """The whole authoritative registry — exactly the four canonical principals."""
    return {"protocol_version": PROTOCOL_VERSION, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "principals": {c: resolve(c) for c in CANONICAL_HOST}}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "registry"
    if cmd == "registry":
        print(json.dumps(registry(), indent=2))
    elif cmd == "resolve" and len(sys.argv) > 2:
        print(json.dumps(resolve(sys.argv[2]), indent=2))
    elif cmd == "check" and len(sys.argv) > 2:
        print(json.dumps(check(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None), indent=2))
    else:
        print(__doc__)
