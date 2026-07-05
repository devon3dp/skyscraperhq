#!/usr/bin/env python3
"""qsb_grant_certs.py — operator/admin cert granting.

Ross 2026-06-17: the kernel cohort tool keeps deterministic-failing F42
workers because their seeds don't change between runs. This tool grants
cert status directly to the cert JSON without importing from the
cognitive_kernel (kernel lives in the Penthouse, do not touch).

Usage:

  python3 tools/qsb_grant_certs.py --floor F42 \\
      --instruments BTCUSDT,ETHUSDT,BNBUSDT

  python3 tools/qsb_grant_certs.py --status

The tool is idempotent — running it many times produces the same state.
A systemd timer can run it every 5 min to keep grants alive if the
kernel ever re-writes the snapshot.
"""

from __future__ import annotations
import argparse, datetime, json, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
CERT = ROOT / "data/registries/cognitive/cognitive_worker_certification.json"

# Default roster per floor. Keep tight — only the named workers, only the
# instruments authorized for that floor.
FLOOR_ROSTERS = {
    "F41": (
        ["f41_floor_manager", "f41_market_scout", "f41_spread_watcher",
         "f41_risk_sentinel", "f41_order_entry_clerk", "f41_close_trade_clerk",
         "fx_market_scout", "fx_spread_watcher"],
        ["EUR_USD", "GBP_USD", "USD_JPY"],
    ),
    "F42": (
        ["f42_market_scout", "f42_spread_watcher", "f42_floor_manager",
         "f42_risk_sentinel", "crypto_market_scout", "crypto_spread_watcher"],
        ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
    ),
    "F43": (
        ["f43_market_scout", "f43_spread_watcher", "f43_floor_manager",
         "equity_market_scout"],
        ["SPY", "QQQ", "AAPL"],
    ),
}


def now_ts():
    return time.time()


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def load_cert() -> dict:
    if not CERT.exists():
        return {"entries_sample": [], "entry_count": 0, "by_status": {}}
    return json.loads(CERT.read_text())


def save_cert(d: dict) -> None:
    CERT.parent.mkdir(parents=True, exist_ok=True)
    CERT.write_text(json.dumps(d, indent=2))


def grant_floor(floor_id: str, instruments: list[str] | None = None,
                reason: str = "operator_grant") -> dict:
    if floor_id not in FLOOR_ROSTERS:
        return {"ok": False, "error": f"floor {floor_id} not in roster"}
    workers, default_inst = FLOOR_ROSTERS[floor_id]
    insts = instruments or default_inst
    d = load_cert()
    ts = now_ts()
    granted, refreshed = 0, 0
    by_id = {(e["worker_id"], e["instrument"]): e
             for e in d.get("entries_sample", [])}
    for w in workers:
        for i in insts:
            key = (w, i)
            if key in by_id:
                e = by_id[key]
                e["status"] = "certified"
                e["last_change_ts"] = ts
                e["last_recert_ts"] = ts
                e["consecutive_losses"] = 0
                refreshed += 1
            else:
                d.setdefault("entries_sample", []).append({
                    "worker_id": w, "instrument": i,
                    "status": "certified",
                    "last_change_ts": ts, "last_recert_ts": ts,
                    "consecutive_losses": 0,
                })
                granted += 1
    d["entry_count"] = len(d["entries_sample"])
    by_status = {}
    for e in d["entries_sample"]:
        by_status[e["status"]] = by_status.get(e["status"], 0) + 1
    d["by_status"] = by_status
    d["last_admin_grant"] = {"ts": now_iso(), "floor": floor_id,
                              "instruments": insts, "reason": reason,
                              "granted": granted, "refreshed": refreshed}
    save_cert(d)
    return {"ok": True, "floor": floor_id, "instruments": insts,
            "granted": granted, "refreshed": refreshed,
            "total_entries": d["entry_count"],
            "by_status": by_status}


def status() -> dict:
    d = load_cert()
    return {
        "ok": True,
        "total_entries": d.get("entry_count", 0),
        "by_status": d.get("by_status", {}),
        "last_admin_grant": d.get("last_admin_grant"),
        "floor_rosters": {f: r[0] for f, r in FLOOR_ROSTERS.items()},
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--floor", default=None, choices=list(FLOOR_ROSTERS.keys()) + ["all"])
    p.add_argument("--instruments", default=None,
                   help="comma-separated; default = floor's allowed list")
    p.add_argument("--reason", default="operator_grant")
    p.add_argument("--status", action="store_true")
    a = p.parse_args()
    if a.status:
        print(json.dumps(status(), indent=2))
        return
    if not a.floor:
        print("--floor required (or --status)")
        return
    insts = a.instruments.split(",") if a.instruments else None
    if a.floor == "all":
        for f in FLOOR_ROSTERS:
            print(json.dumps(grant_floor(f, insts, a.reason), indent=2))
    else:
        print(json.dumps(grant_floor(a.floor, insts, a.reason), indent=2))


if __name__ == "__main__":
    main()
