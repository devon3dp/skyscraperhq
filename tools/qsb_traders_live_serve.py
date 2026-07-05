#!/usr/bin/env python3
"""qsb_traders_live_serve.py — standalone live view of belief-driven traders.

Ross 2026-06-22: dedicated dashboard for the NEW belief-driven trading stack
(NOT the old timer-based F41/F42/F43 cycle counts surfaced on /tower_wins).

Authorship (team co-write):
  Wren-fast: HTML skeleton (4 card sections with semantic IDs)
  Hermes-8b: JSON shape for /api/traders_live response
  Claude:    standalone HTTP server, log-scrape integration, glue + CSS/JS
             that ties Wren's body + Hermes's shape into auto-refreshing page

No clock. Reads logs/intelligence/trader_*.log + belief_state_*.json on each
GET — endpoint is pull-based, no daemon polling. Each browser refresh re-reads
fresh.

Endpoints:
  GET /                — index.html (the live tab)
  GET /api/traders_live — JSON snapshot
"""
from __future__ import annotations
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

ROOT = Path("/vaults/nvme0/qsb_tower_v1")
WEB = ROOT / "web/traders_live"
LOGDIR = ROOT / "logs/intelligence"
TICK_STREAMS = {
    "binance": ROOT / "data/registries/qsb_binance_tick_stream.jsonl",
    "oanda":   ROOT / "data/registries/qsb_oanda_tick_stream.jsonl",
    "alpaca":  ROOT / "data/registries/qsb_alpaca_tick_stream.jsonl",
}
TAIL_BYTES = 65536   # ~400 ticks per venue (need wider coverage for low-vol pairs)
_PRICE_CACHE = {"ts": 0.0, "prices": {}}
PRICE_CACHE_TTL = 1.5  # seconds — refresh latest-price view per request
BELIEFDIR = ROOT / "data/registries/cognitive"
ALPACA_ENV = ROOT / "floors/floor_28_security_department/vault/.env.alpaca_paper"

TRADERS = ["btc", "eth", "bnb",                                    # binance
            "eur", "gbp", "jpy", "aud", "chf", "eurgbp",             # oanda fx
            "xau", "xag", "wti", "bco",                              # oanda metals+oil
            "spx", "nas", "dow", "natgas",                           # oanda indices+gas
            "spy", "aapl", "qqq", "tsla", "nvda", "msft",            # alpaca tech-heavy
            "dia", "xlf", "gld", "coin", "iwm"]                      # alpaca diversify
VENUE_BY_TRADER = {
    "btc": "binance", "eth": "binance", "bnb": "binance",
    "eur": "oanda", "gbp": "oanda", "jpy": "oanda",
    "aud": "oanda", "chf": "oanda", "eurgbp": "oanda",
    "xau": "oanda", "xag": "oanda", "wti": "oanda", "bco": "oanda",
    "spx": "oanda", "nas": "oanda", "dow": "oanda", "natgas": "oanda",
    "spy": "alpaca", "aapl": "alpaca", "qqq": "alpaca",
    "tsla": "alpaca", "nvda": "alpaca", "msft": "alpaca",
    "dia": "alpaca", "xlf": "alpaca", "gld": "alpaca",
    "coin": "alpaca", "iwm": "alpaca",
    # 2026-06-23 expansion (Wren+Hermes picks)
    "de30": "oanda", "jp225": "oanda", "us10y": "oanda",
    "uk10y": "oanda", "xcu": "oanda", "wheat": "oanda",
    "sol": "binance", "ada": "binance", "xrp": "binance",
    "dot": "binance", "avax": "binance", "link": "binance",
}


def scrape_logs() -> dict:
    """Read all trader logs + belief files, build the snapshot.

    Auto-discovers trader_*.log files so Phase 3 strategy traders
    (belief_driven_btc_momentum etc) appear without TRADERS-list edits.
    """
    events = []
    by_trader = {}
    open_pos = {}

    # Discover all trader logs
    log_files = sorted(LOGDIR.glob("trader_*.log"))
    for f in log_files:
        # trader_btc.log -> "btc"; trader_btc_momentum.log -> "btc_momentum"
        w = f.stem.replace("trader_", "")
        text = f.read_text()
        d = by_trader.setdefault(w.upper(), {
            "trader": w.upper(), "opens": 0, "closes": 0,
            "wins": 0, "losses": 0, "pnl": 0.0,
        })

        for line in text.splitlines():
            # OPEN @ <price> qty=<n> [tail]
            # Tail varies: "(×<x>)" (legacy), "(REAL)" (broker integration),
            # "(SIM <reason>)" (broker rejected/disabled), or "(REAL) — ensemble_2/3"
            # Match the LEADING shape, ignore tail.
            m = re.search(
                r"\[belief_driven_(\w+)\] OPEN @ ([\d.]+) qty=([\d.]+)",
                line)
            if m:
                trader = m.group(1).upper()
                price = float(m.group(2))
                qty = float(m.group(3))
                # Extract size_mult if present in tail (×N pattern), default 1.0
                sm = re.search(r"×([\d.]+)", line)
                size_mult = float(sm.group(1)) if sm else 1.0
                # Mark REAL/SIM from broker integration
                is_real = "(REAL)" in line
                events.append({
                    "action": "OPEN", "side": "BUY", "trader": trader,
                    "price": price, "qty": qty, "size_mult": size_mult,
                    "is_real": is_real,
                })
                d["opens"] += 1
                open_pos[trader] = {
                    "trader": trader, "side": "BUY",
                    "entry_px": price,
                    "qty": qty, "size_mult": size_mult,
                    "notional": price * qty,
                }
                continue
            m = re.search(
                r"\[belief_driven_(\w+)\] CLOSE @ ([\d.]+) pnl=([-\d.]+) won=(True|False) \(([^)]+)\)",
                line)
            if m:
                trader = m.group(1).upper()
                price = float(m.group(2))
                pnl = float(m.group(3))
                won = m.group(4) == "True"
                reason = re.sub(r"_held_\d+s$", "", m.group(5))
                # 2026-06-27: CLOSE events also need is_real flag (was OPEN-only).
                # Trader prints "[REAL]" / "[SIM_was_real]" / "[SIM]" marker at line end.
                is_real_close = "[REAL]" in line
                events.append({
                    "action": "CLOSE", "side": "SELL", "trader": trader,
                    "price": price, "pnl": pnl, "won": won, "reason": reason,
                    "is_real": is_real_close,
                })
                d["closes"] += 1
                d["pnl"] += pnl
                if won:
                    d["wins"] += 1
                else:
                    d["losses"] += 1
                open_pos.pop(trader, None)

    per_trader = sorted(by_trader.values(), key=lambda x: -x["opens"])

    # Decorate open positions with live unrealized PnL using latest tick price.
    # Map TRADER short-name → instrument so we can lookup price.
    # The trader short-name appears in the log filename; instrument was extracted
    # from the trader's runtime args. We map via VENUE_BY_TRADER + a lookup table.
    inst_by_trader = {
        "btc": "BTCUSDT", "eth": "ETHUSDT", "bnb": "BNBUSDT",
        "eur": "EUR_USD", "gbp": "GBP_USD", "jpy": "USD_JPY",
        "aud": "AUD_USD", "chf": "USD_CHF", "eurgbp": "EUR_GBP",
        "xau": "XAU_USD", "xag": "XAG_USD", "wti": "WTICO_USD", "bco": "BCO_USD",
        "spx": "SPX500_USD", "nas": "NAS100_USD", "dow": "US30_USD",
        "natgas": "NATGAS_USD",
        "spy": "SPY", "aapl": "AAPL", "qqq": "QQQ",
        "tsla": "TSLA", "nvda": "NVDA", "msft": "MSFT",
        "dia": "DIA", "xlf": "XLF", "gld": "GLD", "coin": "COIN", "iwm": "IWM",
        # 2026-06-23 expansion
        "de30": "DE30_EUR", "jp225": "JP225_USD", "us10y": "USB10Y_USD",
        "uk10y": "UK10YB_GBP", "xcu": "XCU_USD", "wheat": "WHEAT_USD",
        "sol": "SOLUSDT", "ada": "ADAUSDT", "xrp": "XRPUSDT",
        "dot": "DOTUSDT", "avax": "AVAXUSDT", "link": "LINKUSDT",
    }
    prices = latest_prices()
    positions = []
    for trader_name, p in open_pos.items():
        key = trader_name.lower().split("_")[0]
        inst = inst_by_trader.get(key)
        live_price = prices.get(inst) if inst else None
        if live_price is not None:
            p["live_price"] = live_price
            p["unrealized_pnl"] = (live_price - p["entry_px"]) * p["qty"]
            p["unrealized_pct"] = ((live_price - p["entry_px"]) / p["entry_px"]) * 100 if p["entry_px"] else 0.0
        else:
            p["live_price"] = None
            p["unrealized_pnl"] = None
            p["unrealized_pct"] = None
        positions.append(p)
    positions.sort(key=lambda x: x["trader"])

    beliefs = []
    for f in sorted(BELIEFDIR.glob("belief_state_belief_driven_*.json")):
        try:
            b = json.loads(f.read_text())
        except Exception:
            continue
        name = f.stem.replace("belief_state_belief_driven_", "").upper()
        beliefs.append({
            "trader": name,
            "n_trades": b["strategy_fitness"]["n_trades"],
            "win_rate": b["strategy_fitness"]["win_rate"],
            "expectancy": b["strategy_fitness"]["expectancy"],
            "regime_confidence": b["regime"]["regime_confidence"],
            "ticks_seen": b["stream_evidence"]["ticks_seen"],
        })

    # group per_trader rows by venue. Use the SHORT-name prefix to map
    # (so "BTC_MOMENTUM" → venue from "btc" prefix lookup).
    per_trader_by_venue = {"oanda": [], "alpaca": [], "binance": []}
    for r in per_trader:
        key = r["trader"].lower().split("_")[0]  # btc_momentum → btc
        v = VENUE_BY_TRADER.get(key, "binance")
        per_trader_by_venue[v].append(r)

    return {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "events": events,
        "open_positions": positions,
        "per_trader": per_trader,
        "per_trader_by_venue": per_trader_by_venue,
        "beliefs": beliefs,
        "venue_health": venue_health(),
        "broker_oanda": broker_oanda(),
        "broker_alpaca": broker_alpaca(),
        "broker_live_positions": broker_live_positions(),
        "bus_pnl": bus_pnl_state(),
        "health": health_state(),
        "chart_series": chart_series(),
        "tick_rates": tick_rates(),
        "bus_journal": bus_journal_tail(),
        "throttle_state": throttle_state(),
        "worker_cards": worker_cards(),
        "performance_lens": performance_lens(),
        "ensemble_state": ensemble_state(),
        "peer_fusions": peer_fusions_recent(),
        "pnl_by_strategy": pnl_by_strategy(),
        "team_chat": team_chat_recent(),
        "convergence": convergence_view(),
        "trader_chat": trader_chat_recent(),    # 2026-06-26 — Ross "new dash"
        "manager_chat": manager_chat_recent(),  # surface manager broadcasts when published
        "min_profit_gate": min_profit_gate_counts(),  # 2026-06-27 Ross £1-gate counter
    }


