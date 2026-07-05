"""WorkerCertification — Per worker, per instrument certification ledger.

States (state machine):
  not_studying  → studying → tested → certified → suspended → studying ...

Certification gates the trading_authority Reasoning rule:
  trade proposal allowed iff status == certified AND not suspended
  AND last_recert_ts within RECERT_VALID_SECONDS.

Recertification triggers:
  · 5 consecutive losses (suspended)
  · RECERT_VALID_SECONDS elapsed since last cert (cert expires)
  · operator-initiated suspension

The classroom + test runner calls stamp() to transition a worker's
status. The reward_engine and reasoning layer call is_authorized() to
check the gate.
"""

from __future__ import annotations
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple, Any
import time

from . import write_registry, append_log, now


# 1 year recert window. Operator can override via direct stamp.
RECERT_VALID_SECONDS = 365 * 86400.0
SUSPENSION_LOSS_STREAK = 5
VALID_STATES = ("not_studying", "studying", "tested", "certified", "suspended")


@dataclass
class CertEntry:
    worker_id: str
    instrument: str
    status: str
    last_change_ts: float
    last_recert_ts: Optional[float] = None
    consecutive_losses: int = 0
    notes: List[str] = field(default_factory=list)
    history: List[Dict[str, Any]] = field(default_factory=list)

    def is_authorized_now(self) -> bool:
        if self.status != "certified":
            return False
        if self.last_recert_ts is None:
            return False
        if (time.time() - self.last_recert_ts) > RECERT_VALID_SECONDS:
            return False
        return True


class WorkerCertification:
    def __init__(self):
        self._entries: Dict[Tuple[str, str], CertEntry] = {}

    def _key(self, worker_id: str, instrument: str) -> Tuple[str, str]:
        return (worker_id, instrument)

    def get_or_create(self, worker_id: str, instrument: str) -> CertEntry:
        k = self._key(worker_id, instrument)
        if k not in self._entries:
            self._entries[k] = CertEntry(
                worker_id=worker_id, instrument=instrument,
                status="not_studying", last_change_ts=time.time(),
            )
        return self._entries[k]

    def stamp(self, worker_id: str, instrument: str,
              new_status: str, note: str = "",
              now_ts: Optional[float] = None) -> CertEntry:
        if new_status not in VALID_STATES:
            raise ValueError(f"invalid status {new_status!r}")
        e = self.get_or_create(worker_id, instrument)
        prior = e.status
        e.status = new_status
        e.last_change_ts = now_ts or time.time()
        if new_status == "certified":
            e.last_recert_ts = e.last_change_ts
            e.consecutive_losses = 0
        if note:
            e.notes.append(note)
        e.history.append({
            "ts": e.last_change_ts, "from": prior, "to": new_status,
            "note": note,
        })
        append_log("worker_certification.jsonl", {
            "event": "stamp",
            "worker_id": worker_id, "instrument": instrument,
            "from": prior, "to": new_status, "note": note,
        })
        return e

    def record_trade_outcome(self, worker_id: str, instrument: str,
                              pnl: float) -> CertEntry:
        e = self.get_or_create(worker_id, instrument)
        if pnl < 0:
            e.consecutive_losses += 1
            if e.consecutive_losses >= SUSPENSION_LOSS_STREAK \
               and e.status == "certified":
                self.stamp(worker_id, instrument, "suspended",
                           note=f"auto-suspend: {e.consecutive_losses} losses")
        else:
            if e.consecutive_losses > 0:
                append_log("worker_certification.jsonl", {
                    "event": "streak_reset",
                    "worker_id": worker_id, "instrument": instrument,
                    "was_losses": e.consecutive_losses,
                })
            e.consecutive_losses = 0
        return e

    def is_authorized(self, worker_id: str, instrument: str) -> bool:
        e = self._entries.get(self._key(worker_id, instrument))
        return bool(e and e.is_authorized_now())

    def certified_workers(self) -> List[Tuple[str, str]]:
        return [(e.worker_id, e.instrument)
                for e in self._entries.values()
                if e.is_authorized_now()]

    def suspended_workers(self) -> List[Tuple[str, str]]:
        return [(e.worker_id, e.instrument)
                for e in self._entries.values()
                if e.status == "suspended"]

    def studying_workers(self) -> List[Tuple[str, str]]:
        return [(e.worker_id, e.instrument)
                for e in self._entries.values()
                if e.status == "studying"]

    def snapshot(self) -> Dict[str, Any]:
        by_status: Dict[str, int] = {}
        by_instrument: Dict[str, Dict[str, int]] = {}
        for e in self._entries.values():
            by_status[e.status] = by_status.get(e.status, 0) + 1
            d = by_instrument.setdefault(e.instrument, {})
            d[e.status] = d.get(e.status, 0) + 1
        rows = sorted(
            [{"worker_id": e.worker_id,
              "instrument": e.instrument,
              "status": e.status,
              "last_change_ts": e.last_change_ts,
              "last_recert_ts": e.last_recert_ts,
              "consecutive_losses": e.consecutive_losses}
             for e in self._entries.values()],
            key=lambda r: r["worker_id"],
        )
        return {
            "ok": True,
            "kind": "cognitive_worker_certification",
            "generated_ts": now(),
            "entry_count": len(self._entries),
            "by_status": by_status,
            "by_instrument": by_instrument,
            "policy": ("Authority gate. trade proposal allowed iff "
                        "status==certified AND not expired."),
            "recert_valid_seconds": RECERT_VALID_SECONDS,
            "suspension_loss_streak": SUSPENSION_LOSS_STREAK,
            "entries_sample": rows[:80],
        }

    def persist(self) -> Dict[str, Any]:
        snap = self.snapshot()
        write_registry("cognitive_worker_certification.json", snap)
        return snap

    def load_from_snapshot(self) -> int:
        """Rehydrate ledger from cognitive_worker_certification.json."""
        from . import COG_REG, load
        d = load(COG_REG / "cognitive_worker_certification.json")
        if not isinstance(d, dict):
            return 0
        count = 0
        for r in d.get("entries_sample") or []:
            wid = r.get("worker_id")
            inst = r.get("instrument")
            if not (wid and inst):
                continue
            k = self._key(wid, inst)
            if k in self._entries:
                continue
            self._entries[k] = CertEntry(
                worker_id=wid, instrument=inst,
                status=r.get("status", "not_studying"),
                last_change_ts=float(r.get("last_change_ts") or 0),
                last_recert_ts=(float(r["last_recert_ts"])
                                  if r.get("last_recert_ts") else None),
                consecutive_losses=int(r.get("consecutive_losses") or 0),
            )
            count += 1
        return count


_CERT: Optional[WorkerCertification] = None


def worker_certification() -> WorkerCertification:
    global _CERT
    if _CERT is None:
        _CERT = WorkerCertification()
    return _CERT
