#!/usr/bin/env python3
"""
QSB Physical-Worker Registry — MASTER PHASE 2 (2026-07-11, Ross+ChatGPT approved
action_id=PHASE2-DYNAMIC-NETWORK-RESILIENCE-001).

Dynamic registration so TP-Pip / Acer-Cass remain discoverable after DHCP moves
WITHOUT any hardcoded IP being treated as permanent truth. This module is the HQ
side; it is imported by tools/qsb_boardroom_hub.py which exposes the HTTP routes.

TRUTH RULES enforced here:
  - source IP is taken from the actual TCP connection, never from client JSON.
  - only known worker IDs (tp_pip / acer_cass) with matching hostnames register.
  - loopback / non-private-LAN sources are rejected (a physical worker is not HQ).
  - hq_hosted=true is rejected for PHYSICAL registration (surrogates stay separate).
  - only expected local service ports are accepted.
  - a stale/expired worker is "REGISTRATION STALE — LAST ENDPOINT UNKNOWN",
    NEVER "machine off" (power is a separate, human-confirmed fact).
  - atomic writes; append-only history + a current-state snapshot.
  - stores NO secrets.
"""
import ipaddress
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REG = ROOT / "data/registries"
CURRENT = REG / "qsb_physical_workers_current.json"
HISTORY = REG / "qsb_physical_workers_history.jsonl"

# Accepted identities (id -> required hostname). Nothing else may register.
KNOWN_WORKERS = {"tp_pip": "DESKTOP-9RBVKSM", "acer_cass": "DESKTOP-1E2FB5N"}
# Expected local service ports (runtime + known dashboards). Anything else rejected.
ALLOWED_RUNTIME_PORTS = {8871, 8872}
ALLOWED_DASHBOARD_PORTS = {9110, 9111, 9000}
HEARTBEAT_TTL_S = 180  # a heartbeat is fresh for this long; then it goes STALE (not "off")

_FIELDS = ["worker_id", "name", "hostname", "source_ip", "runtime_port",
           "dashboard_port", "dashboard_scope", "physical_independent", "hq_hosted",
           "capabilities", "active_adapter", "connection_type", "timestamp",
           "expires_at", "last_success", "last_failure", "registration_source"]


def _utc():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _is_private_lan(ip):
    try:
        a = ipaddress.ip_address(ip)
        return a.is_private and not a.is_loopback and not a.is_link_local
    except Exception:
        return False


def _atomic_write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(obj, f, indent=2)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _load_current():
    if CURRENT.exists():
        try:
            return json.loads(CURRENT.read_text())
        except Exception:
            pass
    return {"ts": _utc(), "workers": {}}


def _append_history(row):
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    with open(HISTORY, "a") as f:
        f.write(json.dumps(row) + "\n")


def _validate(payload, source_ip, kind):
    """Return (ok, reason). Never trusts client-supplied IP for identity."""
    wid = str(payload.get("worker_id", "")).strip()
    if wid not in KNOWN_WORKERS:
        return False, "REGISTRATION REJECTED — UNKNOWN WORKER ID"
    host = str(payload.get("hostname", "")).strip().upper()
    if host != KNOWN_WORKERS[wid]:
        return False, f"REGISTRATION REJECTED — IDENTITY MISMATCH (expected {KNOWN_WORKERS[wid]})"
    if payload.get("hq_hosted") is True:
        return False, "REGISTRATION REJECTED — hq_hosted=true not allowed for PHYSICAL registry"
    if not _is_private_lan(source_ip):
        return False, "REGISTRATION REJECTED — SOURCE NOT ON PRIVATE LAN (loopback/public blocked)"
    try:
        rport = int(payload.get("runtime_port", 0))
    except Exception:
        rport = 0
    if rport not in ALLOWED_RUNTIME_PORTS:
        return False, "REGISTRATION REJECTED — RUNTIME PORT NOT PERMITTED"
    dport = payload.get("dashboard_port")
    if dport not in (None, "", "UNKNOWN"):
        try:
            if int(dport) not in ALLOWED_DASHBOARD_PORTS:
                return False, "REGISTRATION REJECTED — DASHBOARD PORT NOT PERMITTED"
        except Exception:
            return False, "REGISTRATION REJECTED — DASHBOARD PORT MALFORMED"
    return True, "ok"