def min_profit_gate_counts() -> dict:
    """Count recent CLOSE_HELD entries (£1 gate triggered) + timeout closes per
    venue. Reads pot file for UNIQUE open positions (Ross 2026-06-27: was counting
    log lines, inflated to 150+; now counts unique positions in tracker)."""
    import collections
    out = {"total_held": 0, "by_venue": {"oanda":0, "alpaca":0, "binance":0},
           "timeout_closes_today": 0, "samples": []}
    OANDA_TOK = ("gbp","eur","jpy","aud","chf","eurgbp","xau","xag","wti","bco",
                 "spx","nas","dow","de30","jp225","natgas","wheat","xcu","us10y","uk10y")
    ALPACA_TOK = ("spy","aapl","qqq","tsla","nvda","msft","dia","xlf","gld","coin","iwm")
    today_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # UNIQUE positions from pot file (truth) — not log events
    pot_path = ROOT / "data/registries/qsb_portfolio_pot.json"
    if pot_path.exists():
        try:
            pot = json.loads(pot_path.read_text())
            for k, v in pot.get("open_positions", {}).items():
                inst = (v.get("instrument") or "").upper()
                # Classify venue by instrument shape
                if "USDT" in inst or "USDC" in inst or "BTC" in inst or "ETH" in inst:
                    venue = "binance"
                elif inst in ("SPY","AAPL","QQQ","TSLA","NVDA","MSFT","DIA","XLF","GLD","COIN","IWM"):
                    venue = "alpaca"
                else:
                    venue = "oanda"
                out["total_held"] += 1
                out["by_venue"][venue] = out["by_venue"].get(venue, 0) + 1
                if len(out["samples"]) < 6:
                    out["samples"].append({
                        "worker": k,
                        "pnl_est_gbp": float(v.get("notional_gbp") or 0),
                        "age_secs": None,
                    })
        except Exception as e:
            out["pot_read_err"] = str(e)[:120]
    # timeout closes today: count log events for forced-close
    samples_seen = set()
    for f in sorted(LOGDIR.glob("trader_*.log")):
        if (time.time() - f.stat().st_mtime) > 600:
            continue
        try:
            text = f.read_text().splitlines()[-200:]
        except Exception:
            continue
        for line in text:
            if "min_profit_gate_timeout" in line and today_stamp in line:
                out["timeout_closes_today"] += 1
    return out


def trader_chat_recent(limit: int = 40) -> list[dict]:
    """2026-06-26 — surface qsb_trader_chat_board.jsonl into API.
    Workers post lessons + observations to this board. Until 2026-06-21 had 487
    entries; should grow as trade-board hook fires per close."""
    p = ROOT / "data/registries/qsb_trader_chat_board.jsonl"
    if not p.exists():
        return []
    try:
        size = p.stat().st_size
        with open(p, "rb") as fh:
            fh.seek(max(0, size - 64000))
            tail = fh.read().decode("utf-8", errors="ignore")
    except Exception:
        return []
    out = []
    for ln in tail.split("\n")[1:]:
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
            out.append({
                "ts": (r.get("ts") or r.get("timestamp",""))[:19],
                "worker": r.get("worker_id") or r.get("worker") or "?",
                "side": r.get("side",""),
                "instrument": r.get("instrument",""),
                "msg": (r.get("message") or r.get("msg") or r.get("text") or
                          r.get("note") or json.dumps(r, default=str)[:80])[:140],
                "pnl": r.get("pnl"),
            })
        except Exception:
            pass
    return out[-limit:]


def manager_chat_recent(limit: int = 20) -> list[dict]:
    """2026-06-26 — surface manager.broadcast events from bus journal.
    Empty until qsb_trader_manager.py is updated to publish manager.broadcast."""
    out = []
    for jpath in [BUS_JOURNAL.with_suffix(BUS_JOURNAL.suffix + ".1"), BUS_JOURNAL]:
        if not jpath.exists():
            continue
        try:
            size = jpath.stat().st_size
            with open(jpath, "rb") as fh:
                fh.seek(max(0, size - 64000))
                tail = fh.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        for ln in tail.split("\n")[1:]:
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
                if r.get("name") == "manager.broadcast":
                    p = r.get("payload", {}) or {}
                    out.append({
                        "ts": r.get("ts","")[:19],
                        "level": p.get("level","info"),
                        "msg": p.get("msg","")[:140],
                        "target": p.get("target",""),
                    })
            except Exception:
                pass
    return out[-limit:]


