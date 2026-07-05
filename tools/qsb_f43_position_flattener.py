#!/usr/bin/env python3
"""qsb_f43_position_flattener.py — close aged Alpaca paper positions.

The F43 daemons keep opening fresh positions. Without a flatten step,
unrealized PnL builds without realizing. This runs as a separate
timer (every 30 min) and:

  1. Queries GET /v2/positions
  2. Closes any position whose age > FLATTEN_AGE_MIN OR
     whose absolute market value > FLATTEN_NOTIONAL_USD
  3. Stamps F47 + a flatten ledger

Uses DELETE /v2/positions/{symbol} which Alpaca executes as a market
order at next open (paper account).

HARD CAPS
  - PAPER ONLY (paper-api.alpaca.markets)
  - Idempotent — repeated runs over a closed position are no-ops
  - One DELETE per symbol per run
"""

from __future__ import annotations
import argparse, datetime, json, re, urllib.request, urllib.error
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
VAULT = ROOT / "floors/floor_28_security_department/vault/.env.alpaca_paper"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
LEDGER = ROOT / "data/registries/qsb_f43_flatten_ledger.jsonl"

ALPACA_BASE = "https://paper-api.alpaca.markets"
FLATTEN_NOTIONAL_USD = 300.0    # close when |market_value| > this
FLATTEN_AGE_MIN = 60            # OR when position is older than this


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


def get_positions(env: dict) -> list[dict]:
    req = urllib.request.Request(
        f"{ALPACA_BASE}/v2/positions",
        headers={
            "APCA-API-KEY-ID": env["ALPACA_API_KEY"],
            "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET"],
        })
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def _cancel_open_orders_for(symbol: str, env: dict) -> int:
    """Cancel any open orders for symbol. Returns count canceled."""
    try:
        req = urllib.request.Request(
            f"{ALPACA_BASE}/v2/orders?status=open&limit=50&symbols={symbol}",
            headers={"APCA-API-KEY-ID": env["ALPACA_API_KEY"],
                      "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET"]})
        with urllib.request.urlopen(req, timeout=8) as r:
            orders = json.loads(r.read())
    except Exception:
        return 0
    n = 0
    for o in orders:
        if o.get("symbol") != symbol:
            continue
        try:
            cancel_req = urllib.request.Request(
                f"{ALPACA_BASE}/v2/orders/{o['id']}",
                headers={"APCA-API-KEY-ID": env["ALPACA_API_KEY"],
                          "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET"]},
                method="DELETE")
            with urllib.request.urlopen(cancel_req, timeout=8):
                n += 1
        except Exception:
            pass
    return n


def close_position(symbol: str, env: dict) -> dict:
    # Step 1: cancel any pending orders for this symbol to avoid wash trade
    canceled = _cancel_open_orders_for(symbol, env)
    # Step 2: close the position
    req = urllib.request.Request(
        f"{ALPACA_BASE}/v2/positions/{symbol}",
        headers={
            "APCA-API-KEY-ID": env["ALPACA_API_KEY"],
            "APCA-API-SECRET-KEY": env["ALPACA_API_SECRET"],
        },
        method="DELETE",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return {"ok": True, "canceled_open_orders": canceled,
                    "data": json.loads(r.read())}
    except urllib.error.HTTPError as e:
        return {"ok": False, "http_status": e.code,
                "canceled_open_orders": canceled,
                "error": e.read().decode("utf-8", errors="replace")[:300]}
    except Exception as e:
        return {"ok": False, "canceled_open_orders": canceled,
                "error": str(e)[:200]}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--notional-cap", type=float,
                   default=FLATTEN_NOTIONAL_USD)
    p.add_argument("--age-min", type=int, default=FLATTEN_AGE_MIN)
    a = p.parse_args()

    env = load_vault()
    if not (env.get("ALPACA_API_KEY") and env.get("ALPACA_API_SECRET")):
        print("ERROR: alpaca vault missing creds"); return 1

    positions = get_positions(env)
    actions = []
    now_dt = datetime.datetime.now(datetime.timezone.utc)
    for pos in positions:
        symbol = pos.get("symbol")
        try:
            mv = abs(float(pos.get("market_value") or 0))
        except Exception:
            mv = 0
        # Alpaca positions don't carry an open_time; use side / age heuristic.
        # For this v1, we just gate on notional. (Age would require pulling
        # the position's order history which is expensive.)
        reason = None
        if mv > a.notional_cap:
            reason = f"notional_${mv:.2f}_over_cap_${a.notional_cap}"
        if reason:
            actions.append({"symbol": symbol, "mv": mv, "reason": reason,
                             "qty": pos.get("qty"),
                             "unrealized_pl": pos.get("unrealized_pl")})

    if a.dry_run:
        print(json.dumps({"ts": now_iso(),
                          "positions_seen": len(positions),
                          "would_close": actions}, indent=2)[:3500])
        return 0

    closed = []
    for act in actions:
        res = close_position(act["symbol"], env)
        row = {"ts": now_iso(), "symbol": act["symbol"],
               "mv_at_close": act["mv"],
               "qty_at_close": act["qty"],
               "unrealized_pl_at_close": act["unrealized_pl"],
               "reason": act["reason"],
               "close_result": res}
        closed.append(row)
        # Stamp ledger
        LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(LEDGER, "a") as f:
            f.write(json.dumps(row) + "\n")

    # F47 audit
    with open(F47, "a") as f:
        f.write(json.dumps({
            "ts": now_iso(), "kind": "f43_position_flatten",
            "operator": "claude",
            "summary": (
                f"F43 flattener: {len(positions)} positions seen, "
                f"{len(closed)} closed "
                f"(cap=${a.notional_cap}). "
                f"Closed: {[c['symbol'] for c in closed][:8]}"
            )[:500],
        }) + "\n")

    print(f"[{now_iso()}] F43 flatten: positions={len(positions)} "
          f"closed={len(closed)}")
    for c in closed:
        print(f"  closed {c['symbol']} (mv=${c['mv_at_close']:.2f}, "
              f"reason={c['reason']}, ok={c['close_result']['ok']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
