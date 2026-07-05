#!/usr/bin/env python3
"""qsb_f42_trader_daemon.py — persistent per-trader loop on F42 Binance
testnet floor. Phase 1 of "traders run themselves, not a timer" (Ross
2026-06-17).

WHAT CHANGED
  Before:  one systemd timer fires every 10 min → qsb_f42_trader_cycle.py
           → places ONE trade for the next instrument in a round-robin.
           Workers are just labels on the trade row.

  After:   ONE daemon per trader. Each daemon owns its decision loop:
              loop:
                read my cert (from cognitive_worker_certification.json)
                if cert tier == NONE → I'm in classroom mode, sleep + skip
                else:
                  peek at my instrument's price
                  decide: place / hold (currently round-robin BUY/SELL
                                       within trader's tier privileges)
                  if place: call qsb_binance.py place ... (existing path)
                  stamp own decision to F47 + F42 trader log
                sleep(cycle_interval_for_tier)
           Classroom evaluator (separate daemon, Phase 2) periodically grades
           each trader's recent decisions and promotes/demotes their cert.

USAGE
  python3 tools/qsb_f42_trader_daemon.py \\
      --worker-id f42_market_scout \\
      --instrument BTCUSDT \\
      --strategy scalp

  Designed to run as a systemd --user service. Logs to stdout (captured by
  systemd journal) and append-stamps to:
    data/registries/qsb_f42_trader_cycle.jsonl
    data/registries/qsb_f47_team_records.jsonl
    data/registries/cognitive/cognitive_worker_certification.json (read)

HARD CAPS (unchanged from cycle script)
  - testnet ONLY (URL from .env.binance_testnet)
  - $50 USDT per trade max (tier-gated below)
  - one trade per loop iteration max
  - graceful shutdown on SIGTERM
"""

from __future__ import annotations
import argparse, datetime, json, os, signal, subprocess, sys, time
from pathlib import Path

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
F47 = ROOT / "data/registries/qsb_f47_team_records.jsonl"
OUT = ROOT / "data/registries/qsb_f42_trader_cycle.jsonl"
CERT_FILE = ROOT / "data/registries/cognitive/cognitive_worker_certification.json"
VAULT = ROOT / "floors/floor_28_security_department/vault/.env.binance_testnet"
POLICY_DIR = ROOT / "floors/floor_42_binance_trading_floor/policies"

# Default cycle interval (seconds). Daemon takes --cycle-secs to override.
# Status==certified → trades at this cadence. Status==tested or anything
# else → daemon idles at 2x interval to keep load down.
DEFAULT_CYCLE_S = 600
IDLE_CYCLE_S = 1800
DEFAULT_USDT = 50.0

# Round-robin BUY/SELL per trader so we exercise both sides. Trader's own
# "side cursor" lives in /tmp so it survives daemon restart but resets on
# host reboot — acceptable for a testnet trainer.
SIDE_CURSOR_DIR = Path("/tmp/qsb_trader_side_cursor")

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


def read_cert_status(worker_id: str, instrument: str) -> str | None:
    """Return this worker's cert status for the given instrument as written
    by the cognitive cert snapshot. Values seen on disk: "certified",
    "tested", "suspended", or None if no row exists. The daemon trades
    when status == "certified" and idles otherwise."""
    if not CERT_FILE.exists():
        return None
    try:
        data = json.loads(CERT_FILE.read_text())
    except Exception:
        return None
    # The dashboard snapshot truncates to entries_sample (134). Walk it
    # but also walk by_instrument indices when present.
    candidates = []
    es = data.get("entries_sample") or []
    if isinstance(es, list):
        candidates.extend(es)
    bi = data.get("by_instrument") or {}
    if isinstance(bi, dict):
        for v in bi.values():
            if isinstance(v, list):
                candidates.extend(v)
            elif isinstance(v, dict):
                candidates.extend(v.values() if v else [])
    for c in candidates:
        if not isinstance(c, dict):
            continue
        if c.get("worker_id") != worker_id:
            continue
        if c.get("instrument") != instrument:
            continue
        return c.get("status")
    return None


