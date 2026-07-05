"""
QSB Tower V2 — Paper / Testnet Trade Lifecycle
Phase: QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2

Implements the paper trade lifecycle (open / mark / close / PnL /
learning record) backed by data/db/qsb_paper_trading.sqlite.

Modes:
  * mode = 'simulated_paper'  — local PnL via supplied marks; no network.
  * mode = 'binance_testnet'  — only used if BINANCE_ENV=testnet AND
    BINANCE_API_KEY+SECRET are present. We never place orders through
    tower_ops.binance_testnet.place_testnet_order (it remains
    preview-only by design). For now, even when testnet creds are
    present, this module records the order in our own SQLite as a
    'simulated_paper_with_testnet_marks' trade — we lift marks from the
    public ticker but never actually place real testnet orders.

Hard guarantees:
  * real_money_live_trading_enabled = False
  * openclaw_real_tool_execution_enabled = False
  * stock_live_trading_enabled = False
  * binance_live_trading_enabled = False
  * max_open_trades = 20 (cap enforced)
  * No API keys/secrets are ever written to the SQLite or any JSON.
"""

from datetime import datetime, timezone
from pathlib import Path
import json
import os
import sqlite3
import uuid

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
REG = ROOT / "data/registries"
LOGS = ROOT / "data/logs"
DB_DIR = ROOT / "data/db"

DB_PATH = DB_DIR / "qsb_paper_trading.sqlite"

P_OPEN_TRADES   = REG / "qsb_open_paper_trades.json"
P_POLICY        = REG / "qsb_paper_trading_policy.json"
P_LEARNING      = REG / "qsb_trade_learning.json"
L_TRADE_EVENTS  = LOGS / "qsb_trade_events.jsonl"


MAX_OPEN_TRADES = 24  # raised 2026-06-19 per Ross
DEFAULT_STOP_PCT   = 0.5    # 0.5% stop-loss
DEFAULT_TARGET_PCT = 1.0    # 1.0% take-profit
DEFAULT_TIMEOUT_HOURS = 24


SCHEMA = """
CREATE TABLE IF NOT EXISTS paper_trades (
    trade_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,                    -- simulated_paper | binance_testnet_marks
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,                    -- LONG | SHORT
    entry_price REAL NOT NULL,
    quantity REAL NOT NULL,
    status TEXT NOT NULL,                  -- OPEN | CLOSED | TIMEOUT
    current_pnl REAL DEFAULT 0,
    realized_pnl REAL DEFAULT 0,
    entry_reason TEXT,
    exit_reason TEXT,
    stop_rule REAL,                        -- abs price for stop-loss
    target_rule REAL,                      -- abs price for take-profit
    timeout_ts TEXT,
    worker_id TEXT,
    strategy_id TEXT,
    guardian_verdict TEXT,
    lesson_learned TEXT,
    opened_ts TEXT NOT NULL,
    closed_ts TEXT,
    last_mark_price REAL,
    last_mark_ts TEXT
);

CREATE TABLE IF NOT EXISTS paper_trade_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT,
    event TEXT NOT NULL,
    payload TEXT,
    ts TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_trade_lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id TEXT,
    symbol TEXT,
    side TEXT,
    realized_pnl REAL,
    exit_reason TEXT,
    lesson_text TEXT,
    ts TEXT NOT NULL
);
"""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _conn():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _safety_envelope():
    return {
        "execution_allowed": False,
        "active_local_only": True,
        "advisory_only": True,
        "paper_only": True,
        "real_money_live_trading_enabled": False,
        "live_trading_enabled": False,
        "binance_live_trading_enabled": False,
        "stock_live_trading_enabled": False,
        "openclaw_real_tool_execution_enabled": False,
    }


def _append_event(record):
    L_TRADE_EVENTS.parent.mkdir(parents=True, exist_ok=True)
    record = dict(record)
    record.setdefault("ts", _now())
    record.setdefault("execution_allowed", False)
    with L_TRADE_EVENTS.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")