def convergence_view() -> list[dict]:
    """2026-06-25 (Ross "yes team !!!!!") — convergence-gate status per worker.
    Reads belief_state files directly, runs convergence_gate() against each.
    Surfaces which orthogonal dimensions agree per worker. The cryptoteknikal_id
    TikTok / roman-rr trading-skills approach visualized."""
    try:
        sys.path.insert(0, str(ROOT / "tools"))
        from belief_updater_math import (
            convergence_gate, dim_regime, dim_trend, dim_volatility, dim_cross_asset,
        )
    except Exception:
        return []
    # Currency lookup (mirrors qsb_ensemble_coordinator._CCY_OF)
    CCY_OF = {
        "EUR_USD": ["EUR","USD"], "GBP_USD": ["GBP","USD"], "USD_JPY": ["USD","JPY"],
        "AUD_USD": ["AUD","USD"], "USD_CHF": ["USD","CHF"], "EUR_GBP": ["EUR","GBP"],
        "BTCUSDT": ["BTC","USDT"], "ETHUSDT": ["ETH","USDT"], "BNBUSDT": ["BNB","USDT"],
        "SOLUSDT": ["SOL","USDT"], "ADAUSDT": ["ADA","USDT"], "XRPUSDT": ["XRP","USDT"],
        "SPY":["USD"], "AAPL":["USD"], "QQQ":["USD"], "TSLA":["USD"],
        "NVDA":["USD"], "MSFT":["USD"], "DIA":["USD"], "XLF":["USD"],
        "GLD":["USD"], "COIN":["USD"], "IWM":["USD"],
    }
    # Load all beliefs into a map for cheap peer lookup
    all_beliefs = {}
    for f in BELIEFDIR.glob("belief_state_*.json"):
        if "__" not in f.stem:
            continue
        try:
            all_beliefs[f.stem] = json.loads(f.read_text())
        except Exception:
            continue
    out = []
    for name, belief in all_beliefs.items():
        # filename format: belief_state_<worker_id>__<INSTRUMENT>
        parts = name.replace("belief_state_", "").rsplit("__", 1)
        if len(parts) != 2:
            continue
        worker_id, instrument = parts
        # Find peers sharing a currency
        my_ccys = CCY_OF.get(instrument, [])
        peers = []
        if my_ccys:
            for pname, pbelief in all_beliefs.items():
                if pname == name:
                    continue
                pinst = pname.rsplit("__", 1)[-1] if "__" in pname else ""
                p_ccys = CCY_OF.get(pinst, [])
                if any(c in p_ccys for c in my_ccys):
                    peers.append(pbelief)
                if len(peers) >= 6:
                    break
        # Run gate
        c_ok, c_reason, c_dims = convergence_gate(belief, peers, side="BUY",
                                                    min_dims=3)
        # Per-dim detail for failed dims
        dims_failed = []
        regime_ok, regime_r = dim_regime(belief)
        if not regime_ok:
            dims_failed.append({"name": "regime", "reason": regime_r})
        trend_ok, trend_r = dim_trend(belief, side="BUY")
        if not trend_ok:
            dims_failed.append({"name": "trend", "reason": trend_r})
        vol_ok, vol_r = dim_volatility(belief)
        if not vol_ok:
            dims_failed.append({"name": "volatility", "reason": vol_r})
        cross_ok, cross_r = dim_cross_asset(belief, peers, side="BUY")
        if not cross_ok:
            dims_failed.append({"name": "cross_asset", "reason": cross_r})
        score_pct = int(round(len(c_dims) / 4 * 100))
        out.append({
            "worker_id": worker_id,
            "instrument": instrument,
            "side": "BUY",
            "ok": c_ok,
            "dims_passed": c_dims,
            "dims_failed": dims_failed,
            "peer_count": len(peers),
            "min_dims": 3,
            "score_pct": score_pct,
            "reason": c_reason,
        })
    # Sort: firing first, then by score
    out.sort(key=lambda x: (not x["ok"], -x["score_pct"]))
    return out


def team_chat_recent(limit: int = 30) -> list[dict]:
    """Wren team-chat topic — read team.chat.* events.
    Bus journal rotates at 1000 lines (~30s with current tick volume), so
    we ALSO persist team.chat to a dedicated jsonl that never rotates."""
    persist = ROOT / "data/registries/qsb_team_chat_history.jsonl"
    out = []
    # Read persisted history first (authoritative)
    if persist.exists():
        try:
            size = persist.stat().st_size
            with open(persist, "rb") as fh:
                fh.seek(max(0, size - 32000))
                tail = fh.read().decode("utf-8", errors="ignore")
            for ln in tail.split("\n")[1:]:
                if not ln.strip():
                    continue
                try:
                    r = json.loads(ln)
                except Exception:
                    continue
                out.append(r)
        except Exception:
            pass
    # Also scan recent bus journal (catches anything not yet persisted)
    for jpath in [BUS_JOURNAL.with_suffix(BUS_JOURNAL.suffix + ".1"), BUS_JOURNAL]:
        if not jpath.exists():
            continue
        try:
            size = jpath.stat().st_size
            with open(jpath, "rb") as fh:
                fh.seek(max(0, size - 64000))
                tail = fh.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        for ln in tail.split("\n")[1:]:
            if not ln.strip():
                continue
            try:
                r = json.loads(ln)
            except Exception:
                continue
            name = r.get("name", "")
            if not name.startswith("team.chat."):
                continue
            p = r.get("payload", {}) or {}
            row = {
                "ts": (r.get("ts") or "")[:19],
                "topic": name,
                "worker": (p.get("worker_id") or "?").replace("belief_driven_", ""),
                "instrument": p.get("instrument", ""),
                "venue": p.get("venue", ""),
                "message": p.get("message", ""),
            }
            # Dedup by ts+worker+message
            key = (row["ts"], row["worker"], row["message"])
            if not any((r2.get("ts"), r2.get("worker"), r2.get("message")) == key for r2 in out):
                out.append(row)
                # Append to persistence
                with open(persist, "a") as fh:
                    fh.write(json.dumps(row) + "\n")
    return out[-limit:]


# ─── dashboard v7 — close 7 gaps (team sign-off + Ross all7) 2026-06-23 ─────

def ensemble_state() -> list[dict]:
    """Gap (2): ensemble view. Read ensemble logs for vote outcomes."""
    out = []
    files = sorted(LOGDIR.glob("trader_ensemble_*.log"))
    for f in files:
        name = f.stem.replace("trader_ensemble_", "").upper()
        try:
            size = f.stat().st_size
            with open(f, "rb") as fh:
                fh.seek(max(0, size - 8000))
                tail = fh.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        # Last ensemble vote outcome
        opens = closes = vetoes = 0
        last_vote = None
        for line in tail.split("\n"):
            if " OPEN @ " in line and "ensemble" in line:
                opens += 1
                m = re.search(r"ensemble_(\d)/(\d) \(([^)]+)\)", line)
                if m:
                    last_vote = {"voted": int(m.group(1)), "total": int(m.group(2)),
                                  "strategies": m.group(3).split(",")}
            elif " CLOSE @ " in line and "ensemble" in line:
                closes += 1
            elif "veto" in line.lower():
                vetoes += 1
        try:
            mtime = f.stat().st_mtime
            age_s = max(0, time.time() - mtime)
        except Exception:
            age_s = 1e9
        out.append({
            "name": name, "opens": opens, "closes": closes, "vetoes": vetoes,
            "last_vote": last_vote, "active": age_s < 60, "age_s": round(age_s, 1),
        })
    out.sort(key=lambda x: -x["opens"])
    return out[:30]


def peer_fusions_recent(limit: int = 20) -> list[dict]:
    """Gap (3): peer-fusion ticker. Tail bus journal for peer.belief.* events."""
    if not BUS_JOURNAL.exists():
        return []
    out = []
    try:
        size = BUS_JOURNAL.stat().st_size
        with open(BUS_JOURNAL, "rb") as fh:
            fh.seek(max(0, size - 64000))
            tail = fh.read().decode("utf-8", errors="ignore")
    except Exception:
        return []
    for ln in tail.split("\n")[1:]:
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        name = r.get("name", "")
        if not name.startswith("peer."):
            continue
        p = r.get("payload", {}) or {}
        out.append({
            "ts": r.get("ts", "")[:19],
            "kind": name,
            "from_worker": p.get("from_worker_id", p.get("peer_wid", "?")).replace("belief_driven_", ""),
            "to_worker": p.get("worker_id", "?").replace("belief_driven_", ""),
            "instrument": p.get("instrument", ""),
            "summary": (f"wr={p.get('win_rate','?')}" if "win_rate" in p
                         else json.dumps(p, default=str)[:80]),
        })
    return out[-limit:]


