#!/usr/bin/env python3
"""
qsb_network_healer.py — heals STALE HOME ADDRESSES in the federation.

The recurring failure this whole system hits: a worker box's DHCP lease drifts
(Acer .41->.60, Bill .96->.99) and every consumer that recorded the old raw IP
silently breaks — the work-mode pusher, the CEO room bridge, the box grinder, the
council verifier all died on a dead .41 at various points. The durable fix is to
address homes by their DRIFT-PROOF mDNS hostname (DESKTOP-1E2FB5N.local always
resolves to the current IP). This healer keeps the authoritative presence record
honest and on hostnames.

Each tick, per home: resolve its mDNS hostname -> current IP, probe its real AI
service. Then:
  - reachable + presence.reachable_addr is a raw IP (or a stale/dead one)  -> HEAL:
    rewrite presence.reachable_addr to the mDNS hostname (drift-proof).
  - genuinely unreachable (hostname doesn't resolve / service dead)         -> mark
    OFFLINE + ALERT (honest — never fake reachability).
  - already on a live hostname                                             -> ok.

SAFE: only ever READS the network (probes) and WRITES presence.json + its own log.
Never touches the boxes, the TP-Link/network config, or any AI's brain. Never moves
an identity. Modeled on qsb_ollama_wedge_healer.py / qsb_grinder_healer.py.

Run:  python3 tools/qsb_network_healer.py --dry-run   # show what it WOULD heal
      python3 tools/qsb_network_healer.py             # heal + write presence
"""
import json, socket, subprocess, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
PRESENCE = ROOT / "data" / "registries" / "leadership_comms" / "presence.json"
LOG = ROOT / "data" / "registries" / "qsb_network_healer.jsonl"

# home -> (mDNS hostname or None for localhost, service probe URL path, heartbeat-only?)
# heal-TARGET host = the drift-proof address to re-point to IF the recorded one dies.
# Wren IS the tower (stable LAN .72, reachable by others) — target the tower mDNS name,
# NOT localhost, so a heal never makes Wren unreachable from other machines.
HOMES = {
    "wren": {"host": "24.04ubuntu.local", "probe": "http://127.0.0.1:8851/status", "hb_only": False},
    "tp":   {"host": "DESKTOP-9RBVKSM.local", "probe": "http://DESKTOP-9RBVKSM.local:9120/", "hb_only": False,
             "worker_id": "tp_pip", "physical_host": "DESKTOP-9RBVKSM"},
    "asa":  {"host": "DESKTOP-1E2FB5N.local", "probe": "http://DESKTOP-1E2FB5N.local:9120/", "hb_only": False,
             "worker_id": "acer_cass", "physical_host": "DESKTOP-1E2FB5N"},
    # Bill is a Mac, outbound-relay-only (no inbound port) — judged live by fresh relay heartbeat.
    "bill": {"host": None, "probe": None, "hb_only": True},
}
HB_FRESH_SEC = 300


def _addr_live(addr):
    """Does the currently-recorded address actually answer on an AI service port?"""
    if not addr:
        return False
    for port in (9120, 8851, 8855):
        try:
            with socket.create_connection((addr, port), timeout=2):
                return True
        except Exception:
            continue
    return False


def _log(action, home, detail=""):
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "action": action, "home": home, "detail": str(detail)[:200]}
    try:
        with open(LOG, "a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass
    print(f"[net-healer] {action} {home} {detail}", flush=True)


def _resolve(host):
    if host in ("localhost", "127.0.0.1"):
        return "127.0.0.1"
    try:
        return socket.gethostbyname(host)
    except Exception:
        return None


def _http_ok(url, t=5):
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=t) as r:
            return 200 <= r.status < 500  # any real HTTP answer = service alive
    except Exception:
        return False


def _json_get(url, t=5):
    try:
        import urllib.request
        with urllib.request.urlopen(url, timeout=t) as r:
            return json.loads(r.read() or b"{}")
    except Exception:
        return {}


