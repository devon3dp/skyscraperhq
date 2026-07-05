#!/usr/bin/env python3
"""qsb_f43_trader_daemon.py — persistent per-symbol loop on F43 stocks
floor, trading Alpaca paper.

Phase 1 mirror of qsb_f42_trader_daemon.py for the US equities side. One
daemon per symbol (AAPL, SPY, QQQ).

Hard caps:
  - PAPER ONLY — hits https://paper-api.alpaca.markets
  - $50 USD notional per order
  - One order per cycle per symbol
  - Reads cert status (informational), trusts the gate
  - Stamps F47 + F43 cycle ledger; never touches vault

Loop:
  forever:
    refresh certs (qsb_grant_certs --floor F43 — best-effort)
    pick side (BUY/SELL round-robin per symbol, cursor in /tmp)
    POST /v2/orders to Alpaca paper with notional=50
    stamp result
    sleep(--cycle-secs)
"""

from __future__ import annotations
import argparse, datetime, json, os, re, signal, subprocess, sys, time
import urllib.request, urllib.error
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
OUT = ROOT / "data/registries/qsb_f43_trader_cycle.jsonl"
CERT_FILE = ROOT / "data/registries/cognitive/cognitive_worker_certification.json"
VAULT = ROOT / "floors/floor_28_security_department/vault/.env.alpaca_paper"
POLICY_DIR = ROOT / "floors/floor_43_alpaca_paper_floor/policies"

DEFAULT_CYCLE_S = 600
IDLE_CYCLE_S = 1800
DEFAULT_USD = 50.0
SIDE_CURSOR_DIR = Path("/tmp/qsb_f43_side_cursor")

ALPACA_PAPER_BASE = "https://paper-api.alpaca.markets"

SHUTDOWN = False


def now_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(
        timespec="seconds").replace("+00:00", "Z")


def log(msg: str) -> None:
    print(f"[{now_iso()}] {msg}", flush=True)


def _on_sigterm(signum, frame):
    global SHUTDOWN
    SHUTDOWN = True
    log(f"received signal {signum}, will exit after current loop")


signal.signal(signal.SIGTERM, _on_sigterm)
signal.signal(signal.SIGINT, _on_sigterm)


def load_vault() -> dict:
    """Read .env.alpaca_paper, handle `export VAR=val` syntax."""
    env = {}
    if not VAULT.exists():
        return env
    for line in VAULT.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        line = re.sub(r'^export\s+', '', line)
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\"")
    return env


def read_cert_status(worker_id: str, symbol: str) -> str | None:
    if not CERT_FILE.exists():
        return None
    try:
        data = json.loads(CERT_FILE.read_text())
    except Exception:
        return None
    candidates = []
    es = data.get("entries_sample") or []
    if isinstance(es, list):
        candidates.extend(es)
    for c in candidates:
        if not isinstance(c, dict):
            continue
        if c.get("worker_id") != worker_id:
            continue
        if c.get("instrument") != symbol:
            continue
        return c.get("status")
    return None


def next_side(symbol: str) -> str:
    SIDE_CURSOR_DIR.mkdir(parents=True, exist_ok=True)
    p = SIDE_CURSOR_DIR / f"{symbol}.cursor"
    n = 0
    try:
        n = int(p.read_text().strip() or "0")
    except Exception:
        pass
    p.write_text(str(n + 1))
    return "buy" if n % 2 == 0 else "sell"