def pnl_by_strategy() -> list[dict]:
    """Gap (5): PnL grouped by strategy module (baseline/momentum/mean_revert/breakout)."""
    # Heuristic: parse trader logs, detect strategy from worker_id suffix
    # (btc_momentum, eur_meanrevert, xau_breakout) — else "baseline".
    strat_stats = {"baseline": {"closes": 0, "wins": 0, "pnl": 0.0},
                    "momentum": {"closes": 0, "wins": 0, "pnl": 0.0},
                    "mean_revert": {"closes": 0, "wins": 0, "pnl": 0.0},
                    "breakout": {"closes": 0, "wins": 0, "pnl": 0.0}}
    for f in sorted(LOGDIR.glob("trader_*.log")):
        w = f.stem.replace("trader_", "")
        if w.endswith("_momentum"): strat = "momentum"
        elif w.endswith("_meanrevert"): strat = "mean_revert"
        elif w.endswith("_breakout"): strat = "breakout"
        else: strat = "baseline"
        try:
            text = f.read_text()
        except Exception:
            continue
        for line in text.splitlines():
            m = re.search(
                r"\[belief_driven_\w+\] CLOSE @ [\d.]+ pnl=([-\d.]+) won=(True|False)",
                line)
            if not m:
                continue
            strat_stats[strat]["closes"] += 1
            strat_stats[strat]["pnl"] += float(m.group(1))
            if m.group(2) == "True":
                strat_stats[strat]["wins"] += 1
    out = []
    for s, r in strat_stats.items():
        n = r["closes"]
        out.append({
            "strategy": s, "closes": n, "wins": r["wins"],
            "win_rate": round(r["wins"]/n, 3) if n else 0.0,
            "pnl": round(r["pnl"], 4),
        })
    return sorted(out, key=lambda x: -x["closes"])


# ─── dashboard v6 — Performance Lens (3-CEO integrated) 2026-06-23 ─────

def performance_lens() -> dict:
    """Top-strip with 3 sections fused from one tail read:
      LEFT  (Claude): multi-timeframe PnL 5m/30m/1h/today
      CENTER (Hermes): top-5 best closes + top-5 worst closes today
      RIGHT (Wren): risk gauges — open positions count, max drawdown today,
                     biggest single loss today.
    Source: data/registries/qsb_trader_pnl_bus_tail.jsonl"""
    out = {
        "buckets": {"5m": 0.0, "30m": 0.0, "1h": 0.0, "today": 0.0,
                     "n_5m": 0, "n_30m": 0, "n_1h": 0, "n_today": 0},
        "best": [], "worst": [],
        "risk": {"open_positions": 0, "max_drawdown_today": 0.0,
                  "biggest_loss_today": 0.0, "biggest_win_today": 0.0},
    }
    if not BUS_PNL_TAIL.exists():
        return out

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoffs = {
        "5m":  now.timestamp() - 300,
        "30m": now.timestamp() - 1800,
        "1h":  now.timestamp() - 3600,
        "today": today_start.timestamp(),
    }

    # Read full today-window (tail enough bytes for a heavy day)
    try:
        size = BUS_PNL_TAIL.stat().st_size
        with open(BUS_PNL_TAIL, "rb") as fh:
            fh.seek(max(0, size - 500_000))
            tail = fh.read().decode("utf-8", errors="ignore")
    except Exception:
        return out

    todays_closes: list[dict] = []
    for ln in tail.split("\n")[1:]:
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        ts = r.get("ts", "")
        try:
            ts_clean = ts.replace("Z", "+00:00") if "Z" in ts else ts
            t_ev = datetime.fromisoformat(ts_clean).timestamp()
        except Exception:
            continue
        if t_ev < cutoffs["today"]:
            continue
        pnl = float(r.get("pnl") or 0)
        r["_ts_epoch"] = t_ev
        r["_pnl"] = pnl
        todays_closes.append(r)
        # multi-timeframe buckets
        for key in ("5m", "30m", "1h", "today"):
            if t_ev >= cutoffs[key]:
                out["buckets"][key] += pnl
                out["buckets"][f"n_{key}"] += 1

    # round to 4dp
    for k in ("5m", "30m", "1h", "today"):
        out["buckets"][k] = round(out["buckets"][k], 4)

    # top-5 best + worst (Hermes section)
    by_pnl = sorted(todays_closes, key=lambda r: -r["_pnl"])
    out["best"] = [{"worker": r.get("worker_id", "?").replace("belief_driven_", "").upper(),
                     "instrument": r.get("instrument"), "pnl": round(r["_pnl"], 4),
                     "reason": r.get("reason"), "ts": r.get("ts", "")[:19]}
                    for r in by_pnl[:5]]
    out["worst"] = [{"worker": r.get("worker_id", "?").replace("belief_driven_", "").upper(),
                      "instrument": r.get("instrument"), "pnl": round(r["_pnl"], 4),
                      "reason": r.get("reason"), "ts": r.get("ts", "")[:19]}
                     for r in by_pnl[-5:][::-1]]

    # risk gauges (Wren section)
    # open_positions = sum across all venues from broker_live_positions snapshot
    try:
        blp = broker_live_positions()
        out["risk"]["open_positions"] = sum(len(v) for v in blp.values()
                                              if isinstance(v, list))
    except Exception:
        pass
    # max drawdown today: walk cumulative pnl through today's closes in time order
    todays_closes.sort(key=lambda r: r["_ts_epoch"])
    cum = 0.0
    peak = 0.0
    max_dd = 0.0
    for r in todays_closes:
        cum += r["_pnl"]
        if cum > peak:
            peak = cum
        dd = peak - cum
        if dd > max_dd:
            max_dd = dd
    out["risk"]["max_drawdown_today"] = round(max_dd, 4)
    out["risk"]["biggest_loss_today"] = round(min((r["_pnl"] for r in todays_closes),
                                                    default=0.0), 4)
    out["risk"]["biggest_win_today"]  = round(max((r["_pnl"] for r in todays_closes),
                                                    default=0.0), 4)
    return out


# ─── dashboard v5 — 3-CEO integrated worker cards 2026-06-23 ─────

import hashlib

TRAIT_AXES = ("warm", "fast", "analytical", "creative", "risk")
TRAIT_COLORS = ("#ff8866", "#88c0e0", "#88f0d8", "#f6c45a", "#ff5050")


def _procedural_traits(worker_id: str) -> dict:
    """Mirror src/workers/character.py — deterministic 5-axis trait vector
    from worker_id hash. Same worker_id → same vector."""
    h = hashlib.sha256(worker_id.encode()).digest()
    return {axis: h[i] % 10 for i, axis in enumerate(TRAIT_AXES)}


def _mood_from_recent(pnl_sum: float, win_rate: float, throttled: bool) -> str:
    """Compute live mood from current trader state — Claude integration pick."""
    if throttled:
        return "wound up"
    if pnl_sum > 0 and win_rate > 0.55:
        return "lit up"
    if pnl_sum > 0:
        return "glad"
    if pnl_sum < -0.5:
        return "wary"
    if win_rate < 0.30:
        return "cooled off"
    return "steady"


def _state_badge(belief_n_trades: int, belief_ticks_seen: int,
                  belief_regime_conf: float, venue: str, last_tick_age_s: float | None,
                  closes_today: int) -> tuple[str, str, str]:
    """3-CEO team rules (Wren design + Hermes/Claude rules):
       NEW / CLOSED / LOW_CONF / ACTIVE — returns (state_key, badge_text, mood)."""
    # MARKET_CLOSED: no tick > 1hr (Alpaca during pre-market, weekend, etc)
    if last_tick_age_s is not None and last_tick_age_s > 3600:
        return ("closed", "CLOSED", "patient")
    # NEW: zero trade history + low tick exposure
    if belief_n_trades < 3 and belief_ticks_seen < 50:
        return ("new", "NEW", "curious")
    # LOW_CONF: belief warmed but not confident
    if belief_regime_conf < 0.4 or belief_n_trades < 10:
        return ("low_conf", "LOW CONF", "cautious")
    # ACTIVE
    return ("active", "", "")


def _sparkline_for(instrument: str) -> list[float]:
    """Hermes pick: tick price spark-line per instrument. Returns last ~30
    mid-prices from the matching tick stream. Cached implicit via _PRICE_CACHE
    on instrument level."""
    venue = None
    for v, fpath in TICK_STREAMS.items():
        if not fpath.exists():
            continue
        # Just try all streams — instrument lookup is cheap
        try:
            size = fpath.stat().st_size
            with open(fpath, "rb") as fh:
                fh.seek(max(0, size - 50000))
                tail = fh.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        prices = []
        for ln in tail.split("\n")[1:]:
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            if d.get("instrument") != instrument:
                continue
            p = d.get("price") or d.get("mid") or d.get("bid")
            if p is None:
                continue
            try:
                prices.append(float(p))
            except Exception:
                pass
        if prices:
            return prices[-30:]
    return []