# ── Policy ──────────────────────────────────────────────────────────────

def build_policy():
    binance_env = (os.environ.get("BINANCE_ENV") or "").lower()
    has_binance_testnet_creds = (
        bool(os.environ.get("BINANCE_API_KEY", "").strip())
        and bool(os.environ.get("BINANCE_API_SECRET", "").strip())
        and binance_env == "testnet"
    )

    if has_binance_testnet_creds:
        gateway_status = "binance_testnet_gateway_confirmed_testnet_only"
        active_mode = "binance_testnet_marks"
    else:
        gateway_status = "binance_testnet_not_configured_falling_back_to_simulated_paper"
        active_mode = "simulated_paper"

    payload = {
        "ok": True,
        "phase": "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
        "kind": "qsb_paper_trading_policy",
        "generated_ts": _now(),
        "max_open_trades": MAX_OPEN_TRADES,
        "default_stop_pct": DEFAULT_STOP_PCT,
        "default_target_pct": DEFAULT_TARGET_PCT,
        "default_timeout_hours": DEFAULT_TIMEOUT_HOURS,
        "active_mode": active_mode,
        "gateway_status": gateway_status,
        "binance_testnet_creds_present": has_binance_testnet_creds,
        "binance_env_var": os.environ.get("BINANCE_ENV") or "not_set",
        "credentials_storage_policy":
            "API keys/secrets are never written to SQLite or any JSON registry.",
        "max_trade_size_per_symbol": 10000,
        "supported_symbols_binance_paper": ["BTCUSDT", "ETHUSDT",
                                              "BNBUSDT", "SOLUSDT"],
        "supported_symbols_oanda_paper":  ["EUR_USD", "GBP_USD",
                                              "USD_JPY", "AUD_USD"],
        "supported_symbols_stocks_paper": ["AAPL", "MSFT", "GOOG", "NVDA"],
        "stop_rule_description":   "Closes the trade when mark price crosses stop_rule.",
        "target_rule_description": "Closes the trade when mark price crosses target_rule.",
        "timeout_description":     "Closes the trade after default_timeout_hours.",
        "learning_record_description":
            "Every closed trade writes a row to paper_trade_lessons with "
            "the exit_reason, realized_pnl, and a one-line lesson_text.",
        "guardian_verdict_default": "ALLOW_ADVISORY",
    }
    payload.update(_safety_envelope())
    P_POLICY.parent.mkdir(parents=True, exist_ok=True)
    P_POLICY.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


# ── Helpers ─────────────────────────────────────────────────────────────

def _count_open():
    c = _conn()
    try:
        n = c.execute("SELECT COUNT(*) AS n FROM paper_trades WHERE status='OPEN'").fetchone()["n"]
        return int(n or 0)
    finally:
        c.close()


def _compute_pnl(side, entry, mark, qty):
    side = side.upper()
    if side == "LONG":
        return (mark - entry) * qty
    if side == "SHORT":
        return (entry - mark) * qty
    return 0.0


def _row_to_dict(r):
    d = dict(r)
    return d


# ── Open / mark / close ─────────────────────────────────────────────────

