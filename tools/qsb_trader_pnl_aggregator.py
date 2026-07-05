#!/usr/bin/env python3
"""qsb_trader_pnl_aggregator.py — closes the PnL attribution gap.

Discovered 2026-06-17 (Ross helm): cognitive_worker_certification's
`per_worker_realised_gbp` was empty `{}` even though OANDA's REST shows
£+214.26 lifetime. The aggregator builds the missing per-worker view.

For each floor:
  F41 OANDA: reads qsb_floor41_oanda_trade_lifecycle.json closed_trades
             (190 rows on disk). Each close has worker_id + pnl_amount.
             Splits paper_simulator vs oanda_practice_api so the
             classroom can score live behaviour separately.
  F42 Binance testnet: no close cycle yet — emits trade counts and
             notional sum per worker. PnL attribution TODO when a
             close-cycle daemon lands.
  F43 Alpaca paper: same as F42 — counts + notional.

Writes to data/registries/qsb_trader_pnl_summary.jsonl (one row per tick).
Latest tick is also persisted to qsb_trader_pnl_latest.json for cheap
reads by the dashboard / classroom evaluator.

Designed to run as a systemd timer every ~10 min.
"""

from __future__ import annotations
import argparse, datetime, hashlib, hmac, json, re, time
import urllib.request, urllib.error
from collections import defaultdict, deque
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F41_LIFECYCLE = ROOT / "data/registries/qsb_floor41_oanda_trade_lifecycle.json"
F41_OANDA_HISTORY = ROOT / "data/registries/qsb_oanda_history_summary.json"
F42_CYCLE = ROOT / "data/registries/qsb_f42_trader_cycle.jsonl"
F43_CYCLE = ROOT / "data/registries/qsb_f43_trader_cycle.jsonl"
ALPACA_VAULT = ROOT / "floors/floor_28_security_department/vault/.env.alpaca_paper"
BINANCE_VAULT = ROOT / "floors/floor_28_security_department/vault/.env.binance_testnet"

OUT_TAIL = ROOT / "data/registries/qsb_trader_pnl_summary.jsonl"
OUT_LATEST = ROOT / "data/registries/qsb_trader_pnl_latest.json"
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def aggregate_f41() -> dict:
    """Per-worker realised PnL on F41, split by execution_mode."""
    if not F41_LIFECYCLE.exists():
        return {"floor": "F41", "ok": False, "reason": "no lifecycle file"}
    try:
        data = json.loads(F41_LIFECYCLE.read_text())
    except Exception as e:
        return {"floor": "F41", "ok": False, "reason": str(e)[:200]}

    closes = data.get("closed_trades", [])
    by_worker = defaultdict(lambda: defaultdict(
        lambda: {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}))
    grand = defaultdict(
        lambda: {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0})

    for t in closes:
        worker = t.get("worker_id") or "unknown"
        mode = t.get("execution_mode") or "unknown"
        pnl = float(t.get("pnl_amount") or 0.0)
        b = by_worker[worker][mode]
        b["pnl"] += pnl
        b["trades"] += 1
        if pnl > 0:
            b["wins"] += 1
        elif pnl < 0:
            b["losses"] += 1
        g = grand[mode]
        g["pnl"] += pnl
        g["trades"] += 1
        if pnl > 0:
            g["wins"] += 1
        elif pnl < 0:
            g["losses"] += 1

    # Sort workers by total trades, top 20
    workers_out = []
    for w, modes in by_worker.items():
        total_trades = sum(m["trades"] for m in modes.values())
        total_pnl = sum(m["pnl"] for m in modes.values())
        workers_out.append({
            "worker_id": w, "total_trades": total_trades,
            "total_pnl": round(total_pnl, 4),
            "by_mode": {m: {**v, "pnl": round(v["pnl"], 4)}
                         for m, v in modes.items()},
        })
    workers_out.sort(key=lambda r: r["total_trades"], reverse=True)

    return {
        "floor": "F41", "ok": True,
        "closes_total": len(closes),
        "grand_by_mode": {m: {**v, "pnl": round(v["pnl"], 4)}
                          for m, v in grand.items()},
        "top_workers": workers_out[:20],
    }


