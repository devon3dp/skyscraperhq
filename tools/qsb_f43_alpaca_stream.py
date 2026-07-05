#!/usr/bin/env python3
"""qsb_f43_alpaca_stream.py — live Alpaca data websocket (free IEX feed).

Long-running, event-driven, NO TIMER. Per Ross 2026-06-21 mandate. Alpaca's
data stream is true websocket — auth via JSON message, then subscribe to
trades/quotes for SPY/AAPL/QQQ. Free IEX feed sufficient for paper trading
intelligence.

Reads ALPACA_API_KEY + ALPACA_API_SECRET from
floors/floor_28_security_department/vault/.env.alpaca_paper. Auth payload is
sent once on connect, never logged.

URL: wss://stream.data.alpaca.markets/v2/iex
Tick: [{"T":"t","S":"AAPL","p":150.32,"s":100,"t":"...","x":"V","i":42}]

Outside US equity market hours (weekends / pre-/post-market) Alpaca still
sends a 'success' connect frame and may send 'subscription' confirmation but
no trades. That's expected; the daemon stays connected waiting for the next
open. Reconnect on disconnect: 1s→2s→4s→8s capped at 30s.
"""
from __future__ import annotations
import argparse, asyncio, datetime, json, os, re, signal, sys
from pathlib import Path

import websockets

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
import sys as _sys
_sys.path.insert(0, str(ROOT / "tools"))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402
TICK_LOG = ROOT / "data/registries/qsb_alpaca_tick_stream.jsonl"
EVENT_BUS = ROOT / "data/registries/qsb_event_bus.jsonl"

VAULT = ROOT / "floors/floor_28_security_department/vault/.env.alpaca_paper"
DEFAULT_SYMBOLS = ["SPY", "AAPL", "QQQ", "TSLA", "NVDA", "MSFT",
                    # 2026-06-22 Alpaca expansion (Wren diversification logic
                    # vs Hermes tech-heavy — Claude CEO override picked Wren):
                    # Dow ETF, financial sector ETF, gold ETF, Coinbase, small-caps
                    "DIA", "XLF", "GLD", "COIN", "IWM"]
WS_URL = "wss://stream.data.alpaca.markets/v2/iex"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


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


def emit_event(kind: str, instrument: str, price: float, payload: dict) -> None:
    append_jsonl(EVENT_BUS, {
        "ts": now_iso(),
        "kind": kind,
        "venue": "alpaca",
        "instrument": instrument,
        "price": price,
        "payload": payload,
    })


async def stream_once(key: str, secret: str, symbols: list[str],
                      max_ticks: int | None, backoff_reset_cb,
                      bus_sub: QSBSubscriber | None = None) -> int:
    n = 0
    last_price: dict[str, float] = {}
    connect_t = asyncio.get_event_loop().time()
    reset_armed = True
    async with websockets.connect(WS_URL, ping_interval=30, ping_timeout=30) as ws:
        # Connect frame
        hello = await ws.recv()
        print(f"[{now_iso()}] connected; server hello: {hello[:120]}", flush=True)
        # Auth
        await ws.send(json.dumps({"action": "auth", "key": key, "secret": secret}))
        auth_resp = await ws.recv()
        print(f"[{now_iso()}] auth resp: {auth_resp[:120]}", flush=True)
        # Subscribe to trades
        await ws.send(json.dumps({"action": "subscribe", "trades": symbols}))
        sub_resp = await ws.recv()
        print(f"[{now_iso()}] subscribe resp: {sub_resp[:200]}", flush=True)

        async for raw in ws:
            if reset_armed and asyncio.get_event_loop().time() - connect_t >= 30:
                backoff_reset_cb()
                reset_armed = False
            try:
                msgs = json.loads(raw)
                if not isinstance(msgs, list):
                    continue
                for m in msgs:
                    if m.get("T") != "t":  # 't' = trade
                        continue
                    sym = m["S"]
                    price = float(m["p"])
                    qty = int(m.get("s", 0))
                    tick = {
                        "ts": now_iso(),
                        "venue": "alpaca",
                        "instrument": sym,
                        "price": price, "qty": qty,
                        "trade_id": m.get("i"),
                        "exchange": m.get("x"),
                        "alpaca_time": m.get("t"),
                    }
                    append_jsonl(TICK_LOG, tick)
                    # Hermes-approved 2026-06-21: also publish on bus.
                    if bus_sub and bus_sub.writer:
                        try:
                            await bus_sub.publish("market.tick.alpaca", tick)
                        except Exception:
                            pass

                    prev = last_price.get(sym)
                    if prev and abs(price - prev) / prev >= 0.0010:  # 10 bps move on equities
                        breach_payload = {
                            "venue": "alpaca", "instrument": sym, "price": price,
                            "prev_price": prev,
                            "delta_bps": round((price - prev) / prev * 10000, 1),
                        }
                        emit_event("level_breach", sym, price, breach_payload)
                        if bus_sub and bus_sub.writer:
                            try:
                                await bus_sub.publish("market.level_breach", breach_payload)
                            except Exception:
                                pass
                    last_price[sym] = price

                    n += 1
                    if n % 20 == 0:
                        print(f"[{now_iso()}] {n} ticks (last {sym}={price})", flush=True)
                    if max_ticks and n >= max_ticks:
                        return n
            except Exception as e:
                print(f"[{now_iso()}] parse error: {e}", flush=True)
    return n


async def run(key: str, secret: str, symbols: list[str], max_ticks: int | None) -> int:
    state = {"backoff": 1.0}
    def reset_backoff(): state["backoff"] = 1.0
    bus_sub = QSBSubscriber(worker_id="alpaca_stream")
    bus_task = asyncio.create_task(bus_sub.run(subscriptions=["_noop_"]))
    for _ in range(20):
        await asyncio.sleep(0.1)
        if bus_sub.writer:
            break
    total = 0
    while True:
        try:
            n = await stream_once(key, secret, symbols, max_ticks, reset_backoff, bus_sub)
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
    p.add_argument("--max-ticks", type=int, default=None)
    args = p.parse_args()

    env = load_vault()
    for k, v in env.items():
        os.environ.setdefault(k, v)
    key = os.environ.get("ALPACA_API_KEY", "").strip()
    secret = os.environ.get("ALPACA_API_SECRET", "").strip()
    if not key or not secret:
        print("ERROR: ALPACA_API_KEY + ALPACA_API_SECRET required (vault or env).",
              file=sys.stderr)
        return 2

    loop = asyncio.new_event_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, loop.stop)
    try:
        loop.run_until_complete(run(key, secret, args.symbols, args.max_ticks))
    except SystemExit:
        pass
    finally:
        loop.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
