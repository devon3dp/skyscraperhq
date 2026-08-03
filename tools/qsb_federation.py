#!/usr/bin/env python3
"""
qsb_federation.py — ONE resolver for every box address in the tower federation.

Why this exists (F08 audit top recommendation, 2026-07-30):
  Box DHCP leases drift (Acer .41 -> .60, TP -> .91). ~92 live files hardcode a
  `192.168.1.x`; 26 of them dial the now-DEAD `.41`. Every drift silently broke a
  consumer (work-mode pusher, CEO room bridge, box grinder, council verifier) and
  each was fixed one-by-one. This module kills that bug CLASS: consumers ask the
  resolver for a home's address instead of hardcoding a drifting IP.

Source of truth (in priority order, per call, short-cached):
  1. data/registries/leadership_comms/presence.json — each home self-registers its
     current `reachable_addr` (already mDNS hostnames for tp/asa), refreshed ~20s.
  2. MDNS map below — the single hardcoded fact we DO trust, because an mDNS
     hostname tracks DHCP drift automatically (DESKTOP-9RBVKSM.local always points
     at TP wherever its lease lands). We PREFER the mDNS hostname over any raw IP.

Design contract:
  · Import-safe: NO network calls, NO file reads at import. Everything resolves on
    call, behind a short TTL cache.
  · Never returns a hardcoded drifting IP when an mDNS hostname is known.
  · Dependency-free (stdlib only).

Public API:
  home_addr(name)            -> "DESKTOP-9RBVKSM.local"  (host only; drift-proof)
  cockpit_url(name)          -> "http://DESKTOP-9RBVKSM.local:9120/api/chat"
  worker_url(name)           -> "http://DESKTOP-9RBVKSM.local:8871"   (physical worker)
  url_for(name, port, path)  -> generic "http://<addr>:<port><path>"
  resolve_ip(name)           -> "192.168.1.91" (best-effort mDNS->IP; None if down)
  known_homes()              -> canonical home names

CLI:
  python3 tools/qsb_federation.py                 # dump every home + resolved IP
  python3 tools/qsb_federation.py --name tp       # one home
  python3 tools/qsb_federation.py --cockpit asa   # a cockpit url
"""
from __future__ import annotations

import json
import os
import socket
import time
from pathlib import Path

# ─── locations ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
PRESENCE = Path(os.environ.get(
    "QSB_PRESENCE_JSON",
    str(ROOT / "data" / "registries" / "leadership_comms" / "presence.json"),
))

# ─── SINGLE SOURCE OF TRUTH: home -> mDNS hostname ────────────────────────────
# mDNS (.local) names are the ONLY box addresses we hardcode, because they follow
# the machine across DHCP drift. Verified 2026-07-30:
#   DESKTOP-9RBVKSM.local -> 192.168.1.91 (TP,  Lenovo ThinkPad)
#   DESKTOP-1E2FB5N.local -> 192.168.1.60 (Asa, Acer Aspire)
# Wren runs on THIS tower box (24.04ubuntu / .72); local consumers reach her at
# 127.0.0.1. Bill is on his Mac and is RELAY-managed (no mDNS) — his address comes
# only from presence.json (self-registered reachable_addr).
MDNS = {
    "tp":   "DESKTOP-9RBVKSM.local",
    "asa":  "DESKTOP-1E2FB5N.local",
    "wren": "24.04ubuntu.local",
    # bill: relay-managed, no mDNS — resolved from presence only
}

# Wren is local to the tower; prefer loopback for on-box consumers.
LOCAL_ADDR = {
    "wren": "127.0.0.1",
}

# Default ports by role (consumers may still pass their own via url_for).
COCKPIT_PORT = 9120           # physical_ceo_cockpit_v3 :9120/api/chat
WORKER_PORT = {"tp": 8871, "asa": 8872}  # physical worker endpoints

# ─── aliases: every name a consumer might use -> canonical home ───────────────
_ALIASES = {
    "tp": "tp", "tp_pip": "tp", "pip": "tp",
    "asa": "asa", "acer": "asa", "acer_cass": "asa", "cass": "asa",
    "wren": "wren",
    "bill": "bill",
}

CACHE_TTL = float(os.environ.get("QSB_FEDERATION_TTL", "15"))
_PROBE_TIMEOUT = float(os.environ.get("QSB_FEDERATION_PROBE_TIMEOUT", "1.0"))

# ─── tiny caches (populated on call, never at import) ─────────────────────────
_presence_cache: tuple[float, dict] | None = None
_ip_cache: dict[str, tuple[float, str | None]] = {}


def _canon(name: str) -> str | None:
    if not name:
        return None
    return _ALIASES.get(name.strip().lower())


def known_homes() -> list[str]:
    return ["tp", "asa", "wren", "bill"]


def _is_ip(addr: str) -> bool:
    try:
        socket.inet_aton(addr)
        return addr.count(".") == 3
    except OSError:
        return False