def _record(payload, source_ip, kind):
    """Build a sanitized record from a validated payload. Drops any unknown/secret keys."""
    now = _utc()
    wid = payload["worker_id"]
    rec = {k: None for k in _FIELDS}
    rec.update({
        "worker_id": wid,
        "name": str(payload.get("name", wid))[:60],
        "hostname": KNOWN_WORKERS[wid],
        "source_ip": source_ip,                 # from the TCP connection, authoritative
        "runtime_port": int(payload.get("runtime_port", 0)),
        "dashboard_port": payload.get("dashboard_port"),
        "dashboard_scope": str(payload.get("dashboard_scope", "UNKNOWN"))[:24],
        "physical_independent": bool(payload.get("physical_independent", True)),
        "hq_hosted": False,
        "capabilities": [str(c)[:32] for c in (payload.get("capabilities") or [])][:12],
        "active_adapter": str(payload.get("active_adapter", "UNKNOWN"))[:48],
        "connection_type": str(payload.get("connection_type", "UNKNOWN"))[:16],
        "timestamp": now,
        "expires_at": _utc_plus(HEARTBEAT_TTL_S),
        "registration_source": kind,
    })
    return rec


def _utc_plus(seconds):
    return datetime.fromtimestamp(time.time() + seconds, timezone.utc).isoformat().replace("+00:00", "Z")


def register(payload, source_ip, kind="register"):
    ok, reason = _validate(payload, source_ip, kind)
    if not ok:
        _append_history({"ts": _utc(), "event": "reject", "kind": kind,
                         "worker_id": payload.get("worker_id"), "source_ip": source_ip, "reason": reason})
        return {"ok": False, "error": reason}
    rec = _record(payload, source_ip, kind)
    cur = _load_current()
    prev = cur["workers"].get(rec["worker_id"], {})
    rec["last_success"] = rec["timestamp"]
    rec["last_failure"] = prev.get("last_failure")
    cur["workers"][rec["worker_id"]] = rec
    cur["ts"] = _utc()
    _atomic_write_json(CURRENT, cur)
    _append_history({"ts": rec["timestamp"], "event": kind, "worker_id": rec["worker_id"],
                     "source_ip": source_ip, "runtime_port": rec["runtime_port"],
                     "dashboard_port": rec["dashboard_port"], "connection_type": rec["connection_type"],
                     "active_adapter": rec["active_adapter"]})
    return {"ok": True, "worker": rec}


def heartbeat(payload, source_ip):
    return register(payload, source_ip, kind="heartbeat")


def _annotate_staleness(rec):
    """Freshness only — expired => STALE, never 'off'."""
    out = dict(rec)
    try:
        exp = datetime.fromisoformat((rec.get("expires_at") or "").replace("Z", "+00:00"))
        age = time.time() - datetime.fromisoformat((rec.get("timestamp") or "").replace("Z", "+00:00")).timestamp()
        out["heartbeat_age_s"] = int(age)
        out["registration_fresh"] = time.time() < exp.timestamp()
    except Exception:
        out["heartbeat_age_s"] = None
        out["registration_fresh"] = False
    out["registration_state"] = ("FRESH" if out.get("registration_fresh")
                                 else "REGISTRATION STALE — LAST ENDPOINT UNKNOWN")
    return out


def get_all():
    cur = _load_current()
    return {"ts": _utc(), "workers": {k: _annotate_staleness(v) for k, v in cur.get("workers", {}).items()}}


def get_one(worker_id):
    cur = _load_current()
    w = cur.get("workers", {}).get(worker_id)
    return _annotate_staleness(w) if w else None


def health():
    cur = _load_current()
    workers = {k: _annotate_staleness(v) for k, v in cur.get("workers", {}).items()}
    fresh = sum(1 for w in workers.values() if w.get("registration_fresh"))
    return {"ts": _utc(), "registry": "physical_workers", "known": list(KNOWN_WORKERS),
            "registered": list(workers), "fresh_count": fresh, "heartbeat_ttl_s": HEARTBEAT_TTL_S,
            "workers": workers}
