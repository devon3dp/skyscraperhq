"""WorkerPnL — Per-worker PnL rollup from Floor 41 OANDA practice ledger.

Reads:  data/logs/qsb_floor41_oanda_trade_ledger.jsonl
Emits:  data/registries/cognitive/cognitive_worker_pnl_rollup.json
        per-worker realized_pnl, win_rate, hold_time avg, drawdown,
        per-instrument PnL, per-(instrument,style) PnL (feeds genetics).

Ledger row schema we expect (resilient to absence):
  {
    "ts": "...", "worker_id": "...",
    "instrument": "EUR_USD", "style": "scalp" (optional, defaults "scalp"),
    "units": 100, "side": "buy"|"sell",
    "open_ts": "...", "close_ts": "...",
    "open_price": 1.0850, "close_price": 1.0855,
    "realized_pnl": 0.50    # in account currency
  }

Missing fields are treated as unknown; rows with no worker_id are
attributed to 'unassigned'.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import json
import time

from . import ROOT, write_registry, append_log, now


LEDGER_PATH = ROOT / "data/logs/qsb_floor41_oanda_trade_ledger.jsonl"


@dataclass
class WorkerPnLRow:
    worker_id: str
    closed_trade_count: int = 0
    win_count: int = 0
    loss_count: int = 0
    breakeven_count: int = 0
    realized_pnl: float = 0.0
    best_trade_pnl: float = 0.0
    worst_trade_pnl: float = 0.0
    avg_hold_seconds: float = 0.0
    consecutive_losses_current: int = 0
    consecutive_losses_max: int = 0
    last_trade_ts: Optional[str] = None
    by_instrument_pnl: Dict[str, float] = field(default_factory=dict)
    by_instrument_count: Dict[str, int] = field(default_factory=dict)
    by_pair_pnl: Dict[str, float] = field(default_factory=dict)  # "INST|STYLE" → pnl
    by_pair_count: Dict[str, int] = field(default_factory=dict)

    def win_rate(self) -> Optional[float]:
        decisive = self.win_count + self.loss_count
        if decisive == 0: return None
        return round(self.win_count / decisive, 3)

    def avg_pnl_per_trade(self) -> Optional[float]:
        if self.closed_trade_count == 0: return None
        return round(self.realized_pnl / self.closed_trade_count, 3)


class WorkerPnL:
    def __init__(self):
        self._rows: Dict[str, WorkerPnLRow] = {}
        self._ledger_lines_read = 0

    def _ingest_row(self, r: dict) -> None:
        wid = str(r.get("worker_id") or "unassigned")
        row = self._rows.setdefault(wid, WorkerPnLRow(worker_id=wid))
        pnl = r.get("realized_pnl")
        if isinstance(pnl, (int, float)):
            pnl = float(pnl)
            row.closed_trade_count += 1
            row.realized_pnl += pnl
            row.best_trade_pnl = max(row.best_trade_pnl, pnl)
            row.worst_trade_pnl = min(row.worst_trade_pnl, pnl)
            if pnl > 0:
                row.win_count += 1
                row.consecutive_losses_current = 0
            elif pnl < 0:
                row.loss_count += 1
                row.consecutive_losses_current += 1
                row.consecutive_losses_max = max(
                    row.consecutive_losses_max,
                    row.consecutive_losses_current,
                )
            else:
                row.breakeven_count += 1
            inst = r.get("instrument") or "unknown"
            row.by_instrument_pnl[inst] = row.by_instrument_pnl.get(inst, 0.0) + pnl
            row.by_instrument_count[inst] = row.by_instrument_count.get(inst, 0) + 1
            style = r.get("style") or "scalp"
            pair_key = f"{inst}|{style}"
            row.by_pair_pnl[pair_key] = row.by_pair_pnl.get(pair_key, 0.0) + pnl
            row.by_pair_count[pair_key] = row.by_pair_count.get(pair_key, 0) + 1
        # Hold time estimate (very rough; ignore on parse error)
        try:
            ot = r.get("open_ts"); ct = r.get("close_ts")
            if ot and ct:
                # If they're floats / ints treat as epoch
                if isinstance(ot, (int, float)) and isinstance(ct, (int, float)):
                    hold = float(ct) - float(ot)
                    if hold >= 0:
                        # incremental average
                        n = row.closed_trade_count or 1
                        row.avg_hold_seconds = ((row.avg_hold_seconds * (n - 1))
                                                  + hold) / n
        except Exception:
            pass
        ts = r.get("ts") or r.get("close_ts")
        if isinstance(ts, str):
            row.last_trade_ts = ts

    def refresh(self) -> Dict[str, Any]:
        # Re-read the whole ledger each refresh (cheap; bounded).
        self._rows = {}
        self._ledger_lines_read = 0
        if not LEDGER_PATH.exists():
            return self.snapshot()
        try:
            with LEDGER_PATH.open("r", encoding="utf-8") as f:
                for line in f:
                    self._ledger_lines_read += 1
                    try:
                        rec = json.loads(line)
                    except Exception:
                        continue
                    if isinstance(rec, dict):
                        self._ingest_row(rec)
        except Exception as e:
            append_log("worker_pnl.jsonl",
                       {"event": "refresh_error", "error": str(e)})
        snap = self.snapshot()
        append_log("worker_pnl.jsonl", {
            "event": "refresh",
            "ledger_lines": self._ledger_lines_read,
            "worker_count": len(self._rows),
        })
        return snap

    def top_earners(self, n: int = 10) -> List[Dict[str, Any]]:
        rows = [self._row_dict(r) for r in self._rows.values()]
        rows.sort(key=lambda r: -r["realized_pnl"])
        return rows[:n]

    def biggest_drawdowns(self, n: int = 10) -> List[Dict[str, Any]]:
        rows = [self._row_dict(r) for r in self._rows.values()]
        rows.sort(key=lambda r: r["worst_trade_pnl"])
        return rows[:n]

    def _row_dict(self, r: WorkerPnLRow) -> Dict[str, Any]:
        d = asdict(r)
        d["win_rate"] = r.win_rate()
        d["avg_pnl_per_trade"] = r.avg_pnl_per_trade()
        return d

    def best_pair_for(self, worker_id: str) -> Optional[Tuple[Tuple[str, str], float]]:
        """Return ((instrument, style), pnl) of the worker's best pair."""
        r = self._rows.get(worker_id)
        if not r or not r.by_pair_pnl: return None
        key, pnl = max(r.by_pair_pnl.items(), key=lambda kv: kv[1])
        instrument, style = key.split("|", 1)
        return ((instrument, style), pnl)

    def pnl_by_pair(self, worker_id: str) -> Dict[Tuple[str, str], float]:
        r = self._rows.get(worker_id)
        if not r: return {}
        out: Dict[Tuple[str, str], float] = {}
        for key, pnl in r.by_pair_pnl.items():
            instrument, style = key.split("|", 1)
            out[(instrument, style)] = pnl
        return out

    def closed_trade_count_for(self, worker_id: str) -> int:
        r = self._rows.get(worker_id)
        return r.closed_trade_count if r else 0

    def realized_pnl_for(self, worker_id: str) -> float:
        r = self._rows.get(worker_id)
        return r.realized_pnl if r else 0.0

    def win_rate_for(self, worker_id: str) -> Optional[float]:
        r = self._rows.get(worker_id)
        return r.win_rate() if r else None

    def recent_loss_streak_for(self, worker_id: str) -> int:
        r = self._rows.get(worker_id)
        return r.consecutive_losses_current if r else 0

    def snapshot(self) -> Dict[str, Any]:
        rows = [self._row_dict(r) for r in self._rows.values()]
        total_pnl = sum(r["realized_pnl"] for r in rows)
        return {
            "ok": True,
            "kind": "cognitive_worker_pnl_rollup",
            "generated_ts": now(),
            "policy": ("Read-only rollup. Practice trades only "
                        "(OANDA PRACTICE). No live execution implied."),
            "ledger_path": str(LEDGER_PATH),
            "ledger_lines_read": self._ledger_lines_read,
            "worker_count": len(rows),
            "total_realized_pnl_practice": round(total_pnl, 2),
            "top_earners": self.top_earners(10),
            "biggest_single_trade_losses": self.biggest_drawdowns(10),
            "rows_sample": sorted(rows, key=lambda r: r["worker_id"])[:80],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_worker_pnl_rollup.json", snap)
        return snap


_PNL: Optional[WorkerPnL] = None


def worker_pnl() -> WorkerPnL:
    global _PNL
    if _PNL is None:
        _PNL = WorkerPnL()
    return _PNL