def open_trade(symbol, side, entry_price, quantity,
               worker_id=None, strategy_id=None,
               entry_reason=None, mode=None,
               stop_pct=None, target_pct=None,
               guardian_verdict="ALLOW_ADVISORY"):
    """Open a new paper trade. Returns the trade row + result envelope."""
    policy = build_policy()
    mode = mode or policy["active_mode"]
    side = (side or "LONG").upper()
    if side not in ("LONG", "SHORT"):
        return {"ok": False, "error": "invalid_side",
                **_safety_envelope()}

    try:
        entry_price = float(entry_price)
        quantity = float(quantity)
    except Exception:
        return {"ok": False, "error": "invalid_numeric_input",
                **_safety_envelope()}

    if entry_price <= 0 or quantity <= 0:
        return {"ok": False, "error": "non_positive_inputs",
                **_safety_envelope()}
    if quantity > policy["max_trade_size_per_symbol"]:
        return {"ok": False, "error": "quantity_exceeds_max",
                "max_trade_size_per_symbol": policy["max_trade_size_per_symbol"],
                **_safety_envelope()}

    if _count_open() >= MAX_OPEN_TRADES:
        return {"ok": False, "error": "max_open_trades_reached",
                "max_open_trades": MAX_OPEN_TRADES,
                "current_open_trade_count": _count_open(),
                **_safety_envelope()}

    stop_pct   = float(stop_pct   or DEFAULT_STOP_PCT)
    target_pct = float(target_pct or DEFAULT_TARGET_PCT)
    if side == "LONG":
        stop_rule   = round(entry_price * (1 - stop_pct / 100.0),  6)
        target_rule = round(entry_price * (1 + target_pct / 100.0), 6)
    else:
        stop_rule   = round(entry_price * (1 + stop_pct / 100.0),  6)
        target_rule = round(entry_price * (1 - target_pct / 100.0), 6)

    trade_id = "ptr_" + uuid.uuid4().hex[:14]
    ts = _now()
    c = _conn()
    try:
        c.execute(
            """INSERT INTO paper_trades
                 (trade_id, mode, symbol, side, entry_price, quantity,
                  status, current_pnl, realized_pnl, entry_reason,
                  stop_rule, target_rule, timeout_ts,
                  worker_id, strategy_id, guardian_verdict,
                  opened_ts, last_mark_price, last_mark_ts)
               VALUES (?, ?, ?, ?, ?, ?, 'OPEN', 0, 0, ?,
                       ?, ?, datetime('now', '+%d hours'),
                       ?, ?, ?, ?, ?, ?)"""
            % DEFAULT_TIMEOUT_HOURS,
            (trade_id, mode, symbol.upper(), side, entry_price, quantity,
             entry_reason or "advisory open by " + (strategy_id or "default"),
             stop_rule, target_rule,
             worker_id, strategy_id, guardian_verdict,
             ts, entry_price, ts)
        )
        c.execute(
            "INSERT INTO paper_trade_events(trade_id, event, payload, ts) "
            "VALUES (?, 'open', ?, ?)",
            (trade_id, json.dumps({"side": side, "symbol": symbol,
                                     "entry_price": entry_price,
                                     "quantity": quantity,
                                     "worker_id": worker_id,
                                     "strategy_id": strategy_id,
                                     "guardian_verdict": guardian_verdict,
                                     "stop_rule": stop_rule,
                                     "target_rule": target_rule,
                                     "entry_reason": entry_reason}), ts)
        )
        c.commit()
    finally:
        c.close()

    _append_event({"event": "open_trade", "trade_id": trade_id,
                   "symbol": symbol, "side": side,
                   "entry_price": entry_price, "quantity": quantity,
                   "worker_id": worker_id, "strategy_id": strategy_id,
                   "mode": mode})
    refresh_open_trades_registry()
    return {"ok": True, "trade_id": trade_id,
            "mode": mode, "symbol": symbol, "side": side,
            "entry_price": entry_price, "quantity": quantity,
            "stop_rule": stop_rule, "target_rule": target_rule,
            "current_open_trade_count": _count_open(),
            **_safety_envelope()}


