#!/usr/bin/env python3
"""qsb_f41_oanda_stream.py — live OANDA practice pricing stream.

Long-running, event-driven, NO TIMER. Per Ross 2026-06-21 mandate. OANDA's
streaming endpoint is HTTP chunked (not websocket) — newline-delimited JSON
with HEARTBEAT and PRICE rows. We forward PRICE rows to the tick log and
emit ANALYSE_NOW on level-breaches.

Reads OANDA_API_TOKEN + OANDA_ACCOUNT_ID from
floors/floor_28_security_department/vault/.env.oanda_practice (or top-level
.env.oanda_practice as legacy fallback). Token is sent as Bearer header only,
never logged.

URL: https://stream-fxpractice.oanda.com/v3/accounts/{ACCT}/pricing/stream
Instruments: EUR_USD,GBP_USD,USD_JPY

Reconnect: exponential backoff 1s→2s→4s→8s capped at 30s.
"""
from __future__ import annotations
import argparse, datetime, json, os, re, signal, sys, time
from pathlib import Path

import requests

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
import sys as _sys
_sys.path.insert(0, str(ROOT / "tools"))
from qsb_event_subscriber import QSBSubscriber  # noqa: E402
TICK_LOG = ROOT / "data/registries/qsb_oanda_tick_stream.jsonl"
EVENT_BUS = ROOT / "data/registries/qsb_event_bus.jsonl"

VAULT_PATHS = [
    ROOT / "floors/floor_28_security_department/vault/.env.oanda_practice",
    ROOT / ".env.oanda_practice",
]
DEFAULT_INSTRUMENTS = ["EUR_USD", "GBP_USD", "USD_JPY",
                        "AUD_USD", "USD_CHF", "EUR_GBP",
                        # 2026-06-22 OANDA tier-1 expansion (team consensus):
                        # gold, silver, WTI oil, Brent oil
                        "XAU_USD", "XAG_USD", "WTICO_USD", "BCO_USD",
                        # 2026-06-22 OANDA tier-2 expansion (Wren+Hermes 4/4 unanimous):
                        # SP500, Nasdaq 100, Dow, natural gas
                        "SPX500_USD", "NAS100_USD", "US30_USD", "NATGAS_USD",
                        # 2026-06-23 OANDA tier-3 expansion (Wren pick — Ross sign-off):
                        # DAX, Nikkei, US 10Y, UK 10Y, Copper, Wheat
                        "DE30_EUR", "JP225_USD", "USB10Y_USD",
                        "UK10YB_GBP", "XCU_USD", "WHEAT_USD"]
STREAM_HOST = "https://stream-fxpractice.oanda.com"


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, separators=(",", ":")) + "\n")


def load_vault() -> dict:
    """Read .env.oanda_practice with export VAR=val syntax. Same pattern as
    F43 daemon load_vault."""
    env = {}
    for p in VAULT_PATHS:
        if not p.exists():
            continue
        for line in p.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            line = re.sub(r"^export\s+", "", line)
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
        break
    return env


def emit_event(kind: str, instrument: str, mid: float, payload: dict) -> None:
    append_jsonl(EVENT_BUS, {
        "ts": now_iso(),
        "kind": kind,
        "venue": "oanda",
        "instrument": instrument,
        "price": mid,
        "payload": payload,
    })


