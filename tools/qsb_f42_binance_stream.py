#!/usr/bin/env python3
"""qsb_f42_binance_stream.py — live Binance public trade-stream (no auth).

Long-running, event-driven, NO TIMER. Per Ross 2026-06-21 mandate: traders
must analyse live market events, not poll on a clock. This client subscribes
to the public combined trade stream for BTCUSDT/ETHUSDT/BNBUSDT, writes each
tick to a rolling JSONL, and emits an ANALYSE_NOW row to the event bus.

The trade stream is PUBLIC market data — no API key is sent. Order placement
is unaffected and still gated by certified-worker + testnet URL pin in
src/tower/floors/floor_42_binance_testnet/placement.py.

URL:  wss://stream.binance.com:9443/stream?streams=btcusdt@trade/ethusdt@trade/bnbusdt@trade
Tick: {"e":"trade","E":...,"s":"BTCUSDT","t":..., "p":"64200.00","q":"0.001","T":...,"m":false}

Outputs (append-only):
  data/registries/qsb_binance_tick_stream.jsonl   — every tick
  data/registries/qsb_event_bus.jsonl             — ANALYSE_NOW signals

Reconnect: exponential backoff 1s→2s→4s→8s capped at 30s.
"""
from __future__ import annotations
import argparse, asyncio, datetime, json, signal, sys
from pathlib import Path

import websockets

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
sys.path.insert(0, str(ROOT / "tools"))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402

TICK_LOG = ROOT / "data/registries/qsb_binance_tick_stream.jsonl"
EVENT_BUS = ROOT / "data/registries/qsb_event_bus.jsonl"
DEFAULT_SYMBOLS = ["BTCUSDT", "ETHUSDT", "BNBUSDT",
                    # 2026-06-23 Binance tier-1 expansion (Hermes pick — Ross sign-off):
                    # major L1s + interop + payments + oracle infra
                    "SOLUSDT", "ADAUSDT", "XRPUSDT",
                    "DOTUSDT", "AVAXUSDT", "LINKUSDT"]


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def emit_event(kind: str, instrument: str, price: float, payload: dict) -> None:
    """Emit an ANALYSE_NOW row keyed by venue+instrument for downstream
    regime detector / analyse_then_decide to consume."""
    append_jsonl(EVENT_BUS, {
        "ts": now_iso(),
        "kind": kind,
        "venue": "binance",
        "instrument": instrument,
        "price": price,
        "payload": payload,
    })


async def stream_once(symbols: list[str], max_ticks: int | None,
                      backoff_reset_cb, bus_sub: QSBSubscriber | None = None) -> int:
    streams = "/".join(f"{s.lower()}@trade" for s in symbols)
    url = f"wss://stream.binance.com:9443/stream?streams={streams}"
    n = 0
    last_price_by_sym: dict[str, float] = {}
    connect_t = asyncio.get_event_loop().time()
    reset_armed = True
    async with websockets.connect(url, ping_interval=180, ping_timeout=60) as ws:
        print(f"[{now_iso()}] connected {url}", flush=True)
        async for raw in ws:
            if reset_armed and asyncio.get_event_loop().time() - connect_t >= 30:
                backoff_reset_cb()
                reset_armed = False
            try:
                msg = json.loads(raw)
                data = msg.get("data", {})
                if data.get("e") != "trade":
                    continue
                sym = data["s"]
                price = float(data["p"])
                qty = float(data["q"])
                tick = {
                    "ts": now_iso(),
                    "venue": "binance",
                    "instrument": sym,
                    "price": price,
                    "qty": qty,
                    "trade_id": data.get("t"),
                    "buyer_maker": data.get("m"),
                }
                append_jsonl(TICK_LOG, tick)
                # NEW (Wren-drafted, Claude-applied 2026-06-21): publish to bus
                # so belief_updater + regime_detector + traders react in real time.
                if bus_sub and bus_sub.writer:
                    try:
                        await bus_sub.publish("market.tick.binance", tick)
                    except Exception:
                        pass

                # Emit ANALYSE_NOW on level-breach (>= 0.05% move since last tick
                # we saw for this symbol). Cheap, no model needed.
                prev = last_price_by_sym.get(sym)
                if prev and abs(price - prev) / prev >= 0.0005:
                    payload = {
                        "venue": "binance", "instrument": sym, "price": price,
                        "prev_price": prev,
                        "delta_bps": round((price - prev) / prev * 10000, 1),
                    }
                    emit_event("level_breach", sym, price, payload)
                    if bus_sub and bus_sub.writer:
                        try:
                            await bus_sub.publish("market.level_breach", payload)
                        except Exception:
                            pass
                last_price_by_sym[sym] = price

                n += 1
                if n % 50 == 0:
                    print(f"[{now_iso()}] {n} ticks (last {sym}={price})", flush=True)
                if max_ticks and n >= max_ticks:
                    return n
            except Exception as e:
                print(f"[{now_iso()}] parse error: {e}", flush=True)
    return n


async def run(symbols: list[str], max_ticks: int | None) -> int:
    state = {"backoff": 1.0}
    def reset_backoff(): state["backoff"] = 1.0
    # Connect to bus as a publisher-only worker
    bus_sub = QSBSubscriber(worker_id="binance_stream")
    bus_task = asyncio.create_task(bus_sub.run(subscriptions=["_noop_"]))
    # Wait briefly for connection
    for _ in range(20):
        await asyncio.sleep(0.1)
        if bus_sub.writer:
            break
    total = 0
    while True:
        try:
            n = await stream_once(symbols, max_ticks, reset_backoff, bus_sub)
            total += n
            if max_ticks and total >= max_ticks:
                bus_task.cancel()
                return total
        except (websockets.ConnectionClosed, OSError, asyncio.TimeoutError) as e:
            print(f"[{now_iso()}] disconnect ({e!r}); reconnect in {state['backoff']:.0f}s", flush=True)
            await asyncio.sleep(state["backoff"])
            state["backoff"] = min(state["backoff"] * 2, 30.0)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    p.add_argument("--max-ticks", type=int, default=None,
                   help="exit after N ticks (smoke test). default: run forever")
    args = p.parse_args()

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, loop.stop)
    try:
        return loop.run_until_complete(run(args.symbols, args.max_ticks)) and 0 or 0
    finally:
        loop.close()


if __name__ == "__main__":
    sys.exit(main() or 0)