def _physical_principal_truth(cfg):
    """An open port is insufficient: prove the expected physical principal and local work source."""
    base = cfg["probe"].rstrip("/")
    health = _json_get(base + "/health")
    work = _json_get(base + "/api/workmode")
    local = work.get("local_work") or {}
    checks = {
        "service": health.get("service") == "physical_ceo_cockpit_v3",
        "worker_id": health.get("worker_id") == cfg.get("worker_id"),
        "health_host": health.get("host") == cfg.get("physical_host"),
        "delivery": work.get("delivery") == "box-local-principal",
        "principal_identity": local.get("principal_identity") == cfg.get("worker_id"),
        "physical_hostname": local.get("physical_hostname") == cfg.get("physical_host"),
        "remote_primary_forbidden": local.get("remote_primary_allowed") is False,
    }
    return all(checks.values()), checks


def _ip_dead(addr):
    """True if addr is a raw IP that does not answer a quick TCP probe on :9120/:8851."""
    if not addr or not addr[0].isdigit():
        return False  # a hostname, not a raw IP — leave to resolution
    for port in (9120, 8851):
        try:
            with socket.create_connection((addr, port), timeout=2):
                return False
        except Exception:
            continue
    return True


def heal(dry_run=False):
    try:
        pres = json.loads(PRESENCE.read_text())
    except Exception as e:
        _log("ERROR", "-", f"cannot read presence: {e}")
        return 1
    now = time.time()
    changed = False
    for home, cfg in HOMES.items():
        entry = pres.get(home, {}) or {}
        recorded = entry.get("reachable_addr") or entry.get("addr")
        host = cfg["host"]

        if cfg["hb_only"]:
            # judged by heartbeat freshness (Bill's Mac is outbound-relay-only, no inbound port)
            epoch = entry.get("last_heartbeat_epoch")
            age = (now - float(epoch)) if epoch else None
            if age is not None and age <= HB_FRESH_SEC:
                _log("ok", home, f"relay heartbeat fresh ({int(age)}s)")
            else:
                _log("ALERT_offline", home, f"no fresh relay heartbeat (age={age})")
            continue

        # Heal ONLY when the recorded address is genuinely DEAD — never disturb a live one
        # (e.g. Wren's live .72 must be left alone). Drift = the recorded IP dies while the
        # drift-proof mDNS hostname still reaches the box -> re-point to the hostname.
        if _addr_live(recorded):
            if cfg.get("worker_id"):
                truth, checks = _physical_principal_truth(cfg)
                if not truth:
                    _log("ALERT_identity_or_route", home, json.dumps(checks, sort_keys=True))
                    continue
            _log("ok", home, f"recorded {recorded} live and principal truth verified")
            continue
        cur_ip = _resolve(host)
        host_live = bool(cur_ip) and (cfg["probe"] is None or _http_ok(cfg["probe"]))
        if host_live and cfg.get("worker_id"):
            truth, checks = _physical_principal_truth(cfg)
            if not truth:
                _log("ALERT_identity_or_route", home, json.dumps(checks, sort_keys=True))
                host_live = False
        if host_live:
            _log("HEAL" + ("_DRYRUN" if dry_run else ""), home,
                 f"recorded={recorded} DEAD -> mDNS {host} (live @ {cur_ip})")
            if not dry_run:
                entry["reachable_addr"] = host; entry["status"] = "online"
                entry["healed_ts"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                pres[home] = entry; changed = True
        else:
            _log("ALERT_offline", home,
                 f"recorded={recorded} dead AND mDNS {host} unreachable (resolves={cur_ip}) — honest offline")
            if entry.get("status") != "offline" and not dry_run:
                entry["status"] = "offline"; pres[home] = entry; changed = True

    if changed and not dry_run:
        tmp = PRESENCE.with_suffix(".json.nh_tmp")
        tmp.write_text(json.dumps(pres, indent=2))
        tmp.replace(PRESENCE)
        _log("presence_written", "-", "healed entries persisted")
    return 0


if __name__ == "__main__":
    sys.exit(heal(dry_run="--dry-run" in sys.argv))