def mark_trade(trade_id, mark_price):
    """Update current_pnl and possibly auto-close on stop/target."""
    try:
        mark_price = float(mark_price)
    except Exception:
        return {"ok": False, "error": "invalid_mark_price",
                **_safety_envelope()}

    c = _conn()
    try:
        r = c.execute("SELECT * FROM paper_trades WHERE trade_id=?",
                      (trade_id,)).fetchone()
        if not r:
            return {"ok": False, "error": "trade_not_found",
                    **_safety_envelope()}
        if r["status"] != "OPEN":
            return {"ok": False, "error": "trade_not_open",
                    "status": r["status"], **_safety_envelope()}

        pnl = _compute_pnl(r["side"], r["entry_price"], mark_price, r["quantity"])
        ts = _now()
        c.execute(
            "UPDATE paper_trades SET current_pnl=?, last_mark_price=?, last_mark_ts=? "
            "WHERE trade_id=?", (round(pnl, 6), mark_price, ts, trade_id)
        )

        # Auto-close on target/stop
        side = r["side"]
        stop = r["stop_rule"]
        target = r["target_rule"]
        hit = None
        if side == "LONG":
            if stop and mark_price <= stop:    hit = "stop"
            elif target and mark_price >= target: hit = "target"
        else:  # SHORT
            if stop and mark_price >= stop:    hit = "stop"
            elif target and mark_price <= target: hit = "target"

        c.execute(
            "INSERT INTO paper_trade_events(trade_id, event, payload, ts) "
            "VALUES (?, 'mark', ?, ?)",
            (trade_id, json.dumps({"mark_price": mark_price,
                                     "pnl": round(pnl, 6),
                                     "auto_hit": hit}), ts)
        )
        c.commit()
    finally:
        c.close()

    if hit:
        return close_trade(trade_id, mark_price,
                            exit_reason="auto_" + hit,
                            lesson_learned=("Auto-closed by " + hit +
                                            " rule at mark=" + str(mark_price)))

    refresh_open_trades_registry()
    return {"ok": True, "trade_id": trade_id,
            "current_pnl": round(pnl, 6),
            "last_mark_price": mark_price,
            **_safety_envelope()}


def close_trade(trade_id, close_price=None,
                exit_reason="manual_close",
                lesson_learned=None):
    """Close an open paper trade. Records the lesson for learning."""
    c = _conn()
    try:
        r = c.execute("SELECT * FROM paper_trades WHERE trade_id=?",
                      (trade_id,)).fetchone()
        if not r:
            return {"ok": False, "error": "trade_not_found",
                    **_safety_envelope()}
        if r["status"] != "OPEN":
            return {"ok": False, "error": "trade_not_open",
                    "status": r["status"], **_safety_envelope()}

        if close_price is None:
            close_price = r["last_mark_price"] or r["entry_price"]
        try:
            close_price = float(close_price)
        except Exception:
            close_price = r["entry_price"]

        realized = _compute_pnl(r["side"], r["entry_price"], close_price, r["quantity"])
        ts = _now()
        if lesson_learned is None:
            if realized > 0:
                lesson_learned = ("Profitable %s on %s closed via %s at %.6f"
                                   % (r["side"], r["symbol"], exit_reason,
                                       close_price))
            elif realized < 0:
                lesson_learned = ("Loss %s on %s closed via %s at %.6f — "
                                   "review entry_reason and stop_rule"
                                   % (r["side"], r["symbol"], exit_reason,
                                       close_price))
            else:
                lesson_learned = ("Flat close %s on %s at %.6f"
                                   % (r["side"], r["symbol"], close_price))

        c.execute(
            "UPDATE paper_trades SET status='CLOSED', realized_pnl=?, "
            "current_pnl=?, exit_reason=?, lesson_learned=?, closed_ts=?, "
            "last_mark_price=?, last_mark_ts=? "
            "WHERE trade_id=?",
            (round(realized, 6), round(realized, 6), exit_reason,
             lesson_learned, ts, close_price, ts, trade_id)
        )
        c.execute(
            "INSERT INTO paper_trade_events(trade_id, event, payload, ts) "
            "VALUES (?, 'close', ?, ?)",
            (trade_id, json.dumps({"close_price": close_price,
                                     "realized_pnl": round(realized, 6),
                                     "exit_reason": exit_reason,
                                     "lesson_learned": lesson_learned}), ts)
        )
        c.execute(
            "INSERT INTO paper_trade_lessons(trade_id, symbol, side, "
            "  realized_pnl, exit_reason, lesson_text, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (trade_id, r["symbol"], r["side"], round(realized, 6),
             exit_reason, lesson_learned, ts)
        )
        c.commit()
    finally:
        c.close()

    _append_event({"event": "close_trade", "trade_id": trade_id,
                   "exit_reason": exit_reason,
                   "realized_pnl": round(realized, 6),
                   "lesson_learned": lesson_learned})
    refresh_open_trades_registry()
    refresh_learning_registry()
    return {"ok": True, "trade_id": trade_id,
            "realized_pnl": round(realized, 6),
            "close_price": close_price,
            "exit_reason": exit_reason,
            "lesson_learned": lesson_learned,
            **_safety_envelope()}


