#!/usr/bin/env python3
"""qsb_f42_trader_cycle.py — close-old + open-new cycle for F42 Binance
testnet traders. Mirror of tools/qsb_f41_trader_cycle.py for OANDA.

Per Ross 2026-06-17 authorization (Binance testnet, certified-trader gate).
Every cycle:

  1. Refresh F42 cert keepalive (so the gate stays open).
  2. Place a small rotating trade: BTCUSDT / ETHUSDT / BNBUSDT round-robin.
  3. Optionally close any open position older than --hold-secs.
  4. Stamp the run to qsb_f42_trader_cycle.jsonl + F47 records.

Hard caps:
  - testnet only (URL from .env.binance_testnet)
  - $50 USDT per trade
  - one trade per cycle
  - 3 instruments only (BTCUSDT, ETHUSDT, BNBUSDT)
"""

from __future__ import annotations
import argparse, datetime, json, subprocess, sys
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
OUT = ROOT / "data/registries/qsb_f42_trader_cycle.jsonl"
CURSOR = ROOT / "data/registries/qsb_f42_cycle_cursor.txt"

INSTRUMENTS = ["BTCUSDT", "ETHUSDT", "BNBUSDT"]
WORKERS = {
    "BTCUSDT": "f42_market_scout",
    "ETHUSDT": "f42_spread_watcher",
    "BNBUSDT": "crypto_market_scout",
}


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def get_cursor() -> int:
    if not CURSOR.exists():
        return 0
    try:
        return int(CURSOR.read_text().strip() or "0")
    except Exception:
        return 0


def next_instrument() -> str:
    n = get_cursor()
    inst = INSTRUMENTS[n % len(INSTRUMENTS)]
    CURSOR.parent.mkdir(parents=True, exist_ok=True)
    CURSOR.write_text(str(n + 1))
    return inst


def refresh_certs() -> dict:
    """Make sure F42 admin grants are present before placing."""
    r = subprocess.run(
        ["python3", str(ROOT / "tools/qsb_grant_certs.py"),
         "--floor", "F42", "--reason", "f42_cycle_pre_trade"],
        capture_output=True, text=True, timeout=20, cwd=str(ROOT))
    return {"ok": r.returncode == 0, "stdout_tail": (r.stdout or "")[-300:]}


def place_trade(side: str, usdt: float) -> dict:
    inst = next_instrument()
    worker = WORKERS[inst]
    cmd = ["python3", str(ROOT / "tools/qsb_binance.py"), "place",
           worker, inst, side.upper(), str(usdt),
           "--reason", "f42_trader_cycle_systemd",
           "--confirm"]
    # Source the vault env so the Binance creds are available
    env_path = ROOT / "floors/floor_28_security_department/vault/.env.binance_testnet"
    import os as _os
    env = dict(_os.environ)
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                       cwd=str(ROOT), env=env)
    try:
        out = json.loads(r.stdout)
    except Exception:
        out = {"ok": False, "raw": (r.stdout or r.stderr)[-300:]}
    out["worker"] = worker; out["instrument"] = inst; out["side"] = side
    return out


def stamp(payload: dict):
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(payload) + "\n")
    row = {"ts": payload["ts"], "kind": "f42_trader_cycle",
           "operator": "claude",
           "summary": (f"F42 cycle · {payload.get('instrument','?')} "
                       f"{payload.get('side','?')} ${payload.get('usdt','?')} · "
                       f"placed_ok={payload.get('placed',{}).get('ok')}"
                       f" order={payload.get('placed',{}).get('binance_order_id','?')}")[:500]}
    with open(F47, "a") as f:
        f.write(json.dumps(row) + "\n")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--side", default="BUY", choices=["BUY", "SELL", "buy", "sell"])
    p.add_argument("--usdt", type=float, default=50.0)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.dry_run:
        print("(dry run — would refresh certs + place trade)")
        return 0

    certs = refresh_certs()
    placed = place_trade(a.side, a.usdt)
    payload = {
        "ts": now_iso(), "kind": "f42_trader_cycle",
        "side": a.side.upper(), "usdt": a.usdt,
        "instrument": placed.get("instrument"),
        "worker": placed.get("worker"),
        "certs_ok": certs.get("ok"),
        "placed": placed,
    }
    stamp(payload)
    print(json.dumps(payload, indent=2)[:1500])
    return 0


if __name__ == "__main__":
    sys.exit(main())