def _load_presence(force: bool = False) -> dict:
    """Read presence.json with a short mtime/TTL cache. Never raises."""
    global _presence_cache
    now = time.time()
    if not force and _presence_cache and now - _presence_cache[0] < CACHE_TTL:
        return _presence_cache[1]
    data: dict = {}
    try:
        data = json.loads(PRESENCE.read_text())
    except Exception:
        data = {}
    _presence_cache = (now, data)
    return data


def _presence_addr(canon: str) -> str | None:
    pres = _load_presence()
    # presence keys are the canonical short names (wren/tp/asa/bill)
    rec = pres.get(canon) or {}
    addr = rec.get("reachable_addr")
    return addr.strip() if isinstance(addr, str) and addr.strip() else None


def home_addr(name: str, prefer_local: bool = True) -> str | None:
    """Return the HOST (no scheme/port) for a home, drift-proof.

    Order:
      1. If the home is local to the tower and prefer_local -> loopback.
      2. presence.json reachable_addr IF it is already an mDNS/hostname
         (non-IP) — the home told us where it is, and it's not a drifting IP.
      3. The known mDNS hostname (drift-proof) — PREFERRED over any raw IP.
      4. presence.json reachable_addr even if it's a raw IP (last resort;
         only path for relay-managed homes like bill with no mDNS).
    Returns None if the home is unknown and nothing is registered.
    """
    canon = _canon(name)
    if canon is None:
        return None

    if prefer_local and canon in LOCAL_ADDR:
        return LOCAL_ADDR[canon]

    addr = _presence_addr(canon)
    # 2: presence already holds a hostname (mDNS) — trust it, it doesn't drift.
    if addr and not _is_ip(addr):
        return addr
    # 3: prefer the known mDNS hostname over any raw/drifting IP.
    if canon in MDNS:
        return MDNS[canon]
    # 4: last resort — a raw IP from presence (e.g. bill, relay-managed).
    if addr:
        return addr
    return None


def resolve_ip(name: str, timeout: float | None = None) -> str | None:
    """Best-effort resolve a home to its CURRENT IP via mDNS/DNS. Short-cached.
    Returns None if the host does not currently resolve (i.e. box is down/away).
    Use for display/diagnostics — consumers should dial the HOSTNAME (home_addr)
    so the OS re-resolves on every connection and drift is handled for free.
    """
    addr = home_addr(name, prefer_local=False)
    if not addr:
        return None
    if _is_ip(addr):
        return addr
    now = time.time()
    hit = _ip_cache.get(addr)
    if hit and now - hit[0] < CACHE_TTL:
        return hit[1]
    ip: str | None = None
    try:
        socket.setdefaulttimeout(timeout or _PROBE_TIMEOUT)
        ip = socket.gethostbyname(addr)
    except Exception:
        ip = None
    finally:
        socket.setdefaulttimeout(None)
    _ip_cache[addr] = (now, ip)
    return ip


def url_for(name: str, port: int, path: str = "", scheme: str = "http",
            prefer_local: bool = True) -> str | None:
    """Generic URL builder against a home's current address."""
    addr = home_addr(name, prefer_local=prefer_local)
    if not addr:
        return None
    if path and not path.startswith("/"):
        path = "/" + path
    return f"{scheme}://{addr}:{port}{path}"


def cockpit_url(name: str, path: str = "/api/chat", prefer_local: bool = False) -> str | None:
    """The :9120 physical CEO cockpit chat endpoint for tp/asa."""
    return url_for(name, COCKPIT_PORT, path, prefer_local=prefer_local)


def worker_url(name: str, path: str = "", prefer_local: bool = False) -> str | None:
    """The physical worker endpoint (:8871 TP / :8872 Asa)."""
    canon = _canon(name)
    if canon not in WORKER_PORT:
        return None
    return url_for(name, WORKER_PORT[canon], path, prefer_local=prefer_local)


def _main() -> None:
    import argparse
    ap = argparse.ArgumentParser(description="QSB federation address resolver")
    ap.add_argument("--name", help="resolve one home -> addr + current IP")
    ap.add_argument("--cockpit", help="print the :9120 cockpit url for a home")
    ap.add_argument("--worker", help="print the physical worker url for a home")
    args = ap.parse_args()

    if args.cockpit:
        print(cockpit_url(args.cockpit))
        return
    if args.worker:
        print(worker_url(args.worker))
        return
    if args.name:
        addr = home_addr(args.name)
        print(json.dumps({"name": args.name, "addr": addr,
                          "current_ip": resolve_ip(args.name)}, indent=2))
        return

    # dump everything
    rows = []
    for h in known_homes():
        rows.append({
            "home": h,
            "addr": home_addr(h),
            "addr_remote": home_addr(h, prefer_local=False),
            "current_ip": resolve_ip(h),
            "cockpit": cockpit_url(h) if h in ("tp", "asa") else None,
            "worker": worker_url(h) if h in ("tp", "asa") else None,
        })
    print(json.dumps({"presence_file": str(PRESENCE), "homes": rows}, indent=2))


if __name__ == "__main__":
    _main()