def worker_cards() -> list[dict]:
    """Integrated 3-CEO design — one card per trader with:
      avatar (Claude), mood (Claude), pulse-state (Wren), spark-line (Hermes),
      throttle ratio, recent PnL trend. Source: trader logs + tick streams +
      bus_pnl by_worker + throttle_state."""
    # Pull current throttle + bus PnL state
    ts = throttle_state()
    throttle_map = {w["worker"]: w for w in ts.get("workers", [])}
    bp = bus_pnl_state()
    by_worker = (bp.get("by_worker") or {})

    cards = []
    log_files = sorted(LOGDIR.glob("trader_*.log"))
    for f in log_files:
        w = f.stem.replace("trader_", "")
        venue = VENUE_BY_TRADER.get(w.split("_")[0], "?")
        # Map back to instrument
        inst_by_trader = {
            "btc": "BTCUSDT", "eth": "ETHUSDT", "bnb": "BNBUSDT",
            "eur": "EUR_USD", "gbp": "GBP_USD", "jpy": "USD_JPY",
            "aud": "AUD_USD", "chf": "USD_CHF", "eurgbp": "EUR_GBP",
            "xau": "XAU_USD", "xag": "XAG_USD", "wti": "WTICO_USD", "bco": "BCO_USD",
            "spx": "SPX500_USD", "nas": "NAS100_USD", "dow": "US30_USD",
            "natgas": "NATGAS_USD",
            "spy": "SPY", "aapl": "AAPL", "qqq": "QQQ",
            "tsla": "TSLA", "nvda": "NVDA", "msft": "MSFT",
            "dia": "DIA", "xlf": "XLF", "gld": "GLD", "coin": "COIN", "iwm": "IWM",
            "de30": "DE30_EUR", "jp225": "JP225_USD", "us10y": "USB10Y_USD",
            "uk10y": "UK10YB_GBP", "xcu": "XCU_USD", "wheat": "WHEAT_USD",
            "sol": "SOLUSDT", "ada": "ADAUSDT", "xrp": "XRPUSDT",
            "dot": "DOTUSDT", "avax": "AVAXUSDT", "link": "LINKUSDT",
        }
        instrument = inst_by_trader.get(w.split("_")[0], w.upper())

        worker_id = f"belief_driven_{w}"
        traits = _procedural_traits(worker_id)
        # Avatar colour from worker_id hash
        h = hashlib.sha256(worker_id.encode()).digest()
        hue = h[10] * 360 // 256

        # Bus PnL stats (only for workers that closed trades)
        bw = by_worker.get(worker_id, {})
        n_closes = bw.get("closes", 0)
        wins = bw.get("wins", 0)
        wr = wins / n_closes if n_closes else 0.0
        pnl_sum = bw.get("pnl_sum", 0.0)
        real_closes = bw.get("real_closes", 0)

        thr = throttle_map.get(w.upper(), {})
        throttled = thr.get("throttled", False)

        # Recent activity timestamp from log mtime
        try:
            mtime = f.stat().st_mtime
            age_s = max(0, time.time() - mtime)
        except Exception:
            age_s = 1e9
        active_recent = age_s < 60   # had log update in last min → pulse

        mood = _mood_from_recent(pnl_sum, wr, throttled)

        # State detection (Wren+Hermes+Claude rules)
        belief_path = BELIEFDIR / f"belief_state_belief_driven_{w}__{instrument}.json"
        b_n_trades = 0; b_ticks = 0; b_rc = 0.0
        if belief_path.exists():
            try:
                b = json.loads(belief_path.read_text())
                b_n_trades = b.get("strategy_fitness", {}).get("n_trades", 0)
                b_ticks = b.get("stream_evidence", {}).get("ticks_seen", 0)
                b_rc = b.get("regime", {}).get("regime_confidence", 0.0)
            except Exception:
                pass
        # Tick age — find newest tick for this instrument
        last_tick_age = None
        for v, fpath in TICK_STREAMS.items():
            if not fpath.exists():
                continue
            try:
                size = fpath.stat().st_size
                with open(fpath, "rb") as fh:
                    fh.seek(max(0, size - 20000))
                    tail = fh.read().decode("utf-8", errors="ignore")
                for ln in reversed(tail.split("\n")):
                    if not ln.strip() or f'"{instrument}"' not in ln:
                        continue
                    try:
                        d = json.loads(ln)
                        ts = d.get("ts") or d.get(f"{v}_time", "")
                        ts_clean = ts.replace("Z", "+00:00") if "Z" in ts else ts
                        last_tick_age = time.time() - datetime.fromisoformat(ts_clean).timestamp()
                        break
                    except Exception:
                        continue
                if last_tick_age is not None:
                    break
            except Exception:
                continue
        state_key, badge, override_mood = _state_badge(
            b_n_trades, b_ticks, b_rc, venue, last_tick_age, n_closes)
        if override_mood and state_key != "active":
            mood = override_mood   # NEW/CLOSED/LOW_CONF override the PnL-based mood

        cards.append({
            "state": state_key,
            "badge": badge,
            "worker": w.upper(),
            "venue": venue,
            "instrument": instrument,
            "traits": traits,
            "hue": hue,
            "mood": mood,
            "active": active_recent,
            "throttled": throttled,
            "throttle_ratio": thr.get("ratio", 0),
            "opens_recent": thr.get("opens_recent", 0),
            "cap": thr.get("cap", 0),
            "closes": n_closes,
            "wins": wins,
            "win_rate": round(wr, 3),
            "pnl": round(pnl_sum, 4),
            "real_closes": real_closes,
            "sparkline": _sparkline_for(instrument),
        })

    # Sort: active first, then by recent PnL desc
    cards.sort(key=lambda c: (not c["active"], -c["pnl"]))
    return cards


# ────────── new dashboard v3 functions (Wren design + Hermes order) ──────────

BUS_PNL_LATEST = ROOT / "data/registries/qsb_trader_pnl_bus_latest.json"
BUS_PNL_TAIL = ROOT / "data/registries/qsb_trader_pnl_bus_tail.jsonl"
WATCHDOG_STATE = ROOT / "data/registries/qsb_pnl_watchdog_state.json"


def bus_pnl_state() -> dict:
    """Read qsb_trader_pnl_bus_latest.json. Hermes-folded into the main endpoint
    to avoid two poll loops."""
    if not BUS_PNL_LATEST.exists():
        return {"available": False}
    try:
        return {**json.loads(BUS_PNL_LATEST.read_text()), "available": True}
    except Exception as e:
        return {"available": False, "error": str(e)[:120]}


def health_state() -> dict:
    """Heartbeat age, watchdog status, fleet pids alive. Designed to make
    silent stalls visible at a glance instead of via log dive."""
    now = time.time()
    out = {"ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "aggregator": {"heartbeat_age_s": None, "last_event_ts": None,
                           "event_count": None, "tracked_workers": None,
                           "status": "unknown"},
            "watchdog": {"status": "unknown", "stall_count": None,
                         "state_age_s": None},
            "fleet": []}

    # Aggregator heartbeat via latest payload + mtime
    if BUS_PNL_LATEST.exists():
        try:
            mt = BUS_PNL_LATEST.stat().st_mtime
            payload = json.loads(BUS_PNL_LATEST.read_text())
            age = max(0, now - mt)
            out["aggregator"]["heartbeat_age_s"] = round(age, 1)
            out["aggregator"]["last_event_ts"] = payload.get("last_event_ts")
            out["aggregator"]["event_count"] = payload.get("event_count")
            out["aggregator"]["tracked_workers"] = len(payload.get("by_worker", {}))
            out["aggregator"]["status"] = "alive" if age < 60 else "stale"
        except Exception as e:
            out["aggregator"]["status"] = f"error: {str(e)[:80]}"

    # Watchdog
    if WATCHDOG_STATE.exists():
        try:
            wd = json.loads(WATCHDOG_STATE.read_text())
            age = max(0, now - WATCHDOG_STATE.stat().st_mtime)
            out["watchdog"]["status"] = wd.get("status", "unknown")
            out["watchdog"]["stall_count"] = wd.get("stall_count", 0)
            out["watchdog"]["state_age_s"] = round(age, 1)
        except Exception:
            pass

    # Fleet pids (cheap ps probe — same pattern as session_wakeup)
    try:
        ps = subprocess.run(["ps", "-eo", "pid,cmd"], capture_output=True,
                             text=True, timeout=5).stdout
        targets = [
            ("event_bus", "qsb_event_bus.py"),
            ("belief_updater", "qsb_belief_updater.py"),
            ("regime_detector", "qsb_regime_detector.py"),
            ("oanda_stream", "qsb_f41_oanda_stream.py"),
            ("binance_stream", "qsb_f42_binance_stream.py"),
            ("alpaca_stream", "qsb_f43_alpaca_stream.py"),
            ("pnl_aggregator_bus", "qsb_trader_pnl_aggregator_bus.py"),
            ("pnl_watchdog", "qsb_pnl_watchdog.py"),
        ]
        for label, pattern in targets:
            matches = [l for l in ps.splitlines()
                        if pattern in l and "grep" not in l]
            out["fleet"].append({
                "name": label, "pattern": pattern,
                "alive": len(matches) > 0, "n_procs": len(matches),
                "pid": matches[0].strip().split()[0] if matches else None,
            })
        # Trader + ensemble counts (multi-proc fleet — just count)
        for label, pattern in (("traders", "qsb_belief_driven_trader.py"),
                                ("ensembles", "qsb_ensemble_coordinator.py"),
                                ("dashboard", "qsb_traders_live_serve.py")):
            matches = [l for l in ps.splitlines()
                        if pattern in l and "grep" not in l]
            out["fleet"].append({
                "name": label, "pattern": pattern,
                "alive": len(matches) > 0, "n_procs": len(matches),
                "pid": None,
            })
    except Exception as e:
        out["fleet_error"] = str(e)[:120]

    return out