def aggregate_jsonl_cycle(path: Path, floor: str,
                          worker_field: str,
                          instrument_field: str,
                          notional_field: str) -> dict:
    """F42 / F43: count trades + notional per worker. No close attribution
    yet (testnet/paper don't auto-close)."""
    if not path.exists():
        return {"floor": floor, "ok": False, "reason": "no cycle file"}
    by_worker = defaultdict(lambda: {"trades": 0, "placed_ok": 0,
                                       "notional_total": 0.0,
                                       "instruments": set()})
    for ln in path.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        if d.get("kind") not in ("f42_trader_daemon", "f43_trader_daemon"):
            continue
        w = d.get(worker_field) or "unknown"
        b = by_worker[w]
        b["trades"] += 1
        if d.get("placed", {}).get("ok"):
            b["placed_ok"] += 1
        b["notional_total"] += float(d.get(notional_field) or 0)
        if d.get(instrument_field):
            b["instruments"].add(d[instrument_field])

    workers = []
    for w, v in by_worker.items():
        workers.append({
            "worker_id": w,
            "trades": v["trades"],
            "placed_ok": v["placed_ok"],
            "placement_rate": round(v["placed_ok"] / v["trades"], 3)
                if v["trades"] else 0.0,
            "notional_total": round(v["notional_total"], 2),
            "instruments": sorted(v["instruments"]),
        })
    workers.sort(key=lambda r: r["trades"], reverse=True)
    return {
        "floor": floor, "ok": True,
        "workers": workers,
        "note": "no close-cycle on this floor yet — pnl_attribution TODO",
    }