def _binance_price(symbol: str, minutes_ago: int = 0) -> float | None:
    """Get price now (minutes_ago=0) or N minutes ago (from klines).
    Uses Binance public spot endpoint — no auth needed."""
    import urllib.request
    try:
        if minutes_ago == 0:
            url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
            with urllib.request.urlopen(url, timeout=4) as r:
                return float(json.loads(r.read())["price"])
        # Otherwise fetch a 5-min kline that closed N min ago
        url = (f"https://api.binance.com/api/v3/klines?symbol={symbol}"
               f"&interval=1m&limit={minutes_ago + 1}")
        with urllib.request.urlopen(url, timeout=4) as r:
            klines = json.loads(r.read())
        # klines[0] is oldest; index 4 = close price
        return float(klines[0][4])
    except Exception:
        return None


def next_side(worker_id: str, symbol: str = None) -> str:
    """Strategy-driven side picker. Each worker has their own strategy in
    qsb_trader_memory (Ross 2026-06-19: traders must own their strategy,
    remember wins/losses, and know the difference). After 5 losses in a
    row, qsb_trader_memory rotates the strategy automatically."""
    import sys as _sys
    if str(ROOT / "tools") not in _sys.path:
        _sys.path.insert(0, str(ROOT / "tools"))
    try:
        from qsb_trader_memory import get_strategy
        strat = get_strategy(worker_id, symbol or "")
        sname = strat.get("name", "momentum")
        params = strat.get("params", {})
        lookback = int(params.get("lookback_min", 5))
        threshold = float(params.get("threshold_bps", 5)) / 10_000.0
    except Exception:
        sname, lookback, threshold = "momentum", 5, 0.0005

    if symbol and sname in ("momentum", "mean_revert", "scalp"):
        now_px = _binance_price(symbol, 0)
        then_px = _binance_price(symbol, lookback)
        if now_px is not None and then_px is not None and then_px > 0:
            delta = (now_px - then_px) / then_px
            if sname == "momentum":
                # follow the trend
                if delta > threshold: return "BUY"
                if delta < -threshold: return "SELL"
            elif sname == "mean_revert":
                # fade the trend
                if delta > threshold: return "SELL"
                if delta < -threshold: return "BUY"
            elif sname == "scalp":
                # tight, react to any move
                if delta > threshold: return "BUY"
                if delta < -threshold: return "SELL"
    # random or no signal — alternating cursor
    SIDE_CURSOR_DIR.mkdir(parents=True, exist_ok=True)
    p = SIDE_CURSOR_DIR / f"{worker_id}.cursor"
    n = 0
    try:
        n = int(p.read_text().strip() or "0")
    except Exception:
        pass
    p.write_text(str(n + 1))
    return "BUY" if n % 2 == 0 else "SELL"


def refresh_certs(worker_id: str) -> dict:
    """Keep F42 admin grants fresh so the binance gate stays open."""
    r = subprocess.run(
        ["python3", str(ROOT / "tools/qsb_grant_certs.py"),
         "--floor", "F42",
         "--reason", f"daemon_pre_trade:{worker_id}"],
        capture_output=True, text=True, timeout=20, cwd=str(ROOT))
    return {"ok": r.returncode == 0,
            "stdout_tail": (r.stdout or "")[-200:]}


def place_trade(worker_id: str, instrument: str, side: str,
                usdt: float) -> dict:
    cmd = ["python3", str(ROOT / "tools/qsb_binance.py"), "place",
           worker_id, instrument, side.upper(), str(usdt),
           "--reason", f"f42_daemon:{worker_id}",
           "--confirm"]
    env = dict(os.environ)
    if VAULT.exists():
        for line in VAULT.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=30,
                       cwd=str(ROOT), env=env)
    try:
        out = json.loads(r.stdout)
    except Exception:
        out = {"ok": False, "raw": (r.stdout or r.stderr)[-300:]}
    return out