def chart_series() -> dict:
    """Time series for PnL line chart + per-worker win-rate bars.
    Pulls from the bus aggregator's tail jsonl (already authoritative)."""
    series = {"pnl_over_time": [], "win_rate_by_worker": []}
    if not BUS_PNL_TAIL.exists():
        return series

    # Tail-read last ~200 closes for cumulative PnL series
    try:
        size = BUS_PNL_TAIL.stat().st_size
        with open(BUS_PNL_TAIL, "rb") as fh:
            fh.seek(max(0, size - 80_000))   # ~last 400 rows worth
            tail = fh.read().decode("utf-8", errors="ignore")
    except Exception:
        return series

    lines = tail.split("\n")[1:]   # drop possibly-partial first line
    rows: list[dict] = []
    for ln in lines:
        if not ln.strip():
            continue
        try:
            rows.append(json.loads(ln))
        except Exception:
            continue
    # Keep last 200 chronologically (file is append-only so already ordered)
    rows = rows[-200:]

    cum = 0.0
    for r in rows:
        cum += float(r.get("pnl") or 0)
        series["pnl_over_time"].append({"ts": r.get("ts"), "cum_pnl": round(cum, 4)})

    # Win-rate by worker — read from BUS_PNL_LATEST.by_worker (already aggregated)
    if BUS_PNL_LATEST.exists():
        try:
            payload = json.loads(BUS_PNL_LATEST.read_text())
            for worker, w in (payload.get("by_worker") or {}).items():
                n = w.get("closes", 0)
                if n < 2:   # filter cold workers
                    continue
                wins = w.get("wins", 0)
                series["win_rate_by_worker"].append({
                    "trader": worker.replace("belief_driven_", "").upper(),
                    "win_rate": round(wins / n, 3) if n else 0.0,
                    "n": n,
                    "pnl_sum": round(w.get("pnl_sum", 0), 4),
                })
            series["win_rate_by_worker"].sort(key=lambda x: -x["n"])
            series["win_rate_by_worker"] = series["win_rate_by_worker"][:20]
        except Exception:
            pass

    return series


# ─── dashboard v4 — Wren+Hermes team picks 2026-06-23 ─────────────

BUS_JOURNAL = ROOT / "data/registries/qsb_bus_journal.jsonl"


def tick_rates() -> dict:
    """Hermes pick (A): ticks/sec per venue. Tail-reads each tick stream,
    counts events in the last 10 seconds, returns rate."""
    out = {}
    window_s = 10.0
    now_t = time.time()
    for venue, fpath in TICK_STREAMS.items():
        info = {"rate_per_s": 0.0, "ticks_last_10s": 0, "last_tick_age_s": None}
        if not fpath.exists():
            out[venue] = info
            continue
        try:
            size = fpath.stat().st_size
            with open(fpath, "rb") as fh:
                fh.seek(max(0, size - 32768))   # ~last 200 ticks
                tail = fh.read().decode("utf-8", errors="ignore")
        except Exception:
            out[venue] = info
            continue
        n = 0
        last_ts_iso = None
        for ln in tail.split("\n")[1:]:
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            ts = d.get("ts") or d.get(f"{venue}_time") or ""
            last_ts_iso = ts
            # Parse iso ts; count if within window
            try:
                # iso8601 with optional fractional
                ts_clean = ts.replace("Z", "+00:00") if "Z" in ts else ts
                t_then = datetime.fromisoformat(ts_clean).timestamp()
                if (now_t - t_then) <= window_s:
                    n += 1
            except Exception:
                pass
        info["ticks_last_10s"] = n
        info["rate_per_s"] = round(n / window_s, 2)
        if last_ts_iso:
            try:
                ts_clean = last_ts_iso.replace("Z", "+00:00") if "Z" in last_ts_iso else last_ts_iso
                info["last_tick_age_s"] = round(now_t - datetime.fromisoformat(ts_clean).timestamp(), 1)
            except Exception:
                pass
        out[venue] = info
    return out


def bus_journal_tail(n: int = 40) -> list[dict]:
    """Wren pick (C): live bus event journal tail — what's happening NOW.
    Returns last N events with name + payload summary."""
    if not BUS_JOURNAL.exists():
        return []
    try:
        size = BUS_JOURNAL.stat().st_size
        with open(BUS_JOURNAL, "rb") as fh:
            fh.seek(max(0, size - 32768))
            tail = fh.read().decode("utf-8", errors="ignore")
    except Exception:
        return []
    rows = []
    for ln in tail.split("\n")[1:]:
        if not ln.strip():
            continue
        try:
            r = json.loads(ln)
        except Exception:
            continue
        payload = r.get("payload", {}) or {}
        # Compact payload — pick key fields per event type
        name = r.get("name", "?")
        summary = ""
        if name.startswith("market.tick."):
            summary = f"{payload.get('instrument','?')} @ {payload.get('mid') or payload.get('price') or payload.get('bid','?')}"
        elif name == "trade.opened" or name == "trade.closed":
            wid = payload.get("worker_id", "?").replace("belief_driven_", "")
            if name == "trade.closed":
                pnl = payload.get("pnl"); won = payload.get("won")
                summary = f"{wid} pnl={pnl} won={won} ({payload.get('reason','?')})"
            else:
                summary = f"{wid} {payload.get('side','?')} @ {payload.get('entry_px','?')}"
        elif name == "system.heartbeat.alive":
            summary = f"pid={payload.get('daemon_pid')} uptime={payload.get('uptime_s')}s rx={payload.get('rx_counter')}"
        elif name == "pnl.aggregator.heartbeat":
            summary = f"events={payload.get('event_count')} workers={payload.get('tracked_workers')}"
        elif name == "worker.escalation":
            summary = f"{payload.get('worker_id','?')} severity={payload.get('severity','?')}"
        else:
            summary = json.dumps(payload, default=str)[:80]
        rows.append({"ts": r.get("ts"), "name": name, "summary": summary})
    return rows[-n:]