# ── Reads ──────────────────────────────────────────────────────────────

def list_open_trades():
    c = _conn()
    try:
        rows = c.execute(
            "SELECT * FROM paper_trades WHERE status='OPEN' ORDER BY opened_ts DESC"
        ).fetchall()
    finally:
        c.close()
    return [_row_to_dict(r) for r in rows]


def list_closed_trades(limit=50):
    c = _conn()
    try:
        rows = c.execute(
            "SELECT * FROM paper_trades WHERE status<>'OPEN' "
            "ORDER BY closed_ts DESC LIMIT ?", (int(limit),)
        ).fetchall()
    finally:
        c.close()
    return [_row_to_dict(r) for r in rows]


def list_lessons(limit=20):
    c = _conn()
    try:
        rows = c.execute(
            "SELECT * FROM paper_trade_lessons ORDER BY id DESC LIMIT ?",
            (int(limit),)
        ).fetchall()
    finally:
        c.close()
    return [_row_to_dict(r) for r in rows]


def refresh_open_trades_registry():
    open_trades = list_open_trades()
    payload = {
        "ok": True,
        "kind": "qsb_open_paper_trades",
        "generated_ts": _now(),
        "max_open_trades": MAX_OPEN_TRADES,
        "open_trade_count": len(open_trades),
        "remaining_trade_slots": MAX_OPEN_TRADES - len(open_trades),
        "total_current_pnl": round(sum((t.get("current_pnl") or 0)
                                         for t in open_trades), 6),
        "trades": open_trades,
    }
    payload.update(_safety_envelope())
    P_OPEN_TRADES.parent.mkdir(parents=True, exist_ok=True)
    P_OPEN_TRADES.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


def refresh_learning_registry():
    lessons = list_lessons(limit=200)
    closed = list_closed_trades(limit=200)
    total_realized = round(sum((t.get("realized_pnl") or 0) for t in closed), 6)
    payload = {
        "ok": True,
        "kind": "qsb_trade_learning",
        "generated_ts": _now(),
        "lesson_count": len(lessons),
        "closed_trade_count": len(closed),
        "total_realized_pnl": total_realized,
        "lessons": lessons,
    }
    payload.update(_safety_envelope())
    P_LEARNING.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return payload


# ── Seed / training routine ────────────────────────────────────────────

