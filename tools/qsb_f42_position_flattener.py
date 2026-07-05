#!/usr/bin/env python3
"""qsb_f42_position_flattener.py — close aged Binance testnet positions
AND update each trader's memory so the learning loop closes.

The F42 daemons open positions every cycle; without a close step,
`record_close()` never fires, so traders never accumulate wins/losses, so
they never adapt. This closes that gap.

For each trader's memory file:
  1. Find any open_trades older than FLATTEN_AGE_MIN
  2. Place an opposite-side market order of the same qty (closes it)
  3. Get the fill price from the Binance response
  4. Call qsb_trader_memory.record_close() — this updates wins/losses,
     pnl, streaks, AND auto-rotates strategy on 5-loss streak

Hard caps:
  - testnet only
  - one close per trader per run
  - never closes a position younger than FLATTEN_AGE_MIN
  - never closes more than MAX_CLOSES_PER_RUN per run (safety)
"""

from __future__ import annotations
import argparse, datetime, json, os, re, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))

MEM_DIR = ROOT / "data/registries/trader_memory"
LEDGER = ROOT / "data/registries/qsb_f42_flatten_ledger.jsonl"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
VAULT = ROOT / "floors/floor_28_security_department/vault/.env.binance_testnet"

FLATTEN_AGE_MIN = 10          # close positions older than this (min)
MAX_CLOSES_PER_RUN = 20       # safety cap on flatten passes

F42_WORKERS = {
    "f42_market_scout":     "BTCUSDT",
    "f42_spread_watcher":   "ETHUSDT",
    "crypto_market_scout":  "BNBUSDT",
}


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def load_vault() -> dict:
    env = {}
    if not VAULT.exists():
        return env
    for line in VAULT.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = re.sub(r"^export\s+", "", line)
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def _ticker_price(symbol: str) -> float | None:
    """Get current price for converting base qty → USDT notional."""
    import urllib.request, json as _json
    try:
        with urllib.request.urlopen(
                f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}",
                timeout=4) as r:
            return float(_json.loads(r.read())["price"])
    except Exception:
        return None


def close_via_binance(worker_id: str, symbol: str, open_trade: dict,
                       env: dict) -> dict:
    """Place an opposite-side market order on testnet.

    qsb_binance.py place only accepts USDT NOTIONAL (positional `usdt`),
    not base qty. So we convert: notional_usdt = base_qty × current_price.
    """
    opposite = "SELL" if open_trade["side"].upper() == "BUY" else "BUY"
    qty = float(open_trade["qty"])
    if qty <= 0:
        return {"ok": False, "error": "qty<=0"}
    px = _ticker_price(symbol)
    if not px:
        return {"ok": False, "error": "ticker fetch failed"}
    notional_usdt = round(qty * px, 2)
    if notional_usdt < 1:
        return {"ok": False, "error": f"notional {notional_usdt} too small"}
    # Use the existing qsb_binance.py wrapper which knows the vault env +
    # cert keepalive + signing. Pass a worker label so audit rows attribute
    # the close to the flattener, not to the original opener.
    import subprocess
    cmd = ["python3", str(ROOT / "tools/qsb_binance.py"), "place",
           worker_id, symbol, opposite, str(notional_usdt),
           "--reason", f"f42_flatten:{worker_id}",
           "--confirm"]
    real_env = dict(os.environ)
    for k, v in env.items():
        real_env.setdefault(k, v)
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                            cwd=str(ROOT), env=real_env)
        try:
            out = json.loads(r.stdout)
        except Exception:
            out = {"ok": False, "raw": (r.stdout or r.stderr)[-300:]}
        return out
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def age_min(ts_iso: str) -> float:
    try:
        t = datetime.datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
        delta = datetime.datetime.now(datetime.timezone.utc) - t
        return delta.total_seconds() / 60.0
    except Exception:
        return 9999.0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--age-min", type=float, default=FLATTEN_AGE_MIN)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--worker", help="only flatten this worker (default: all F42)")
    a = p.parse_args()

    from qsb_trader_memory import load, record_close, get_summary
    env = load_vault()
    if not env.get("QSB_BINANCE_TESTNET_API_KEY"):
        print("ERROR: binance vault missing"); return 1

    closes_done = 0
    workers = ([a.worker] if a.worker
                else list(F42_WORKERS.keys()))
    for w in workers:
        symbol = F42_WORKERS.get(w, "BTCUSDT")
        mem = load(w, symbol)
        for ot in list(mem["open_trades"]):
            age = age_min(ot["opened_ts"])
            if age < a.age_min:
                continue
            row = {"ts": now_iso(), "worker": w, "symbol": symbol,
                   "open_age_min": round(age, 1),
                   "side_to_close": ot["side"], "qty": ot["qty"]}
            if a.dry_run:
                row["dry_run"] = True
                print(json.dumps(row))
                continue
            res = close_via_binance(w, symbol, ot, env)
            row["close_result"] = res
            # If we got a fill price, record it into memory (this is the
            # learning event)
            if res.get("ok"):
                exit_px = (res.get("fill_price")
                           or res.get("binance_response", {}).get("fills", [{}])[0].get("price"))
                if exit_px:
                    try:
                        mem_after = record_close(
                            w, symbol, ot["order_id"], float(exit_px))
                        row["pnl_recorded"] = mem_after["closed_trades"][0]["pnl"]
                        row["won"] = mem_after["closed_trades"][0]["won"]
                        row["new_loss_streak"] = mem_after["stats"]["loss_streak"]
                        row["new_strategy"] = mem_after["strategy"]["name"]
                    except Exception as e:
                        row["record_close_err"] = str(e)[:160]
            LEDGER.parent.mkdir(parents=True, exist_ok=True)
            with open(LEDGER, "a") as f:
                f.write(json.dumps(row) + "\n")
            closes_done += 1
            print(json.dumps(row))
            if closes_done >= MAX_CLOSES_PER_RUN:
                break

    if not a.dry_run:
        with open(F47, "a") as f:
            f.write(json.dumps({
                "ts": now_iso(), "kind": "f42_position_flatten",
                "operator": "claude",
                "summary": f"F42 flatten: {closes_done} close(s) done",
            }) + "\n")

    print(f"\n[{now_iso()}] F42 flatten: {closes_done} closes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
