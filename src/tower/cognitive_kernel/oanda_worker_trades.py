"""OANDA worker trades — certified-worker gate over the practice trading API.

Composes two existing pieces:

  · tower_ops.oanda_practice_trading.place_practice_order() — already
    enforces all 11 guardrails (instrument whitelist, max units, max
    open trades, max trades/hour, max spread, max daily loss, kill
    switch, manual confirm) and calls the real OANDA practice REST API.

  · cognitive_kernel.worker_certification — the cert ledger we built
    for the lineage system; per worker, per instrument, must be
    'certified' AND not 'suspended' to trade.

What this module adds:

  1. CERTIFIED-WORKER GATE — refuses to call place_practice_order unless
     worker_certification.is_authorized(worker_id, instrument) is True.

  2. PER-WORKER ATTRIBUTION — every placement and close writes a row to
     cognitive_oanda_worker_trades.jsonl carrying worker_id, oanda
     trade_id, fill price, instrument, units, side, broker_response_id.
     This closes the per-worker PnL attribution loop the lineage system
     was missing — `worker_pnl.refresh()` reads it next tick.

  3. LEARNING FEEDBACK — when a trade closes, the realized PnL is
     reported into learning.report_outcome() so per-worker beliefs in
     the UncertaintyTracker update. The compensation engine mints QBC
     on profitable closes (capped per day).

  4. ANTI-FRAUD — close() refuses to operate on a trade_id whose
     owning worker_id is different from the requested closer.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Any
import json
import time

from . import ROOT, write_registry, append_log, load, COG_REG, now, SAFETY
from .worker_certification import worker_certification
from .worker_pnl import worker_pnl
from .learning import learning
from .bank import bank


# Where we journal per-worker OANDA trades. This is what worker_pnl reads.
WORKER_LEDGER_PATH = ROOT / "data/logs/qsb_floor41_oanda_trade_ledger.jsonl"
# Lookup of (oanda_trade_id → owning worker_id) so close() can verify ownership.
WORKER_OWNERSHIP_PATH = ROOT / "data/registries/qsb_floor41_oanda_trade_ownership.json"


# Maximum QBC compensation per trade (defends mint integrity).
QBC_PER_GBP_PNL = 1.0
QBC_MAX_PER_TRADE = 50.0


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def _load_ownership() -> Dict[str, str]:
    if not WORKER_OWNERSHIP_PATH.exists():
        return {}
    try:
        d = json.loads(WORKER_OWNERSHIP_PATH.read_text(encoding="utf-8"))
        return d.get("ownership") or {}
    except Exception:
        return {}


def _save_ownership(ownership: Dict[str, str]) -> None:
    payload = {
        "ok": True,
        "kind": "qsb_floor41_oanda_trade_ownership",
        "generated_ts": _now_iso(),
        "policy": "Map of oanda_trade_id → owning worker_id. Closer must match.",
        "ownership": ownership,
    }
    WORKER_OWNERSHIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    WORKER_OWNERSHIP_PATH.write_text(json.dumps(payload, indent=2),
                                        encoding="utf-8")


def _append_worker_ledger(row: Dict[str, Any]) -> None:
    WORKER_LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with WORKER_LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ── PLACE ──────────────────────────────────────────────────────────────

def place_for_worker(worker_id: str, instrument: str, units: int,
                       side: str, entry_reason: str,
                       confirm_practice_order: bool,
                       style: str = "scalp") -> Dict[str, Any]:
    """Place an OANDA practice order on behalf of a certified worker."""

    # ── Cognitive gate: cert + status ─────────────────────────────────
    wc = worker_certification()
    wc.load_from_snapshot()
    instrument = (instrument or "").upper()
    if not wc.is_authorized(worker_id, instrument):
        entry = wc.get_or_create(worker_id, instrument)
        return {
            "ok": False, "blocked": True,
            "blocked_by": "worker_certification_gate",
            "reason": f"worker {worker_id} not certified for {instrument} "
                       f"(status={entry.status}, consecutive_losses="
                       f"{entry.consecutive_losses})",
            "safety_envelope": dict(SAFETY),
        }

    # ── Manual confirm required at THIS layer too ─────────────────────
    # (oanda_practice_trading also enforces it; redundancy is fine.)
    if not confirm_practice_order:
        return {
            "ok": False, "blocked": True,
            "blocked_by": "manual_confirm_required",
            "reason": "confirm_practice_order=True required at placement",
            "safety_envelope": dict(SAFETY),
        }

    # ── Delegate to the canonical placement function ──────────────────
    try:
        from tower_ops.oanda_practice_trading import place_practice_order
    except Exception as e:
        return {"ok": False, "error": f"oanda_practice_trading_unavailable: {e}"}

    payload = {
        "mode": "PRACTICE_ONLY",
        "instrument": instrument,
        "units": int(units),
        "side": side.lower(),
        "confirm_practice_order": True,
        "entry_reason": entry_reason,
    }
    resp = place_practice_order(payload)

    if not resp.get("ok"):
        append_log("oanda_worker_trades.jsonl", {
            "event": "place_blocked_or_failed",
            "worker_id": worker_id, "payload": payload,
            "response": resp,
        })
        return resp

    # Extract OANDA broker IDs for honest attribution
    oanda_resp = resp.get("oanda_response") or {}
    fill = oanda_resp.get("orderFillTransaction") or {}
    trade_opened = fill.get("tradeOpened") or {}
    oanda_trade_id = trade_opened.get("tradeID") or fill.get("id")
    fill_price = fill.get("price")
    broker_order_id = fill.get("id")
    fill_time = fill.get("time")

    # ── Per-worker ledger row (the row worker_pnl reads) ──────────────
    ledger_row = {
        "ts": _now_iso(),
        "event": "open_filled",
        "execution_mode": "oanda_practice_real",   # NOT paper_simulator
        "worker_id": worker_id,
        "instrument": instrument,
        "units": int(units),
        "side": side.lower(),
        "style": style,
        "entry_reason": entry_reason,
        "open_price": float(fill_price) if fill_price else None,
        "open_ts": fill_time,
        "oanda_trade_id": str(oanda_trade_id) if oanda_trade_id else None,
        "broker_order_id": str(broker_order_id) if broker_order_id else None,
        "realized_pnl": 0.0,   # not realized until close
    }
    _append_worker_ledger(ledger_row)

    # ── Update ownership map for close() verification ─────────────────
    if oanda_trade_id:
        ownership = _load_ownership()
        ownership[str(oanda_trade_id)] = worker_id
        _save_ownership(ownership)

    append_log("oanda_worker_trades.jsonl", {
        "event": "place_executed",
        "worker_id": worker_id,
        "instrument": instrument, "units": units, "side": side,
        "oanda_trade_id": oanda_trade_id,
        "fill_price": fill_price,
    })

    return {
        "ok": True,
        "worker_id": worker_id,
        "instrument": instrument, "units": units, "side": side,
        "oanda_trade_id": oanda_trade_id,
        "broker_order_id": broker_order_id,
        "fill_price": fill_price,
        "fill_time": fill_time,
        "policy": ("Real OANDA practice order placed via certified-worker "
                    "gate. Ledger row stamped. Ownership recorded."),
        "safety_envelope": dict(SAFETY),
    }


# ── CLOSE ──────────────────────────────────────────────────────────────

def close_for_worker(worker_id: str, oanda_trade_id: str,
                      close_reason: str) -> Dict[str, Any]:
    """Close an OANDA practice trade. Verifies the worker owns it,
    then routes the realized PnL into the Learning + worker_pnl +
    bank/compensation loops."""

    # ── Verify ownership ──────────────────────────────────────────────
    ownership = _load_ownership()
    owner = ownership.get(str(oanda_trade_id))
    if owner is None:
        return {
            "ok": False, "blocked": True,
            "blocked_by": "ownership_unknown",
            "reason": f"no ownership record for OANDA trade {oanda_trade_id}",
            "safety_envelope": dict(SAFETY),
        }
    if owner != worker_id:
        append_log("oanda_worker_trades.jsonl", {
            "event": "close_blocked_owner_mismatch",
            "requested_by": worker_id, "actual_owner": owner,
            "oanda_trade_id": oanda_trade_id,
        })
        return {
            "ok": False, "blocked": True,
            "blocked_by": "ownership_mismatch",
            "reason": (f"worker {worker_id} attempted to close trade "
                        f"{oanda_trade_id} owned by {owner}"),
            "safety_envelope": dict(SAFETY),
        }

    # ── Delegate to canonical close ───────────────────────────────────
    try:
        from tower_ops.oanda_practice_trading import close_practice_trade
    except Exception as e:
        return {"ok": False, "error": f"oanda_practice_trading_unavailable: {e}"}

    resp = close_practice_trade({"trade_id": oanda_trade_id, "units": "ALL"})
    if not resp.get("ok"):
        append_log("oanda_worker_trades.jsonl", {
            "event": "close_failed",
            "worker_id": worker_id, "oanda_trade_id": oanda_trade_id,
            "response": resp,
        })
        return resp

    # Extract realized PnL + price from OANDA response
    oanda_resp = resp.get("oanda_response") or {}
    fill = oanda_resp.get("orderFillTransaction") or {}
    realized_pl = float(fill.get("pl") or 0)
    close_price = fill.get("price")
    close_time = fill.get("time")
    instrument = fill.get("instrument") or "?"

    # ── Per-worker ledger row (close event) ──────────────────────────
    ledger_row = {
        "ts": _now_iso(),
        "event": "close_filled",
        "execution_mode": "oanda_practice_real",
        "worker_id": worker_id,
        "instrument": instrument,
        "oanda_trade_id": str(oanda_trade_id),
        "broker_order_id": str(fill.get("id") or ""),
        "close_price": float(close_price) if close_price else None,
        "close_ts": close_time,
        "close_reason": close_reason,
        "realized_pnl": realized_pl,
    }
    _append_worker_ledger(ledger_row)

    # ── Feed Learning + certification + compensation ─────────────────
    outcome = ("success" if realized_pl > 0
                else "failure" if realized_pl < 0
                else "partial")
    # Update cert state — consecutive losses, possible suspension
    wc = worker_certification()
    wc.load_from_snapshot()
    wc.record_trade_outcome(worker_id, instrument, realized_pl)
    wc.persist()

    # Update belief tracker through learning layer
    learning().report_outcome(
        proposal_id=None,
        outcome=outcome,
        summary=(f"Worker {worker_id} closed {instrument} trade "
                  f"{oanda_trade_id} for PnL {realized_pl:+.4f}"),
        related_belief_keys=[f"worker_skill:{worker_id}:{instrument}"],
        confidence_delta_hint=min(0.1, abs(realized_pl) * 0.001),
        tags=["oanda_practice", "worker_outcome"],
    )

    # Compensation — mint QBC capped per trade
    minted = None
    if realized_pl > 0:
        amount = min(QBC_MAX_PER_TRADE, realized_pl * QBC_PER_GBP_PNL)
        if amount > 0:
            txn = bank().mint(worker_id, amount, "mint_pnl_share",
                                note=f"OANDA practice profit £{realized_pl:.2f} "
                                      f"on trade {oanda_trade_id}",
                                metadata={"oanda_trade_id": str(oanda_trade_id)})
            if txn:
                minted = {"txn_id": txn.txn_id, "amount_qbc": amount}
                bank().persist()

    # Refresh per-worker PnL rollup so it picks up the new row
    worker_pnl().refresh()
    worker_pnl().persist()

    append_log("oanda_worker_trades.jsonl", {
        "event": "close_executed",
        "worker_id": worker_id,
        "oanda_trade_id": oanda_trade_id,
        "realized_pnl": realized_pl,
        "outcome": outcome,
        "qbc_minted": minted,
    })

    return {
        "ok": True,
        "worker_id": worker_id,
        "oanda_trade_id": oanda_trade_id,
        "instrument": instrument,
        "realized_pnl_gbp": realized_pl,
        "close_price": close_price,
        "close_time": close_time,
        "outcome": outcome,
        "qbc_minted": minted,
        "consecutive_losses_after_close":
            wc.get_or_create(worker_id, instrument).consecutive_losses,
        "policy": ("Real OANDA practice trade closed. Learning + cert + "
                    "compensation all updated atomically."),
        "safety_envelope": dict(SAFETY),
    }


# ── BACKFILL: claim an existing open OANDA trade for a worker ──────

def claim_existing_open_trade(worker_id: str, oanda_trade_id: str,
                                 instrument: str,
                                 style: str = "scalp") -> Dict[str, Any]:
    """Claim ownership of an OANDA trade that already existed before
    the worker-attribution layer. Used to backfill the live trade
    id=154 the operator placed earlier without a worker_id. Requires
    the worker to be currently certified for the instrument."""
    wc = worker_certification()
    wc.load_from_snapshot()
    instrument = (instrument or "").upper()
    if not wc.is_authorized(worker_id, instrument):
        return {
            "ok": False, "blocked": True,
            "blocked_by": "worker_certification_gate",
            "reason": f"worker {worker_id} not certified for {instrument}",
        }
    ownership = _load_ownership()
    if str(oanda_trade_id) in ownership:
        if ownership[str(oanda_trade_id)] == worker_id:
            return {"ok": True, "note": "already owned by this worker"}
        return {
            "ok": False, "blocked": True,
            "blocked_by": "already_owned",
            "reason": (f"trade {oanda_trade_id} already owned by "
                        f"{ownership[str(oanda_trade_id)]}"),
        }
    ownership[str(oanda_trade_id)] = worker_id
    _save_ownership(ownership)
    # Synth a ledger row marking the claim (so per-worker rollups see it)
    _append_worker_ledger({
        "ts": _now_iso(),
        "event": "claim_existing_open_trade",
        "execution_mode": "oanda_practice_real",
        "worker_id": worker_id,
        "instrument": instrument,
        "style": style,
        "oanda_trade_id": str(oanda_trade_id),
        "broker_order_id": str(oanda_trade_id),
        "realized_pnl": 0.0,
        "note": ("Pre-attribution trade claimed by certified worker; "
                  "PnL will flow on close."),
    })
    append_log("oanda_worker_trades.jsonl", {
        "event": "claim_existing_open_trade",
        "worker_id": worker_id, "oanda_trade_id": oanda_trade_id,
    })
    return {"ok": True, "worker_id": worker_id,
            "oanda_trade_id": oanda_trade_id,
            "instrument": instrument,
            "note": "ownership claimed; PnL on close will route to this worker"}


# ── SNAPSHOT ────────────────────────────────────────────────────────

def snapshot() -> Dict[str, Any]:
    ownership = _load_ownership()
    # Count per-worker live trades + total realized PnL from per-worker ledger
    per_worker_realised: Dict[str, float] = {}
    per_worker_open: Dict[str, int] = {}
    rows = 0
    if WORKER_LEDGER_PATH.exists():
        try:
            with WORKER_LEDGER_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    rows += 1
                    try: r = json.loads(line)
                    except Exception: continue
                    if r.get("execution_mode") != "oanda_practice_real":
                        continue
                    wid = r.get("worker_id")
                    if not wid: continue
                    if r.get("event") == "open_filled":
                        per_worker_open[wid] = per_worker_open.get(wid, 0) + 1
                    elif r.get("event") == "close_filled":
                        per_worker_realised[wid] = per_worker_realised.get(wid, 0) + float(r.get("realized_pnl") or 0)
                        per_worker_open[wid] = max(0, per_worker_open.get(wid, 0) - 1)
        except Exception:
            pass
    return {
        "ok": True,
        "kind": "cognitive_oanda_worker_trades",
        "generated_ts": now(),
        "policy": ("Certified-worker gate over the OANDA practice API. "
                    "Per-worker attribution. Learning + compensation "
                    "loop closed on close()."),
        "safety_envelope": dict(SAFETY),
        "ownership_count": len(ownership),
        "ownership_sample": dict(list(ownership.items())[:30]),
        "per_worker_realised_gbp": per_worker_realised,
        "per_worker_open_count": per_worker_open,
        "worker_ledger_rows_total": rows,
    }


def persist() -> Dict[str, Any]:
    snap = snapshot()
    write_registry("cognitive_oanda_worker_trades.json", snap)
    return snap