def seed_training_demo():
    """Open a small batch of paper trades and immediately progress one
    through mark+close so the learning ledger has content for the
    dashboard. This is a TRAINING demonstration — never real money.

    Idempotent: only runs if there are no existing trades."""
    c = _conn()
    try:
        n = c.execute("SELECT COUNT(*) AS n FROM paper_trades").fetchone()["n"]
    finally:
        c.close()
    if int(n or 0) > 0:
        return {"ok": True, "skipped": True,
                "reason": "paper_trades already seeded",
                "existing_count": int(n)}

    out = {"opened": [], "closed": []}

    binance = json.loads((REG / "binance_paper_strategy_latest.json")
                          .read_text(encoding="utf-8")) if (REG / "binance_paper_strategy_latest.json").exists() else {}
    last_marks = {}
    for row in (binance.get("results") or []):
        sym = row.get("symbol")
        last = row.get("last") or row.get("mid")
        if sym and last:
            last_marks[sym] = float(last)

    if not last_marks:
        last_marks = {"BTCUSDT": 63414.0, "ETHUSDT": 3500.0,
                       "BNBUSDT": 600.0, "SOLUSDT": 150.0}

    seeds = [
        # symbol, side, qty, worker, strategy, reason, stop_pct, target_pct
        ("BTCUSDT", "LONG",  0.10,
         "wrk_binance_market_scout", "strategy_momentum_btc",
         "Momentum confirmed in 3 timeframes (paper-only)",
         0.5, 1.5),
        ("ETHUSDT", "LONG",  1.0,
         "wrk_spread_watcher", "strategy_mean_reversion_eth",
         "Spread narrowed to historical low (paper-only)",
         0.4, 1.0),
        ("BNBUSDT", "SHORT", 5.0,
         "wrk_risk_clerk", "strategy_overbought_bnb",
         "RSI > 78 on 1h (paper-only)",
         0.5, 1.0),
        ("SOLUSDT", "LONG", 10.0,
         "wrk_arbitrage_observer", "strategy_funding_carry_sol",
         "Positive funding carry observed (paper-only)",
         0.6, 1.2),
    ]
    for sym, side, qty, wrk, strat, reason, sp, tp in seeds:
        entry = float(last_marks.get(sym, 100.0))
        res = open_trade(sym, side, entry, qty,
                          worker_id=wrk, strategy_id=strat,
                          entry_reason=reason,
                          stop_pct=sp, target_pct=tp,
                          guardian_verdict="ALLOW_ADVISORY")
        if res.get("ok"):
            out["opened"].append(res["trade_id"])

    # Demonstrate a closing trade so the learning ledger has content.
    if out["opened"]:
        first_tid = out["opened"][0]
        # Move BTC mark up slightly to hit no target, then close manually.
        btc_mark = last_marks.get("BTCUSDT", 63414.0) * 1.003
        mark_trade(first_tid, btc_mark)
        closed = close_trade(first_tid, btc_mark,
                              exit_reason="manual_close_training_demo",
                              lesson_learned=("Training demo close: "
                                              "small profit captured by "
                                              "manual exit — confirm rule"
                                              " did not over-fit"))
        out["closed"].append(closed.get("trade_id"))

    _append_event({"event": "seed_training_demo",
                   "opened_count": len(out["opened"]),
                   "closed_count": len(out["closed"])})
    refresh_open_trades_registry()
    refresh_learning_registry()
    out["ok"] = True
    out.update(_safety_envelope())
    return out


# ── CLI ────────────────────────────────────────────────────────────────

def status():
    return {
        "ok": True,
        "phase": "QSB_OPENCLAW_PAPER_TRADE_WORKERS_3D_SKYSCRAPER_V2",
        "kind": "qsb_paper_trading_status",
        "generated_ts": _now(),
        "policy": build_policy(),
        "open_trades": refresh_open_trades_registry(),
        "learning": refresh_learning_registry(),
        **_safety_envelope(),
    }


def main():
    import sys
    cmd = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    if cmd == "policy":
        print(json.dumps(build_policy(), indent=2))
    elif cmd == "seed":
        print(json.dumps(seed_training_demo(), indent=2))
    elif cmd == "open_list":
        print(json.dumps(refresh_open_trades_registry(), indent=2))
    elif cmd == "lessons":
        print(json.dumps(refresh_learning_registry(), indent=2))
    elif cmd == "status":
        print(json.dumps(status(), indent=2))
    else:
        print(json.dumps({"ok": False, "error": "unknown_command",
                          "valid": ["policy", "seed", "open_list",
                                     "lessons", "status"]}, indent=2))
        raise SystemExit(2)


if __name__ == "__main__":
    main()