def refresh_certs(symbol: str) -> dict:
    """Best-effort floor-level cert keepalive."""
    try:
        r = subprocess.run(
            ["python3", str(ROOT / "tools/qsb_grant_certs.py"),
             "--floor", "F43",
             "--reason", f"daemon_pre_trade:{symbol}"],
            capture_output=True, text=True, timeout=20, cwd=str(ROOT))
        return {"ok": r.returncode == 0,
                "stdout_tail": (r.stdout or "")[-200:]}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def alpaca_place_order(symbol: str, side: str, notional_usd: float,
                       env: dict) -> dict:
    """POST /v2/orders to Alpaca paper. Returns the broker's response."""
    api_key = env.get("ALPACA_API_KEY") or env.get("APCA_API_KEY_ID")
    api_sec = env.get("ALPACA_API_SECRET") or env.get("APCA_API_SECRET_KEY")
    if not (api_key and api_sec):
        return {"ok": False, "error": "missing ALPACA_API_KEY/SECRET in vault"}
    url = f"{ALPACA_PAPER_BASE}/v2/orders"
    body = {
        "symbol": symbol,
        "notional": str(round(notional_usd, 2)),
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_sec,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = json.loads(r.read())
        return {"ok": True, "order_id": data.get("id"),
                "client_order_id": data.get("client_order_id"),
                "status": data.get("status"), "symbol": data.get("symbol"),
                "side": data.get("side"), "notional": data.get("notional")}
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", errors="replace")[:300]
        return {"ok": False, "http_status": e.code, "error": err}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def stamp(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(payload) + "\n")
    row = {
        "ts": payload["ts"], "kind": "f43_trader_daemon",
        "operator": payload.get("worker"),
        "summary": (
            f"F43 daemon · {payload.get('symbol','?')} "
            f"{payload.get('side','?')} ${payload.get('usd','?')} · "
            f"cert={payload.get('cert_status','?')} · "
            f"placed_ok={payload.get('placed',{}).get('ok')} "
            f"alpaca_order={payload.get('placed',{}).get('order_id','?')}"
        )[:500],
    }
    with open(F47, "a") as f:
        f.write(json.dumps(row) + "\n")


def load_policy(worker_id: str) -> dict:
    """Hot-reload policy file on each loop. {} if none."""
    p = POLICY_DIR / f"{worker_id}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def run_loop(worker_id: str, symbol: str, cycle_secs: int, usd: float,
             max_iters: int | None = None) -> int:
    env = load_vault()
    log(f"daemon start · worker={worker_id} symbol={symbol} "
        f"cycle={cycle_secs}s usd={usd}")
    iters = 0
    failures = 0
    while not SHUTDOWN:
        iters += 1
        policy = load_policy(worker_id)
        effective_cycle = int(policy.get("cycle_secs", cycle_secs))
        effective_usd = float(policy.get("usd", usd))
        cert_status = read_cert_status(worker_id, symbol)
        certs = refresh_certs(symbol)
        side = next_side(symbol)
        log(f"attempt · cert={cert_status!r} side={side} "
            f"usd={effective_usd} symbol={symbol} "
            f"policy={'yes' if policy else 'no'}")
        placed = alpaca_place_order(symbol, side, effective_usd, env)
        ok = bool(placed.get("ok"))
        stamp({
            "ts": now_iso(), "kind": "f43_trader_daemon",
            "worker": worker_id, "symbol": symbol,
            "cert_status": cert_status, "side": side, "usd": effective_usd,
            "policy_applied": bool(policy),
            "certs_keepalive_ok": certs.get("ok"),
            "placed": placed,
        })
        if ok:
            failures = 0
            sleep_s = effective_cycle
            log(f"placed_ok=true order={placed.get('order_id','?')} "
                f"status={placed.get('status','?')} · next {sleep_s}s")
        else:
            failures += 1
            sleep_s = min(effective_cycle * (2 ** min(failures, 4)),
                          IDLE_CYCLE_S)
            log(f"placed_ok=false (fail #{failures}): "
                f"{placed.get('error','?')[:120]} · next {sleep_s}s")

        if max_iters is not None and iters >= max_iters:
            log(f"max_iters reached ({iters}), exiting")
            return 0

        remaining = sleep_s
        while remaining > 0 and not SHUTDOWN:
            time.sleep(min(5, remaining))
            remaining -= 5
    log("daemon stop · clean shutdown")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--worker-id", required=True,
                   help="e.g. f43_stock_scout")
    p.add_argument("--symbol", required=True,
                   choices=["AAPL", "SPY", "QQQ", "MSFT", "NVDA", "TSLA"])
    p.add_argument("--cycle-secs", type=int, default=DEFAULT_CYCLE_S)
    p.add_argument("--usd", type=float, default=DEFAULT_USD)
    p.add_argument("--max-iters", type=int, default=None)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()

    if a.dry_run:
        env = load_vault()
        print(json.dumps({
            "worker": a.worker_id, "symbol": a.symbol,
            "cycle_secs": a.cycle_secs, "usd": a.usd,
            "cert_status": read_cert_status(a.worker_id, a.symbol),
            "alpaca_key_loaded": bool(env.get("ALPACA_API_KEY")),
        }, indent=2))
        return 0

    return run_loop(a.worker_id, a.symbol, a.cycle_secs, a.usd,
                    max_iters=a.max_iters)


if __name__ == "__main__":
    sys.exit(main())