def throttle_state() -> dict:
    """Per-worker hourly open count + cap (visualizes the 3-CEO throttle work).
    Counts OPEN @ lines per trader log in last RATE_WINDOW_S=3600s."""
    out = {"workers": [], "window_s": 3600,
            "caps": {"binance": 30, "oanda": 12, "alpaca": 20}}
    now_t = time.time()
    log_files = sorted(LOGDIR.glob("trader_*.log"))
    for f in log_files:
        w = f.stem.replace("trader_", "")
        venue = VENUE_BY_TRADER.get(w.split("_")[0], "?")
        cap = out["caps"].get(venue, 60)
        # Tail-read last ~50KB
        try:
            size = f.stat().st_size
            with open(f, "rb") as fh:
                fh.seek(max(0, size - 50000))
                tail = fh.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        opens_in_window = 0
        last_throttle_log = None
        for line in tail.split("\n"):
            # Look for "[2026-06-23T...] belief_driven_X connected" or OPEN @ lines
            if "OPEN @" in line and f"belief_driven_{w}" in line:
                # We don't have a timestamp on these lines, so count all in tail
                # (good enough for last ~50KB which covers recent activity)
                opens_in_window += 1
            elif "self_throttle" in line:
                last_throttle_log = line[-80:].strip()
        # Cap at window — last 60min approximation by limiting to cap*2
        opens_in_window = min(opens_in_window, cap * 4)  # noise guard
        ratio = opens_in_window / cap if cap > 0 else 0
        out["workers"].append({
            "worker": w.upper(),
            "venue": venue,
            "opens_recent": opens_in_window,
            "cap": cap,
            "ratio": round(ratio, 2),
            "throttled": bool(last_throttle_log),
        })
    out["workers"].sort(key=lambda x: -x["ratio"])
    return out


def trader_detail(name: str) -> dict:
    """Drilldown for one trader: belief + last 10 trades + open position.
    Hermes-warned: KEEP STRICTLY TO THIS — no control surfaces."""
    name = re.sub(r"[^A-Za-z0-9_]", "", name).lower()
    out = {"trader": name.upper(), "belief": None, "last_trades": [],
            "open_position": None, "error": None}

    # Belief state — filename pattern is belief_state_belief_driven_{name}__{INSTRUMENT}.json
    matches = sorted(BELIEFDIR.glob(f"belief_state_belief_driven_{name}__*.json"))
    if not matches:
        # fallback for files without the instrument suffix
        single = BELIEFDIR / f"belief_state_belief_driven_{name}.json"
        if single.exists():
            matches = [single]
    if matches:
        try:
            out["belief"] = json.loads(matches[0].read_text())
        except Exception as e:
            out["error"] = f"belief read: {str(e)[:80]}"

    # Last 10 closes from trader log
    log_path = LOGDIR / f"trader_{name}.log"
    if log_path.exists():
        try:
            text = log_path.read_text()
            closes = []
            for line in text.splitlines():
                m = re.search(
                    r"\[belief_driven_(\w+)\] CLOSE @ ([\d.]+) pnl=([-\d.]+) won=(True|False) \(([^)]+)\)",
                    line)
                if not m:
                    continue
                closes.append({
                    "price": float(m.group(2)),
                    "pnl": float(m.group(3)),
                    "won": m.group(4) == "True",
                    "reason": re.sub(r"_held_\d+s$", "", m.group(5)),
                })
            out["last_trades"] = closes[-10:]
        except Exception as e:
            out["error"] = (out["error"] or "") + f" log: {str(e)[:80]}"

    # Open position from current scrape_logs view
    try:
        snap = scrape_logs()
        for p in snap.get("open_positions", []):
            if p.get("trader", "").lower() == name:
                out["open_position"] = p
                break
    except Exception:
        pass

    return out


def latest_prices() -> dict:
    """Tail-read each tick stream file, return {instrument: latest_price}.
    Cached for PRICE_CACHE_TTL seconds to bound IO under poll load."""
    now = time.time()
    if _PRICE_CACHE["prices"] and (now - _PRICE_CACHE["ts"]) < PRICE_CACHE_TTL:
        return _PRICE_CACHE["prices"]
    prices: dict[str, float] = {}
    for venue, fpath in TICK_STREAMS.items():
        if not fpath.exists():
            continue
        try:
            size = fpath.stat().st_size
            with open(fpath, "rb") as fh:
                fh.seek(max(0, size - TAIL_BYTES))
                tail = fh.read().decode("utf-8", errors="ignore")
        except Exception:
            continue
        # Process complete lines only
        lines = tail.split("\n")[1:]   # drop possibly-incomplete first line
        for ln in lines:
            if not ln.strip():
                continue
            try:
                d = json.loads(ln)
            except Exception:
                continue
            inst = d.get("instrument")
            if not inst:
                continue
            price = d.get("price") or d.get("mid") or d.get("bid")
            if price is None:
                continue
            prices[inst] = float(price)
    _PRICE_CACHE["ts"] = now
    _PRICE_CACHE["prices"] = prices
    return prices