def _read_vault(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = re.sub(r"^export\s+", "", line)
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def _fifo_realized_pnl(trades: list[dict]) -> dict:
    """FIFO match buys vs sells per symbol with originator attribution.

    Each trade is {symbol, side: buy/sell, qty, price, ts (ms),
                   worker (optional)}.
    PnL attribution rule: realized PnL goes to the worker who OPENED the
    lot (the buyer for long lots, the seller for short lots). When a
    closing trade matches multiple lots, the PnL is split proportionally.

    Returns:
      {
        symbol: {
          realized_pnl, matched_qty, open_long_qty, open_short_qty,
          trades_total,
          by_worker: {worker_id: {realized_pnl, matched_qty}}
        }
      }
    """
    by_symbol = defaultdict(list)
    for t in trades:
        by_symbol[t["symbol"]].append(t)
    out = {}
    for sym, ts in by_symbol.items():
        ts_sorted = sorted(ts, key=lambda r: r.get("ts") or 0)
        # FIFO lots: each entry is (qty, price, originator_worker)
        longs = deque()
        shorts = deque()
        realized = 0.0
        matched = 0.0
        by_worker = defaultdict(lambda: {"realized_pnl": 0.0,
                                          "matched_qty": 0.0})
        for tr in ts_sorted:
            qty = float(tr["qty"])
            price = float(tr["price"])
            worker_here = tr.get("worker", "unattributed")
            if tr["side"] == "buy":
                # Close any open shorts FIFO; PnL goes to the SHORT opener
                while qty > 1e-12 and shorts:
                    s_qty, s_price, s_worker = shorts[0]
                    take = min(qty, s_qty)
                    pnl = (s_price - price) * take
                    realized += pnl
                    matched += take
                    by_worker[s_worker]["realized_pnl"] += pnl
                    by_worker[s_worker]["matched_qty"] += take
                    qty -= take
                    s_qty -= take
                    if s_qty < 1e-12:
                        shorts.popleft()
                    else:
                        shorts[0] = (s_qty, s_price, s_worker)
                if qty > 1e-12:
                    longs.append((qty, price, worker_here))
            else:  # sell
                while qty > 1e-12 and longs:
                    l_qty, l_price, l_worker = longs[0]
                    take = min(qty, l_qty)
                    pnl = (price - l_price) * take
                    realized += pnl
                    matched += take
                    by_worker[l_worker]["realized_pnl"] += pnl
                    by_worker[l_worker]["matched_qty"] += take
                    qty -= take
                    l_qty -= take
                    if l_qty < 1e-12:
                        longs.popleft()
                    else:
                        longs[0] = (l_qty, l_price, l_worker)
                if qty > 1e-12:
                    shorts.append((qty, price, worker_here))
        open_long_qty = sum(q for q, _, _ in longs)
        open_short_qty = sum(q for q, _, _ in shorts)
        # Round worker entries
        bw_out = {w: {"realized_pnl": round(v["realized_pnl"], 6),
                       "matched_qty": round(v["matched_qty"], 6)}
                  for w, v in by_worker.items()}
        out[sym] = {
            "realized_pnl": round(realized, 6),
            "matched_qty": round(matched, 6),
            "open_long_qty": round(open_long_qty, 6),
            "open_short_qty": round(open_short_qty, 6),
            "trades_total": len(ts_sorted),
            "by_worker": bw_out,
        }
    return out


def _load_order_to_worker_map(cycle_path: Path,
                               order_key: str) -> dict:
    """Walk a F42/F43 cycle jsonl and build {order_id: worker_id} map.
    For F42 use order_key='binance_order_id'; for F43 use 'order_id'."""
    mapping: dict = {}
    if not cycle_path.exists():
        return mapping
    for ln in cycle_path.read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:
            continue
        placed = d.get("placed") or {}
        oid = placed.get(order_key)
        if oid is None:
            continue
        worker = d.get("worker") or d.get("worker_id")
        if worker:
            # Keys: both string and string-of-int forms — broker may
            # return int (Binance) or uuid (Alpaca).
            mapping[str(oid)] = worker
    return mapping


def aggregate_alpaca_pnl() -> dict:
    env = _read_vault(ALPACA_VAULT)
    key = env.get("ALPACA_API_KEY")
    sec = env.get("ALPACA_API_SECRET")
    if not (key and sec):
        return {"floor": "F43", "ok": False, "reason": "vault creds missing"}
    url = ("https://paper-api.alpaca.markets/v2/orders"
           "?status=closed&limit=200&direction=desc")
    req = urllib.request.Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": sec,
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            orders = json.loads(r.read())
    except Exception as e:
        return {"floor": "F43", "ok": False,
                "reason": f"alpaca api: {str(e)[:200]}"}
    # Build order_id → worker map from F43 cycle jsonl
    order_to_worker = _load_order_to_worker_map(F43_CYCLE, "order_id")
    trades = []
    for o in orders:
        if o.get("status") != "filled":
            continue
        try:
            qty = float(o.get("filled_qty") or 0)
            price = float(o.get("filled_avg_price") or 0)
        except Exception:
            continue
        if qty <= 0 or price <= 0:
            continue
        # filled_at is ISO; convert to epoch ms for sort key
        fa = o.get("filled_at") or o.get("updated_at") or ""
        try:
            ts = int(datetime.datetime.fromisoformat(
                fa.replace("Z", "+00:00")).timestamp() * 1000)
        except Exception:
            ts = 0
        worker = order_to_worker.get(str(o.get("id")), "unattributed")
        trades.append({
            "symbol": o["symbol"], "side": o["side"],
            "qty": qty, "price": price, "ts": ts,
            "worker": worker,
        })
    pnl = _fifo_realized_pnl(trades)
    return {"floor": "F43", "ok": True,
             "filled_orders": len(trades),
             "broker_pnl_usd_by_symbol": pnl,
             "broker_pnl_usd_total": round(
                 sum(v["realized_pnl"] for v in pnl.values()), 4)}


def aggregate_binance_pnl() -> dict:
    env = _read_vault(BINANCE_VAULT)
    key = env.get("QSB_BINANCE_TESTNET_API_KEY")
    sec = env.get("QSB_BINANCE_TESTNET_API_SECRET")
    host = env.get("QSB_BINANCE_TESTNET_URL")
    if not (key and sec and host):
        return {"floor": "F42", "ok": False, "reason": "vault creds missing"}
    # Build order_id → worker map from F42 cycle jsonl
    order_to_worker = _load_order_to_worker_map(F42_CYCLE,
                                                  "binance_order_id")
    all_trades = []
    for sym in ("BTCUSDT", "ETHUSDT", "BNBUSDT"):
        ts_ms = int(time.time() * 1000)
        qs = f"symbol={sym}&timestamp={ts_ms}&recvWindow=5000"
        sig = hmac.new(sec.encode(), qs.encode(),
                       hashlib.sha256).hexdigest()
        url = f"{host}/api/v3/myTrades?{qs}&signature={sig}"
        req = urllib.request.Request(url,
                                      headers={"X-MBX-APIKEY": key})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                tr = json.loads(r.read())
        except Exception as e:
            return {"floor": "F42", "ok": False,
                    "reason": f"binance api {sym}: {str(e)[:200]}"}
        for t in tr:
            try:
                qty = float(t.get("qty") or 0)
                price = float(t.get("price") or 0)
            except Exception:
                continue
            if qty <= 0 or price <= 0:
                continue
            worker = order_to_worker.get(str(t.get("orderId")),
                                           "unattributed")
            all_trades.append({
                "symbol": sym,
                "side": "buy" if t.get("isBuyer") else "sell",
                "qty": qty, "price": price,
                "ts": int(t.get("time") or 0),
                "worker": worker,
            })
    pnl = _fifo_realized_pnl(all_trades)
    return {"floor": "F42", "ok": True,
             "filled_trades": len(all_trades),
             "broker_pnl_usdt_by_symbol": pnl,
             "broker_pnl_usdt_total": round(
                 sum(v["realized_pnl"] for v in pnl.values()), 4)}


def stamp(summary: dict) -> None:
    OUT_TAIL.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_TAIL, "a") as f:
        f.write(json.dumps(summary) + "\n")
    OUT_LATEST.write_text(json.dumps(summary, indent=2))
    # F47 audit
    f41 = summary["by_floor"]["F41"]
    grand = f41.get("grand_by_mode", {}) if f41.get("ok") else {}
    sim_pnl = grand.get("paper_simulator", {}).get("pnl", 0)
    live_pnl = grand.get("oanda_practice_api", {}).get("pnl", 0)
    line = (f"F41 closes={f41.get('closes_total','?')} · "
            f"sim_pnl={sim_pnl} GBP · live_pnl={live_pnl} GBP · "
            f"F42 workers={len(summary['by_floor']['F42'].get('workers',[]))} · "
            f"F43 workers={len(summary['by_floor']['F43'].get('workers',[]))}")
    with open(F47, "a") as f:
        f.write(json.dumps({
            "ts": summary["ts"], "kind": "trader_pnl_aggregate_tick",
            "operator": "claude", "summary": line[:500],
        }) + "\n")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true",
                   help="print to stdout, don't stamp")
    a = p.parse_args()

    f42_local = aggregate_jsonl_cycle(
        F42_CYCLE, "F42", "worker", "instrument", "usdt")
    f43_local = aggregate_jsonl_cycle(
        F43_CYCLE, "F43", "worker", "symbol", "usd")
    # Merge broker-side realized PnL (FIFO matched) on top of local counts.
    f42_broker = aggregate_binance_pnl()
    f43_broker = aggregate_alpaca_pnl()
    if f42_broker.get("ok"):
        f42_local["broker"] = f42_broker
    if f43_broker.get("ok"):
        f43_local["broker"] = f43_broker

    # Fold in OANDA's authoritative lifetime PnL snapshot (pulled by
    # qsb_oanda_history_pull.py — the broker's truth, not just our local
    # lifecycle file's subset).
    f41 = aggregate_f41()
    if F41_OANDA_HISTORY.exists():
        try:
            f41["oanda_lifetime"] = json.loads(F41_OANDA_HISTORY.read_text())
        except Exception:
            pass

    summary = {
        "ts": now_iso(),
        "kind": "trader_pnl_aggregate",
        "by_floor": {
            "F41": f41,
            "F42": f42_local,
            "F43": f43_local,
        },
    }

    if a.dry_run:
        print(json.dumps(summary, indent=2)[:5000])
    else:
        stamp(summary)
        # Compact one-line stdout for systemd log
        f41 = summary["by_floor"]["F41"]
        grand = f41.get("grand_by_mode", {}) if f41.get("ok") else {}
        print(
            f"[{summary['ts']}] PnL · F41 closes={f41.get('closes_total','?')}"
            f" sim={grand.get('paper_simulator',{}).get('pnl',0)} GBP"
            f" live={grand.get('oanda_practice_api',{}).get('pnl',0)} GBP"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
