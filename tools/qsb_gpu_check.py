#!/usr/bin/env python3
"""qsb_gpu_check.py — agent-facing GPU lease / permission check.

Any agent (Forge, Sage-narrator, Hermes, iQuest) calls this BEFORE loading
a model bigger than 3 GB VRAM. Wren doesn't need to check — she has priority
per the Council policy at data/registries/qsb_gpu_policy.json.

Usage:
  # Ask permission to load a 5 GB model as Forge
  python3 tools/qsb_gpu_check.py --agent forge --size-gib 5
  → prints JSON verdict; exit 0 = OK, 1 = DENY

  # Open a 60s lease for yourself
  python3 tools/qsb_gpu_check.py --agent forge --size-gib 5 --acquire --ttl 60
  → prints lease_id if acquired

  # Release your lease when done
  python3 tools/qsb_gpu_check.py --release <lease_id>

  # List active leases
  python3 tools/qsb_gpu_check.py --list

Wren-priority is honored: if Wren has been active in the last 30s, other
agents get DENY unless the warden's grace period has elapsed.

Real-money gates unchanged.
"""
from __future__ import annotations
import argparse, json, os, sys, time, uuid
import urllib.request, urllib.error
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
POLICY_FILE = ROOT / "data/registries/qsb_gpu_policy.json"
LEASES_FILE = ROOT / "data/registries/qsb_gpu_leases.jsonl"
WARDEN_URL = "http://127.0.0.1:8853"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def load_policy() -> dict:
    try:
        return json.loads(POLICY_FILE.read_text())
    except Exception:
        # sensible fallback if policy missing
        return {
            "hard_limits": {"max_model_size_gib": 9, "auto_evict_above_gib": 10},
            "priority": ["wren", "hermes", "forge", "sage", "iquest", "claude", "others"],
            "leases": {"default_ttl_s": 300, "wren_grace_after_session_s": 30,
                        "yield_to_wren_if_active_within_s": 30},
        }


def check_via_warden(agent: str, size_gib: float) -> dict | None:
    """Ask the Warden's HTTP endpoint. If it's not up, fall back to local file check."""
    try:
        r = urllib.request.urlopen(
            f"{WARDEN_URL}/gpu/check?agent={agent}&size_gib={size_gib}", timeout=3)
        return json.loads(r.read().decode())
    except Exception:
        return None


def check_locally(agent: str, size_gib: float, policy: dict) -> dict:
    """Same allowance logic as warden — used as fallback when warden is down."""
    hard_max = policy["hard_limits"]["max_model_size_gib"]
    if size_gib > hard_max:
        return {"ok": False, "reason": f"model {size_gib}GiB > hard cap {hard_max}GiB"}
    priority = policy["priority"]
    my_rank = priority.index(agent) if agent in priority else priority.index("others")
    active = list_leases_active()
    for lease in active:
        holder = lease.get("agent", "?")
        holder_rank = priority.index(holder) if holder in priority else priority.index("others")
        if holder_rank < my_rank:
            return {"ok": False, "reason": f"lease held by {holder} (higher priority)",
                    "lease_id": lease.get("lease_id")}
    if agent != "wren":
        yield_s = policy["leases"]["yield_to_wren_if_active_within_s"]
        if wren_recently_active(yield_s):
            return {"ok": False, "reason": f"wren was active in the last {yield_s}s — yield"}
    return {"ok": True, "reason": "no blocking lease + no wren activity"}


def wren_recently_active(within_s: int) -> bool:
    sess = ROOT / "data/registries/qsb_wren_local_agent_sessions.jsonl"
    if not sess.exists(): return False
    try:
        with sess.open("rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 100_000))
            chunk = f.read().decode("utf-8", errors="ignore")
        lines = [l for l in chunk.splitlines() if l.strip()]
        if not lines: return False
        last = json.loads(lines[-1])
        ts_end = last.get("ts_end", "")
        if not ts_end: return False
        age = time.time() - datetime.fromisoformat(ts_end.replace("Z", "+00:00")).timestamp()
        return age < within_s
    except Exception:
        return False


def list_leases_active() -> list:
    if not LEASES_FILE.exists(): return []
    now = time.time()
    latest = {}
    try:
        for line in LEASES_FILE.read_text(errors="ignore").splitlines():
            if not line.strip(): continue
            try: d = json.loads(line)
            except Exception: continue
            lid = d.get("lease_id")
            if lid: latest[lid] = d
    except Exception:
        return []
    return [d for d in latest.values()
            if d.get("action") != "release" and d.get("expires_ts", 0) > now]


def acquire_lease(agent: str, size_gib: float, ttl_s: int, model: str = "") -> dict:
    lid = f"L-{int(time.time())}-{uuid.uuid4().hex[:6]}"
    row = {
        "ts": utc_iso(),
        "lease_id": lid,
        "action": "acquire",
        "agent": agent,
        "size_gib": size_gib,
        "model": model,
        "ttl_s": ttl_s,
        "expires_ts": time.time() + ttl_s,
    }
    LEASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LEASES_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def release_lease(lease_id: str) -> dict:
    row = {"ts": utc_iso(), "lease_id": lease_id, "action": "release"}
    LEASES_FILE.parent.mkdir(parents=True, exist_ok=True)
    with LEASES_FILE.open("a") as f:
        f.write(json.dumps(row) + "\n")
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", help="requesting agent (wren|hermes|forge|sage|iquest|claude|others)")
    ap.add_argument("--size-gib", type=float, default=1.0)
    ap.add_argument("--model", default="")
    ap.add_argument("--acquire", action="store_true", help="acquire a lease after passing check")
    ap.add_argument("--ttl", type=int, default=None, help="lease TTL in seconds")
    ap.add_argument("--release", metavar="LEASE_ID", help="release a specific lease")
    ap.add_argument("--list", action="store_true", help="list active leases")
    a = ap.parse_args()

    policy = load_policy()

    if a.list:
        active = list_leases_active()
        print(json.dumps(active, indent=2, default=str))
        return

    if a.release:
        row = release_lease(a.release)
        print(json.dumps(row, indent=2, default=str))
        return

    if not a.agent:
        ap.print_help(); sys.exit(2)

    verdict = check_via_warden(a.agent, a.size_gib) or check_locally(a.agent, a.size_gib, policy)
    print(json.dumps(verdict, indent=2, default=str))

    if not verdict.get("ok"):
        sys.exit(1)

    if a.acquire:
        ttl = a.ttl or policy["leases"]["default_ttl_s"]
        lease = acquire_lease(a.agent, a.size_gib, ttl, a.model)
        print("---")
        print(json.dumps({"acquired": lease}, indent=2, default=str))


if __name__ == "__main__":
    main()