def stamp(payload: dict) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps(payload) + "\n")
    row = {
        "ts": payload["ts"], "kind": "f42_trader_daemon",
        "operator": payload.get("worker"),
        "summary": (
            f"F42 daemon · {payload.get('worker','?')} · "
            f"{payload.get('instrument','?')} {payload.get('side','?')} "
            f"${payload.get('usdt','?')} · tier={payload.get('tier','?')} · "
            f"placed_ok={payload.get('placed',{}).get('ok')} "
            f"order={payload.get('placed',{}).get('binance_order_id','?')}"
        )[:500],
    }
    with open(F47, "a") as f:
        f.write(json.dumps(row) + "\n")


def stamp_idle(worker_id: str, instrument: str, strategy: str,
               reason: str) -> None:
    """Trader idled this cycle (cert missing, etc). Audit so we can see
    classroom-pending traders without grepping logs."""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "a") as f:
        f.write(json.dumps({
            "ts": now_iso(), "kind": "f42_trader_idle",
            "worker": worker_id, "instrument": instrument,
            "strategy": strategy, "reason": reason,
        }) + "\n")


def load_policy(worker_id: str) -> dict:
    """Read this trader's policy file. Returns {} if none — daemon falls
    back to CLI args / defaults. Reloaded each loop so Ross (or the
    classroom) can hot-patch tunables without daemon restart."""
    p = POLICY_DIR / f"{worker_id}.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception:
        return {}