def stream_once(token: str, account_id: str, instruments: list[str],
                max_ticks: int | None, backoff_reset_cb,
                bus_publish_fn=None) -> int:
    url = f"{STREAM_HOST}/v3/accounts/{account_id}/pricing/stream"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept-Datetime-Format": "RFC3339",
    }
    params = {"instruments": ",".join(instruments)}
    n = 0
    last_mid: dict[str, float] = {}
    connect_t = time.monotonic()
    reset_armed = True
    with requests.get(url, headers=headers, params=params, stream=True, timeout=30) as r:
        r.raise_for_status()
        print(f"[{now_iso()}] connected {url} ({r.status_code})", flush=True)
        for line in r.iter_lines(decode_unicode=True):
            if reset_armed and time.monotonic() - connect_t >= 30:
                backoff_reset_cb()
                reset_armed = False
            if not line:
                continue
            try:
                row = json.loads(line)
                if row.get("type") != "PRICE":
                    continue
                inst = row["instrument"]
                bids = row.get("bids") or []
                asks = row.get("asks") or []
                if not bids or not asks:
                    continue
                bid = float(bids[0]["price"])
                ask = float(asks[0]["price"])
                mid = (bid + ask) / 2
                spread = ask - bid
                tick = {
                    "ts": now_iso(),
                    "venue": "oanda",
                    "instrument": inst,
                    "bid": bid, "ask": ask, "mid": mid, "spread": spread,
                    "oanda_time": row.get("time"),
                    "tradeable": row.get("tradeable", True),
                }
                append_jsonl(TICK_LOG, tick)
                # Wren-approved 2026-06-21: also publish on bus.
                if bus_publish_fn:
                    bus_publish_fn("market.tick.oanda", tick)

                prev = last_mid.get(inst)
                if prev and abs(mid - prev) / prev >= 0.0003:  # 3 bps move on forex
                    breach_payload = {
                        "venue": "oanda", "instrument": inst, "price": mid,
                        "prev_mid": prev,
                        "delta_bps": round((mid - prev) / prev * 10000, 2),
                        "spread_pips": round(spread * (10000 if "JPY" not in inst else 100), 2),
                    }
                    emit_event("level_breach", inst, mid, breach_payload)
                    if bus_publish_fn:
                        bus_publish_fn("market.level_breach", breach_payload)
                last_mid[inst] = mid

                n += 1
                if n % 20 == 0:
                    print(f"[{now_iso()}] {n} ticks (last {inst} mid={mid})", flush=True)
                if max_ticks and n >= max_ticks:
                    return n
            except Exception as e:
                print(f"[{now_iso()}] parse error: {e}", flush=True)
    return n


def run(token: str, account_id: str, instruments: list[str], max_ticks: int | None) -> int:
    state = {"backoff": 1.0}
    def reset_backoff(): state["backoff"] = 1.0
    # OANDA stream is sync (HTTP chunked); spin up a tiny async bus client in
    # a background thread and provide a sync publish bridge via run_coroutine.
    import threading, asyncio as _aio
    bus_loop = _aio.new_event_loop()
    bus_sub = QSBSubscriber(worker_id="oanda_stream")
    def _bus_thread():
        _aio.set_event_loop(bus_loop)
        bus_loop.run_until_complete(bus_sub.run(subscriptions=["_noop_"]))
    threading.Thread(target=_bus_thread, daemon=True).start()
    # Wait briefly for connection
    for _ in range(20):
        time.sleep(0.1)
        if bus_sub.writer:
            break
    def bus_publish_sync(name: str, payload: dict) -> None:
        if not bus_sub.writer:
            return
        try:
            _aio.run_coroutine_threadsafe(bus_sub.publish(name, payload),
                                           bus_loop).result(timeout=2)
        except Exception:
            pass
    total = 0
    while True:
        try:
            n = stream_once(token, account_id, instruments, max_ticks,
                             reset_backoff, bus_publish_sync)
            total += n
            if max_ticks and total >= max_ticks:
                return total
        except (requests.exceptions.RequestException, OSError) as e:
            print(f"[{now_iso()}] disconnect ({e!r}); reconnect in {state['backoff']:.0f}s", flush=True)
            time.sleep(state["backoff"])
            state["backoff"] = min(state["backoff"] * 2, 30.0)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--instruments", nargs="+", default=DEFAULT_INSTRUMENTS)
    p.add_argument("--max-ticks", type=int, default=None)
    args = p.parse_args()

    env = load_vault()
    for k, v in env.items():
        os.environ.setdefault(k, v)
    token = os.environ.get("OANDA_API_TOKEN", "").strip()
    account_id = os.environ.get("OANDA_ACCOUNT_ID", "").strip()
    if not token or not account_id:
        print("ERROR: OANDA_API_TOKEN + OANDA_ACCOUNT_ID required (vault or env).",
              file=sys.stderr)
        return 2

    def _shutdown(*_):
        print(f"[{now_iso()}] shutdown requested", flush=True)
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    run(token, account_id, args.instruments, args.max_ticks)
    return 0


if __name__ == "__main__":
    sys.exit(main())
