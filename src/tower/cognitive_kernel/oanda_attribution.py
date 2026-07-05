"""OANDA worker_id attribution helper.

Two surfaces:
  · attribute_row(row, worker_id, style) — call this from wherever
    practice trades get appended to the ledger so the row carries the
    proper attribution.
  · audit_ledger() — scans the ledger for rows missing worker_id and
    reports the count + last-seen timestamps so the operator can decide
    which legacy rows to backfill.
"""

from __future__ import annotations
from typing import Dict, Any, Optional, List, Tuple
import json
import time

from . import ROOT, write_registry, append_log, now


LEDGER_PATH = ROOT / "data/logs/qsb_floor41_oanda_trade_ledger.jsonl"


def attribute_row(row: Dict[str, Any], worker_id: str,
                    style: str = "scalp") -> Dict[str, Any]:
    """Return a copy of `row` with worker_id + style stamped if missing."""
    out = dict(row)
    if not out.get("worker_id"):
        out["worker_id"] = worker_id
    if not out.get("style"):
        out["style"] = style
    return out


def append_attributed(row: Dict[str, Any], worker_id: str,
                        style: str = "scalp") -> None:
    """Append an attributed trade row to the OANDA ledger.

    This is the canonical entry point. Future OANDA placement code
    should call this rather than writing the ledger directly.
    """
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(attribute_row(row, worker_id, style)) + "\n")
    append_log("oanda_attribution.jsonl", {
        "event": "append",
        "worker_id": worker_id, "style": style,
        "instrument": row.get("instrument"),
        "realized_pnl": row.get("realized_pnl"),
    })


def audit_ledger() -> Dict[str, Any]:
    """Scan the ledger; report rows lacking worker_id."""
    total = 0
    unassigned = 0
    last_unassigned_ts: Optional[str] = None
    by_instrument_unassigned: Dict[str, int] = {}
    if not LEDGER_PATH.exists():
        return {
            "ok": True, "kind": "cognitive_oanda_attribution_audit",
            "generated_ts": now(),
            "ledger_present": False,
            "total_rows": 0, "unassigned_rows": 0,
        }
    try:
        with LEDGER_PATH.open("r", encoding="utf-8") as f:
            for line in f:
                total += 1
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if not r.get("worker_id"):
                    unassigned += 1
                    ts = r.get("ts") or r.get("close_ts")
                    if isinstance(ts, str):
                        last_unassigned_ts = ts
                    inst = r.get("instrument") or "unknown"
                    by_instrument_unassigned[inst] = \
                        by_instrument_unassigned.get(inst, 0) + 1
    except Exception as e:
        append_log("oanda_attribution.jsonl",
                   {"event": "audit_error", "error": str(e)})
    return {
        "ok": True,
        "kind": "cognitive_oanda_attribution_audit",
        "generated_ts": now(),
        "ledger_present": True,
        "ledger_path": str(LEDGER_PATH),
        "total_rows": total,
        "unassigned_rows": unassigned,
        "attribution_coverage": round((total - unassigned) / total, 3) if total else 1.0,
        "by_instrument_unassigned": by_instrument_unassigned,
        "last_unassigned_ts": last_unassigned_ts,
        "advice": (
            "Future OANDA placement code MUST call oanda_attribution."
            "append_attributed(row, worker_id, style). Legacy rows can be "
            "left unassigned (they stay in the 'unassigned' bucket of "
            "per-worker PnL) or backfilled manually by the operator."
        ),
    }


def persist() -> Dict[str, Any]:
    snap = audit_ledger()
    write_registry("cognitive_oanda_attribution_audit.json", snap)
    return snap