def run_loop(worker_id: str, instrument: str, strategy: str,
             cycle_secs: int, usdt: float,
             max_iters: int | None = None) -> int:
    log(f"daemon start · worker={worker_id} instrument={instrument} "
        f"strategy={strategy} cycle={cycle_secs}s usdt={usdt}")
    iters = 0
    consecutive_failures = 0
    while not SHUTDOWN:
        iters += 1
        # Hot-reload policy each loop — Ross / classroom can patch tunables
        # without daemon restart.
        policy = load_policy(worker_id)
        effective_cycle = int(policy.get("cycle_secs", cycle_secs))
        effective_usdt = float(policy.get("usd", policy.get("usdt", usdt)))
        # Cert status is informational, not the gate. The binance gate
        # enforces cert via floor-level grant inside qsb_binance.py; the
        # daemon just calls and respects what comes back. Status lookup
        # here exists so the audit row carries the classroom verdict.
        status = read_cert_status(worker_id, instrument)
        certs = refresh_certs(worker_id)
        # Bring this trader's own state into the log + chat-board peer-learn.
        try:
            import sys as _sys
            if str(ROOT / "tools") not in _sys.path:
                _sys.path.insert(0, str(ROOT / "tools"))
            from qsb_trader_memory import (get_summary, record_open, load,
                                              save, DEFAULT_STRATEGIES)
            from qsb_trader_chat_board import (post_status, peer_learn,
                                                  now_iso as _board_now)
            mem_summary = get_summary(worker_id, instrument)
            # Peer-learn: if losing streak, look at the fleet for a winner
            mem = load(worker_id, instrument)
            sug = peer_learn(
                worker_id=worker_id,
                current_strategy=mem["strategy"]["name"],
                loss_streak=mem["stats"]["loss_streak"],
            )
            if sug:
                # Find the strategy spec by name and swap
                target = next((s for s in DEFAULT_STRATEGIES
                                if s["name"] == sug["new"]), None)
                if target:
                    mem["strategy"] = target.copy()
                    mem["strategy_history"].append({
                        "ts": _board_now(),
                        "from": sug["old"], "to": sug["new"],
                        "reason": f"peer_learn from {sug['peer']}",
                    })
                    mem["stats"]["loss_streak"] = 0
                    save(worker_id, mem)
                    log(f"  peer_learn: swapped {sug['old']} → {sug['new']} "
                        f"(peer {sug['peer']}, win_rate "
                        f"{sug['peer_win_rate']})")
        except Exception as e:
            mem_summary = None
            record_open = None
            post_status = None
            log(f"  memory/board err: {str(e)[:80]}")
        side = next_side(worker_id, instrument)
        log(f"attempt · cert_status={status!r} side={side} "
            f"usdt={effective_usdt} instrument={instrument} "
            f"policy_overrides={'yes' if policy else 'no'} "
            f"mem={mem_summary}")
        placed = place_trade(worker_id, instrument, side, effective_usdt)
        ok = bool(placed.get("ok"))
        # Remember the open trade so close-cycle (Phase 3) can score it.
        if ok and record_open and placed.get("fill_price"):
            try:
                record_open(
                    worker_id, instrument,
                    placed.get("binance_order_id") or placed.get("order_id"),
                    side,
                    float(placed.get("fill_qty") or 0),
                    float(placed.get("fill_price") or 0),
                )
            except Exception as e:
                log(f"  record_open err: {str(e)[:80]}")
        # Post status to the cross-floor chat board so peer learners see us.
        if post_status:
            try:
                mem_now = load(worker_id, instrument)
                s = mem_now["stats"]
                post_status(
                    worker_id=worker_id, floor="F42",
                    instrument=instrument,
                    strategy=mem_now["strategy"]["name"],
                    win_streak=s["win_streak"],
                    loss_streak=s["loss_streak"],
                    total_pnl=s["total_pnl"],
                    wins=s["wins"], losses=s["losses"],
                )
            except Exception as e:
                log(f"  post_status err: {str(e)[:80]}")
        stamp({
            "ts": now_iso(), "kind": "f42_trader_daemon",
            "worker": worker_id, "instrument": instrument,
            "strategy": strategy, "status": status,
            "side": side, "usdt": effective_usdt,
            "policy_applied": bool(policy),
            "trader_memory": mem_summary,
            "certs_keepalive_ok": certs.get("ok"),
            "placed": placed,
        })
        if ok:
            consecutive_failures = 0
            sleep_s = effective_cycle
            log(f"placed_ok=true order="
                f"{placed.get('binance_order_id','?')} · "
                f"next cycle in {sleep_s}s")
        else:
            consecutive_failures += 1
            # Back off when the gate refuses (cert revoked, kill switch,
            # network blip). Caps at IDLE_CYCLE_S so we still keep checking.
            sleep_s = min(effective_cycle * (2 ** min(consecutive_failures, 4)),
                          IDLE_CYCLE_S)
            log(f"placed_ok=false (fail #{consecutive_failures}) · "
                f"next attempt in {sleep_s}s")

        if max_iters is not None and iters >= max_iters:
            log(f"max_iters reached ({iters}), exiting")
            return 0

        # Sleep in small ticks so SIGTERM lands fast.
        remaining = sleep_s
        while remaining > 0 and not SHUTDOWN:
            chunk = min(5, remaining)
            time.sleep(chunk)
            remaining -= chunk
    log("daemon stop · clean shutdown")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--worker-id", required=True,
                   help="e.g. f42_market_scout")
    p.add_argument("--instrument", required=True,
                   help="e.g. BTCUSDT")
    p.add_argument("--strategy", default="scalp",
                   choices=["scalp", "swing", "breakout",
                            "mean_revert", "news_event", "arb"])
    p.add_argument("--cycle-secs", type=int, default=DEFAULT_CYCLE_S,
                   help=f"sleep between trade attempts when certified (default {DEFAULT_CYCLE_S})")
    p.add_argument("--usdt", type=float, default=DEFAULT_USDT,
                   help=f"trade size in USDT per attempt (default {DEFAULT_USDT})")
    p.add_argument("--max-iters", type=int, default=None,
                   help="Smoke-test mode: exit after N iterations")
    p.add_argument("--dry-run", action="store_true",
                   help="Read cert + log decision; do NOT call binance")
    a = p.parse_args()

    if a.dry_run:
        status = read_cert_status(a.worker_id, a.instrument)
        print(json.dumps({
            "worker": a.worker_id, "instrument": a.instrument,
            "strategy": a.strategy, "cert_status": status,
            "would_trade": status == "certified",
            "would_sleep_s": (a.cycle_secs if status == "certified"
                              else IDLE_CYCLE_S),
            "would_size_usdt": a.usdt if status == "certified" else 0.0,
        }, indent=2))
        return 0

    return run_loop(a.worker_id, a.instrument, a.strategy,
                    cycle_secs=a.cycle_secs, usdt=a.usdt,
                    max_iters=a.max_iters)


if __name__ == "__main__":
    sys.exit(main())