_BROKER_POS_CACHE = {"ts": 0.0, "data": {}}
def broker_live_positions() -> dict:
    """Real broker open positions across OANDA practice + Alpaca paper + Binance.
    30s cache. Each list has dicts: symbol, qty, side, entry, current, unrealized_pnl."""
    now = time.time()
    if _BROKER_POS_CACHE["data"] and (now - _BROKER_POS_CACHE["ts"]) < 30:
        return _BROKER_POS_CACHE["data"]
    out = {"oanda": [], "alpaca": [], "binance": []}
    # ALPACA
    try:
        key, secret = _load_alpaca_env()
        if key and secret:
            req = urllib.request.Request(
                "https://paper-api.alpaca.markets/v2/positions",
                headers={"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret})
            with urllib.request.urlopen(req, timeout=8) as r:
                positions = json.loads(r.read())
            for p in positions:
                out["alpaca"].append({
                    "symbol": p.get("symbol"),
                    "side": p.get("side", "long").upper(),
                    "qty": float(p.get("qty", 0) or 0),
                    "entry": float(p.get("avg_entry_price", 0) or 0),
                    "current": float(p.get("current_price", 0) or 0),
                    "unrealized_pnl": float(p.get("unrealized_pl", 0) or 0),
                    "unrealized_pct": float(p.get("unrealized_plpc", 0) or 0) * 100,
                })
    except Exception as e:
        out["alpaca_error"] = str(e)[:120]
    # OANDA
    try:
        oanda_env = ROOT / "floors/floor_28_security_department/vault/.env.oanda_practice"
        if oanda_env.exists():
            env = {}
            for ln in oanda_env.read_text().splitlines():
                if "=" in ln and not ln.lstrip().startswith("#"):
                    # 2026-06-26 fix: strip "export " prefix; .env files using
                    # `export FOO=bar` format weren't being parsed (key included "export").
                    ln_clean = ln.strip()
                    if ln_clean.startswith("export "):
                        ln_clean = ln_clean[7:]
                    k, v = ln_clean.split("=", 1)
                    env[k.strip()] = v.strip().strip("\"'")
            # 2026-06-26 fix: env file uses OANDA_API_TOKEN/OANDA_ACCOUNT_ID names,
            # accept both naming conventions so probe doesn't return empty.
            tok = env.get("OANDA_PRACTICE_TOKEN") or env.get("OANDA_API_TOKEN")
            acct = env.get("OANDA_PRACTICE_ACCOUNT_ID") or env.get("OANDA_ACCOUNT_ID")
            if tok and acct:
                req = urllib.request.Request(
                    f"https://api-fxpractice.oanda.com/v3/accounts/{acct}/openTrades",
                    headers={"Authorization": f"Bearer {tok}"})
                with urllib.request.urlopen(req, timeout=8) as r:
                    trades = json.loads(r.read()).get("trades", [])
                for t in trades:
                    units = float(t.get("currentUnits", 0))
                    out["oanda"].append({
                        "symbol": t.get("instrument"),
                        "side": "BUY" if units > 0 else "SELL",
                        "qty": abs(units),
                        "entry": float(t.get("price", 0)),
                        "current": None,  # OANDA doesn't include current_price here
                        "unrealized_pnl": float(t.get("unrealizedPL", 0)),
                        "unrealized_pct": None,
                        "trade_id": t.get("id"),
                    })
    except Exception as e:
        out["oanda_error"] = str(e)[:120]
    # BINANCE testnet — non-zero balances of streamed instruments
    try:
        binance_env = ROOT / "floors/floor_28_security_department/vault/.env.binance_testnet"
        env = {}
        if binance_env.exists():
            for ln in binance_env.read_text().splitlines():
                if "=" in ln and not ln.startswith("#"):
                    k, v = ln.split("=", 1); env[k.strip()] = v.strip().strip("\"'")
        bkey = env.get("QSB_BINANCE_TESTNET_API_KEY")
        bsecret = env.get("QSB_BINANCE_TESTNET_API_SECRET")
        burl = (env.get("QSB_BINANCE_TESTNET_URL") or "https://testnet.binance.vision").rstrip("/")
        if bkey and bsecret:
            import hmac, hashlib
            ts_ms = int(time.time() * 1000)
            qs = f"timestamp={ts_ms}"
            sig = hmac.new(bsecret.encode(), qs.encode(), hashlib.sha256).hexdigest()
            url = f"{burl}/api/v3/account?{qs}&signature={sig}"
            req = urllib.request.Request(url, headers={"X-MBX-APIKEY": bkey})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read())
            # Streamed instruments → assets we care about
            assets_of_interest = {"BTC", "ETH", "BNB", "USDT"}
            # Get current prices for the interesting assets to compute notional
            for b in d.get("balances", []):
                asset = b.get("asset", "")
                if asset not in assets_of_interest:
                    continue
                free = float(b.get("free", 0))
                locked = float(b.get("locked", 0))
                qty = free + locked
                if qty < 1e-8:
                    continue
                # Use latest streamed price if available
                live_px = None
                if asset != "USDT":
                    live_px = latest_prices().get(asset + "USDT")
                notional = qty * (live_px if live_px else (1.0 if asset == "USDT" else 0))
                out["binance"].append({
                    "symbol": asset,
                    "side": "LONG",
                    "qty": qty,
                    "entry": None,          # spot — no entry concept, just holdings
                    "current": live_px,
                    "unrealized_pnl": 0.0,  # spot holdings have no unrealized PnL
                    "unrealized_pct": None,
                    "notional": notional,
                })
    except Exception as e:
        out["binance_error"] = str(e)[:120]
    _BROKER_POS_CACHE["ts"] = now
    _BROKER_POS_CACHE["data"] = out
    return out


def venue_health() -> list[dict]:
    """Parse the 3 stream logs for tick counts + last tick + connection status."""
    out = []
    for venue, fname in (("oanda", "f41_stream.log"),
                          ("binance", "f42_stream.log"),
                          ("alpaca", "f43_stream.log")):
        f = LOGDIR / fname
        d = {"venue": venue, "ticks_seen": 0, "last_tick": None, "connected": False}
        if f.exists():
            text = f.read_text()
            tick_lines = [l for l in text.splitlines() if "ticks" in l]
            if tick_lines:
                m = re.search(r"(\d+) ticks \(last ([^)]+)\)", tick_lines[-1])
                if m:
                    d["ticks_seen"] = int(m.group(1))
                    d["last_tick"] = m.group(2)
            # crude liveness: any "connected" in last 20 lines + file mtime recent
            d["connected"] = ("connected" in text and
                              (time.time() - f.stat().st_mtime) < 60)
        out.append(d)
    return out


_OANDA_CACHE = {"ts": 0.0, "data": None}
def broker_oanda() -> dict:
    """Read OANDA practice status via subprocess (read-only). Cache 30s to avoid
    hammering the broker / our own tool."""
    now = time.time()
    if _OANDA_CACHE["data"] and (now - _OANDA_CACHE["ts"]) < 30:
        return _OANDA_CACHE["data"]
    out = {"realized_gbp": None, "unrealized_gbp": None,
            "open_trade_count": None, "snapshot_age_s": None, "error": None}
    # 2026-06-26 fix: previous logic counted only OUR tracked workers (3 vs 23 reality).
    # Hit broker directly for ground truth — same fix as broker_live_positions().
    try:
        oanda_env = ROOT / "floors/floor_28_security_department/vault/.env.oanda_practice"
        env = {}
        if oanda_env.exists():
            for ln in oanda_env.read_text().splitlines():
                if "=" in ln and not ln.lstrip().startswith("#"):
                    ln_clean = ln.strip()
                    if ln_clean.startswith("export "): ln_clean = ln_clean[7:]
                    k, v = ln_clean.split("=", 1)
                    env[k.strip()] = v.strip().strip("\"'")
        tok = env.get("OANDA_PRACTICE_TOKEN") or env.get("OANDA_API_TOKEN")
        acct = env.get("OANDA_PRACTICE_ACCOUNT_ID") or env.get("OANDA_ACCOUNT_ID")
        if tok and acct:
            req = urllib.request.Request(
                f"https://api-fxpractice.oanda.com/v3/accounts/{acct}",
                headers={"Authorization": f"Bearer {tok}"})
            with urllib.request.urlopen(req, timeout=8) as r:
                d = json.loads(r.read()).get("account", {})
            out["realized_gbp"] = round(float(d.get("pl") or 0), 2)
            out["unrealized_gbp"] = round(float(d.get("unrealizedPL") or 0), 2)
            out["open_trade_count"] = int(d.get("openTradeCount") or 0)
            out["snapshot_age_s"] = 0
        else:
            out["error"] = "missing_oanda_token_or_account_in_vault"
    except Exception as e:
        out["error"] = str(e)[:120]
    _OANDA_CACHE["ts"] = now
    _OANDA_CACHE["data"] = out
    return out


def _load_alpaca_env() -> tuple[str, str]:
    key = secret = ""
    if ALPACA_ENV.exists():
        for line in ALPACA_ENV.read_text().splitlines():
            if line.startswith("ALPACA_API_KEY="):
                key = line.split("=", 1)[1].strip().strip("\"'")
            elif line.startswith("ALPACA_API_SECRET="):
                secret = line.split("=", 1)[1].strip().strip("\"'")
    return key, secret


_ALPACA_CACHE = {"ts": 0.0, "data": None}
def broker_alpaca() -> dict:
    """Live Alpaca paper account snapshot. Cached 30s."""
    now = time.time()
    if _ALPACA_CACHE["data"] and (now - _ALPACA_CACHE["ts"]) < 30:
        return _ALPACA_CACHE["data"]
    out = {"equity": None, "buying_power": None, "cash": None,
            "portfolio_value": None, "status": None,
            "positions_count": None, "snapshot_age_s": None, "error": None}
    try:
        key, secret = _load_alpaca_env()
        if not (key and secret):
            out["error"] = "no_paper_keys"
            _ALPACA_CACHE.update(ts=now, data=out); return out
        hdrs = {"APCA-API-KEY-ID": key, "APCA-API-SECRET-KEY": secret}
        # account
        req = urllib.request.Request("https://paper-api.alpaca.markets/v2/account", headers=hdrs)
        with urllib.request.urlopen(req, timeout=10) as r:
            d = json.loads(r.read())
        out["equity"] = float(d.get("equity", 0) or 0)
        out["buying_power"] = float(d.get("buying_power", 0) or 0)
        out["cash"] = float(d.get("cash", 0) or 0)
        out["portfolio_value"] = float(d.get("portfolio_value", 0) or 0)
        out["status"] = d.get("status")
        # positions
        req2 = urllib.request.Request("https://paper-api.alpaca.markets/v2/positions", headers=hdrs)
        with urllib.request.urlopen(req2, timeout=10) as r:
            positions = json.loads(r.read())
        out["positions_count"] = len(positions) if isinstance(positions, list) else 0
        out["snapshot_age_s"] = 0
    except Exception as e:
        out["error"] = str(e)[:120]
    _ALPACA_CACHE["ts"] = now
    _ALPACA_CACHE["data"] = out
    return out


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # 2026-06-26: belt-and-braces cache busting — operator was seeing stale
        # OANDA-no-data panels because Chrome kept old JS in memory.
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            idx = WEB / "index.html"
            if idx.exists():
                self._send(200, idx.read_bytes(), "text/html; charset=utf-8")
            else:
                self._send(500, b"index.html missing", "text/plain")
            return
        if self.path == "/api/traders_live":
            try:
                payload = json.dumps(scrape_logs()).encode("utf-8")
                self._send(200, payload, "application/json")
            except Exception as e:
                self._send(500, str(e).encode(), "text/plain")
            return
        if self.path.startswith("/api/trader_detail"):
            try:
                from urllib.parse import urlparse, parse_qs
                q = parse_qs(urlparse(self.path).query)
                name = (q.get("trader") or [""])[0]
                payload = json.dumps(trader_detail(name)).encode("utf-8")
                self._send(200, payload, "application/json")
            except Exception as e:
                self._send(500, str(e).encode(), "text/plain")
            return
        self._send(404, b"not found", "text/plain")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--port", type=int, default=8847)
    p.add_argument("--host", default="127.0.0.1")
    args = p.parse_args()
    srv = HTTPServer((args.host, args.port), Handler)
    print(f"traders_live: http://{args.host}:{args.port}/", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
